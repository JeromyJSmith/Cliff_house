"""Pairwise LiDAR scan registration with capped threads: every prepared scan pair, both directions, as hypotheses.

Input is the `lidar_prep prepare` stage root (`scans.parquet` + `<fp>/scans/<scan>/{cloud_5cm.ply, cloud_2cm.ply,
fpfh_5cm.npy}`). The method is `lidar_prep.register_pair`: mutual FPFH matches, 4-DOF RANSAC, the top 24 distinct
hypotheses refined by point-to-plane ICP, best kept by feature agreement × colour agreement, then a check on the 2 cm
clouds. This module schedules it so it cannot oversubscribe a machine that is busy with other work:

* each unordered pair runs in its own process with every native pool at one thread (OMP/BLAS/vecLib env caps, and
  Open3D's own `set_max_threads`, which its ICP needs: it ignores OMP_NUM_THREADS here);
* that process computes the mutual matches once and registers A→B and B→A from them (mutual nearest neighbours are
  symmetric, so this equals matching twice);
* `Throttle` admits at most one new pair per `ramp_s` while the 1-minute load average is under `max_load` and fewer
  than `workers` run; when load stays at or over `max_load` it pauses the newest running pair (SIGSTOP; a stopped
  process leaves the load average) and resumes it (SIGCONT) once load is clearly back under. At least one pair keeps
  running, so the job always makes progress.

Output, `<out>/lidar_align/<fp>/` (the bucket layout `stages/lidar_align/<fp>/`):
  pairs/<A>__<B>.json   one per ordered pair as it finishes (a rerun with the same fingerprint resumes, never rewrites)
  logs/<A>__<B>.log     stdout/stderr of the process that ran the unordered pair
  pairs.parquet         one row per ordered pair + reciprocal consistency of the unordered pair + the acceptance gate
  manifest.json         inputs (sha256 per file), code sha256, parameters, versions, machine, thread caps, timings
The fingerprint covers input hashes, code hashes, parameters and library versions.

Every transform is a **hypothesis** with its residuals (ICP inlier RMSE and fitness, RANSAC inlier ratio, held-out
2 cm check, reciprocal error). Nothing here is survey truth; scale is as captured.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import platform
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STAGE = "lidar_align"
STAGE_VERSION = 1
THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
              "NUMEXPR_NUM_THREADS")
INPUT_FILES = ("cloud_5cm.ply", "cloud_2cm.ply", "fpfh_5cm.npy")
ACCEPT = {"min_check_fitness": 0.25, "max_recip_deg": 1.0, "max_recip_m": 0.05}
STATUS = "hypothesis: pairwise rigid fits with residuals; not survey truth, not an accepted site registration"


def cap_threads(n: int = 1) -> None:
    """Pin this process's native thread pools to n threads. The env caps must be set before numpy/scipy load (the
    scheduler passes them in the child's environment). Open3D's ICP and evaluation ignore OMP_NUM_THREADS on this build
    (measured: 16 threads, ~10× CPU over wall), so its own limit is set too."""
    for k in THREAD_ENV:
        os.environ[k] = str(n)
    import open3d as o3d

    o3d.utility.set_max_threads(n)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


def code_hashes() -> dict:
    here = Path(__file__).resolve().parent
    return {name: sha256_file(here / name) for name in ("lidar_prep.py", "lidar_align.py")}


def fingerprint(inputs: dict, params: dict, code: dict, versions: dict) -> str:
    key = json.dumps({"stage": STAGE, "stage_version": STAGE_VERSION, "inputs": inputs, "params": params,
                      "code": code, "versions": versions}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def scan_dirs(prep_root: Path) -> dict[str, Path]:
    import polars as pl

    s = pl.read_parquet(prep_root / "scans.parquet")
    return {scan: prep_root / fp / "scans" / scan for scan, fp in s.select("scan", "fingerprint").iter_rows()}


def input_hashes(dirs: dict[str, Path]) -> dict:
    return {scan: {f: sha256_file(d / f) for f in INPUT_FILES} for scan, d in sorted(dirs.items())}


def pair_name(a: str, b: str) -> str:
    return f"{a}__{b}"


def run_unordered(dir_a: Path, dir_b: Path, pairs_dir: Path, todo: tuple[bool, bool], threads: int = 1) -> list[dict]:
    """Register A→B and/or B→A from one set of mutual matches; write each result to pairs/<A>__<B>.json atomically."""
    cap_threads(threads)
    import numpy as np

    from cliff_house import lidar_prep as lp

    t0 = time.perf_counter()
    ia, ib = lp.feature_matches(np.load(dir_a / "fpfh_5cm.npy"), np.load(dir_b / "fpfh_5cm.npy"))
    match_s = time.perf_counter() - t0
    rows = []
    for (src, dst, m), want in zip(((dir_a, dir_b, (ia, ib)), (dir_b, dir_a, (ib, ia))), todo):
        if not want:
            continue
        tm = {}
        t1 = time.perf_counter()
        row = lp.register_pair(src, dst, lp.PARAMS, matches=m, workers=threads, timings=tm)
        row |= {"match_s_shared": match_s, "register_s": time.perf_counter() - t1,
                **{f"t_{k}": v for k, v in tm.items()}, "pid": os.getpid(), "host": platform.node(),
                "finished_utc": datetime.now(timezone.utc).isoformat(), "status": "hypothesis"}
        f = pairs_dir / f"{pair_name(row['a'], row['b'])}.json"
        if f.exists():
            raise FileExistsError(f"{f} exists; results are never overwritten")
        tmp = f.with_suffix(".json.part")
        tmp.write_text(json.dumps(row, indent=1))
        tmp.rename(f)
        rows.append(row)
    return rows


class Throttle:
    """Load-average governor. `step` returns "admit", "pause", "resume" or None for one poll.

    admit:  a pair is queued, nothing is paused, fewer than `workers` run, load1 < max_load − 1, and `ramp_s` since
            the last admit (the 1-min load average lags, so ramping slowly avoids overshoot). With nothing running the
            first pair is admitted regardless, so the run never stalls.
    pause:  load1 ≥ max_load on `over_polls` consecutive polls, more than one pair active, `ramp_s` since the last
            pause/resume.
    resume: something is paused, load1 < max_load − hysteresis, `ramp_s` since the last pause/resume."""

    def __init__(self, workers: int, max_load: float, ramp_s: float = 60.0, hysteresis: float = 3.0,
                 over_polls: int = 2):
        self.workers, self.max_load, self.ramp_s, self.hyst, self.over_polls = workers, max_load, ramp_s, hysteresis, over_polls
        self.over = 0
        self.last_admit = self.last_change = -1e18

    def step(self, now: float, load1: float, active: int, paused: int, queued: int) -> str | None:
        self.over = self.over + 1 if load1 >= self.max_load else 0
        if self.over >= self.over_polls and active > 1 and now - self.last_change >= self.ramp_s:
            self.over, self.last_change = 0, now
            return "pause"
        if paused and load1 < self.max_load - self.hyst and now - self.last_change >= self.ramp_s:
            self.last_change = now
            return "resume"
        if queued and not paused and active < self.workers and (
                active == 0 or (load1 < self.max_load - 1 and now - self.last_admit >= self.ramp_s)):
            self.last_admit = now
            return "admit"
        return None


def summarize(rows: dict[tuple[str, str], dict]) -> list[dict]:
    """Ordered-pair rows plus the reciprocal error of their unordered pair and the acceptance gate."""
    import numpy as np

    from cliff_house import lidar_prep as lp

    out = []
    for (a, b), row in sorted(rows.items()):
        r = dict(row)
        back = rows.get((b, a))
        if back is not None:
            r["recip_deg"], r["recip_m"] = lp.reciprocal_error(np.array(row["T_b_a"]), np.array(back["T_b_a"]))
        else:
            r["recip_deg"] = r["recip_m"] = None
        r["accepted"] = back is not None and lp.accept(r, **ACCEPT)
        r["status"] = "hypothesis"
        out.append(r)
    return out


def write_parquet(rows: list[dict], path: Path) -> None:
    import polars as pl

    pl.DataFrame([{k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()} for r in rows],
                 infer_schema_length=None).write_parquet(path)


def align(prep_root: Path, out_root: Path, workers: int = 4, max_load: float = 16.0, threads: int = 1,
          scans: list[str] | None = None, poll_s: float = 15.0, ramp_s: float = 60.0, log=print,
          limit_pairs: int | None = None) -> Path:
    cap_threads(threads)
    import numpy as np
    import open3d
    import scipy

    from cliff_house import lidar_prep as lp

    dirs = scan_dirs(prep_root)
    if scans:
        dirs = {s: dirs[s] for s in scans}
    versions = {"open3d": open3d.__version__, "scipy": scipy.__version__, "numpy": np.__version__,
                "python": platform.python_version()}
    log(f"hashing inputs of {len(dirs)} scans …")
    inputs = input_hashes(dirs)
    code = code_hashes()
    run_params = {"register": dict(lp.PARAMS), "accept": ACCEPT, "seed": 0, "feature_matching": "tiled exact float64"}
    fp = fingerprint(inputs, run_params, code, versions)
    out = out_root / STAGE / fp
    (out / "pairs").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)
    outer_log = log

    def log(m: str) -> None:  # noqa: F811 — also keep the progress log with the results
        outer_log(m)
        with open(out / "run.log", "a") as f:
            f.write(m + "\n")

    # Unordered pairs, most expensive first (matching ~ na·nb) so the long ones do not trail at the end.
    size = {s: (d / "cloud_5cm.ply").stat().st_size for s, d in dirs.items()}
    pairs = sorted(itertools.combinations(sorted(dirs), 2), key=lambda p: -size[p[0]] * size[p[1]])
    if limit_pairs:
        pairs = pairs[:limit_pairs]
    done = {}
    for a, b in itertools.permutations(sorted(dirs), 2):
        f = out / "pairs" / f"{pair_name(a, b)}.json"
        if f.exists():
            done[(a, b)] = json.loads(f.read_text())
    queue = [(a, b, ((a, b) not in done, (b, a) not in done)) for a, b in pairs
             if (a, b) not in done or (b, a) not in done]
    total = len(pairs)
    log(f"fingerprint {fp}: {total} unordered pairs ({2 * total} ordered), {len(queue)} to run, "
        f"{len(done)} ordered results already present; workers ≤ {workers}, load < {max_load}, threads/pair {threads}")
    log(f"output {out}")
    started = datetime.now(timezone.utc)
    t_start = time.time()
    finished, ran_here = total - len(queue), 0
    env = os.environ | {k: str(threads) for k in THREAD_ENV}
    src_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = src_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    running: dict[int, dict] = {}  # pid -> {proc, a, b, t0, paused, logf}
    throttle = Throttle(workers, max_load, ramp_s)
    peak_active = 0
    try:
        while queue or running:
            for pid, job in list(running.items()):
                if job["proc"].poll() is None:
                    continue
                del running[pid]
                job["logf"].close()
                a, b = job["a"], job["b"]
                got = [(x, y) for x, y in ((a, b), (b, a)) if (out / "pairs" / f"{pair_name(x, y)}.json").exists()]
                if job["proc"].returncode != 0:
                    log(f"FAILED {pair_name(a, b)} (exit {job['proc'].returncode}); see logs/{pair_name(a, b)}.log")
                for key in got:
                    if key in done:
                        continue
                    row = done[key] = json.loads((out / "pairs" / f"{pair_name(*key)}.json").read_text())
                    log(json.dumps({"pair": pair_name(*key), "icp_rmse_m": round(row["icp_rmse_m"], 4),
                                    "icp_fitness": round(row["icp_fitness"], 3),
                                    # share of FPFH matches inside the best RANSAC hypothesis: ~1e-5..1e-4 here,
                                    # so 3 decimals printed a misleading 0.0
                                    "ransac_fitness": float(f"{row['ransac_fitness']:.3g}"),
                                    "check_fitness_2cm": round(row["check_fitness_2cm"], 3),
                                    "tilt_deg": round(row["tilt_deg"], 2), "register_s": round(row["register_s"], 1)}))
                finished += 1
                ran_here += 1
                left = len(queue) + len(running)
                eta_h = (time.time() - t_start) / ran_here * left / 3600
                log(f"[{datetime.now():%H:%M:%S}] {finished}/{total} unordered pairs done "
                    f"({time.time() - job['t0']:.0f}s this pair), running {len(running)}, "
                    f"load {os.getloadavg()[0]:.1f}, ETA {eta_h:.1f} h")
            paused = [p for p, j in running.items() if j["paused"]]
            active = len(running) - len(paused)
            load1 = os.getloadavg()[0]
            action = throttle.step(time.time(), load1, active, len(paused), len(queue))
            if action == "admit":
                a, b, todo = queue.pop(0)
                logf = open(out / "logs" / f"{pair_name(a, b)}.log", "a")
                cmd = [sys.executable, "-m", "cliff_house.lidar_align", "_pair", str(dirs[a]), str(dirs[b]),
                       str(out / "pairs"), "".join("1" if t else "0" for t in todo), "--threads", str(threads)]
                proc = subprocess.Popen(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT)
                running[proc.pid] = {"proc": proc, "a": a, "b": b, "t0": time.time(), "paused": False, "logf": logf}
                log(f"[{datetime.now():%H:%M:%S}] start {pair_name(a, b)} pid {proc.pid}; active {active + 1}, "
                    f"paused {len(paused)}, load {load1:.1f}")
            elif action == "pause":
                pid = max((p for p in running if not running[p]["paused"]), key=lambda p: running[p]["t0"])
                os.kill(pid, signal.SIGSTOP)
                running[pid]["paused"] = True
                log(f"[{datetime.now():%H:%M:%S}] load {load1:.1f} ≥ {max_load}: paused pid {pid}")
            elif action == "resume":
                pid = min(paused, key=lambda p: running[p]["t0"])
                os.kill(pid, signal.SIGCONT)
                running[pid]["paused"] = False
                log(f"[{datetime.now():%H:%M:%S}] load {load1:.1f}: resumed pid {pid}")
            peak_active = max(peak_active, len(running) - sum(j["paused"] for j in running.values()))
            if action != "admit" or not queue:
                time.sleep(poll_s)
    finally:
        for pid, job in running.items():  # interrupted: let paused children finish rather than leave them stopped
            if job["paused"]:
                os.kill(pid, signal.SIGCONT)
    rows = summarize(done)
    write_parquet(rows, out / "pairs.parquet")
    missing = [pair_name(a, b) for a, b in pairs for k in ((a, b), (b, a)) if k not in done]
    manifest = {
        "stage": STAGE, "stage_version": STAGE_VERSION, "fingerprint": fp, "status": STATUS,
        "inputs": {"prep_root": str(prep_root), "scans": {s: {"dir": str(dirs[s].relative_to(prep_root)), **inputs[s]}
                                                          for s in sorted(dirs)}},
        "code_sha256": code, "params": run_params, "versions": versions,
        "machine": {"host": platform.node(), "platform": platform.platform(), "cpu": platform.processor(),
                    "workers_max": workers, "peak_active": peak_active, "threads_per_pair": threads,
                    "max_load": max_load, "ramp_s": ramp_s, "thread_env": {k: env.get(k) for k in THREAD_ENV},
                    "open3d_max_threads": int(open3d.utility.get_max_threads())},
        "started_utc": started.isoformat(), "finished_utc": datetime.now(timezone.utc).isoformat(),
        "ordered_pairs": len(rows), "missing_ordered_pairs": missing, "accepted_pairs": sum(r["accepted"] for r in rows),
        "residual_fields": {"icp_rmse_m": "point-to-plane ICP inlier RMSE on the 5 cm clouds (m)",
                            "icp_fitness": "share of 5 cm source points with a target within icp_dist",
                            "ransac_fitness": "RANSAC inlier ratio of the mutual FPFH matches (ransac_dist)",
                            "check_fitness_2cm": "held-out check: share of 2 cm source points within check_dist",
                            "check_rmse_m": "held-out check RMSE (m)", "colour_error": "mean |ΔRGB| on overlap (0–1)",
                            "recip_deg": "rotation of T_ab·T_ba (deg)", "recip_m": "translation of T_ab·T_ba (m)"},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    log(f"done: {manifest['accepted_pairs']} of {len(rows)} ordered pairs pass the gate {ACCEPT}; "
        f"{len(missing)} missing; {out}")
    return out


def upload(out: Path, bucket: str, log=print) -> int:
    """Copy `<out>` to `stages/lidar_align/<fp>/` in the bucket. Never overwrites: files already there are skipped."""
    from huggingface_hub import batch_bucket_files, list_bucket_tree

    from cliff_house.storage import retry

    bucket = bucket.removeprefix("hf://buckets/").rstrip("/")
    prefix = f"stages/{STAGE}/{out.name}"
    existing = {getattr(e, "path", "") for e in retry(lambda: list(list_bucket_tree(bucket, prefix, recursive=True)))}
    files = sorted(p for p in out.rglob("*") if p.is_file() and not p.name.endswith(".part"))
    add = [(str(p), f"{prefix}/{p.relative_to(out).as_posix()}") for p in files]
    skipped = [dst for _, dst in add if dst in existing]
    add = [(src, dst) for src, dst in add if dst not in existing]
    for k in range(0, len(add), 200):
        retry(batch_bucket_files, bucket, add=add[k:k + 200])
        log(f"uploaded {min(k + 200, len(add))}/{len(add)} to hf://buckets/{bucket}/{prefix}/")
    if skipped:
        log(f"{len(skipped)} files already in the bucket were left as they are")
    return len(add)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "_pair":  # internal: one unordered pair in a capped child process
        ap = argparse.ArgumentParser()
        ap.add_argument("dir_a", type=Path)
        ap.add_argument("dir_b", type=Path)
        ap.add_argument("pairs_dir", type=Path)
        ap.add_argument("todo")
        ap.add_argument("--threads", type=int, default=1)
        a = ap.parse_args(argv[1:])
        run_unordered(a.dir_a, a.dir_b, a.pairs_dir, (a.todo[0] == "1", a.todo[1] == "1"), a.threads)
        return 0
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prep", type=Path, required=True, help="lidar_prep stage root (has scans.parquet)")
    ap.add_argument("--out", type=Path, required=True, help="stage root; results go to <out>/lidar_align/<fp>/")
    ap.add_argument("--workers", type=int, default=4, help="most pairs holding a slot at once")
    ap.add_argument("--max-load", type=float, default=16.0, help="1-min load average to stay under")
    ap.add_argument("--ramp", type=float, default=60.0, help="seconds between admits and between pause/resume steps")
    ap.add_argument("--threads", type=int, default=1, help="native threads per pair process")
    ap.add_argument("--scans", nargs="*", help="only these scans")
    ap.add_argument("--limit-pairs", type=int)
    ap.add_argument("--bucket", help="HF bucket id; upload results under stages/lidar_align/<fp>/ when given")
    args = ap.parse_args(argv)
    log = lambda m: print(m, flush=True)  # noqa: E731
    out = align(args.prep, args.out, args.workers, args.max_load, args.threads, args.scans, ramp_s=args.ramp,
                log=log, limit_pairs=args.limit_pairs)
    if args.bucket:
        upload(out, args.bucket, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
