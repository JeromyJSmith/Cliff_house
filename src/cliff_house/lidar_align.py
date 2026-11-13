"""Pairwise LiDAR scan registration with capped threads: every prepared scan pair, both directions, as hypotheses.

Input is the `lidar_prep prepare` stage root (`scans.parquet` + `<fp>/scans/<scan>/{cloud_5cm.ply, cloud_2cm.ply,
fpfh_5cm.npy}`). The method is `lidar_prep.register_pair`, unchanged: mutual FPFH matches, 4-DOF RANSAC, the top 24
distinct hypotheses refined by point-to-plane ICP, best kept by feature agreement × colour agreement, then a check on
the 2 cm clouds. This module only schedules it so it cannot oversubscribe the machine:

* every worker runs single-threaded (OMP/BLAS env caps set before the worker imports anything, KD-tree `workers=1`);
* a worker takes one *unordered* pair, computes the mutual matches once and registers A→B and B→A from them (mutual
  nearest neighbours are symmetric, so this is the same result as matching twice);
* new pairs are only started while the 1-minute load average is under `--max-load`, with at most `--workers` running,
  so another job on the machine (e.g. a Resolve render) makes this one back off instead of fighting it.

Output, `<out>/lidar_align/<fp>/` (the bucket layout `stages/lidar_align/<fp>/`):
  pairs/<A>__<B>.json   one per ordered pair as it finishes (a rerun with the same fingerprint resumes, never rewrites)
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
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

STAGE = "lidar_align"
STAGE_VERSION = 1
THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
              "NUMEXPR_NUM_THREADS")
INPUT_FILES = ("cloud_5cm.ply", "cloud_2cm.ply", "fpfh_5cm.npy")
ACCEPT = {"min_check_fitness": 0.25, "max_recip_deg": 1.0, "max_recip_m": 0.05}
STATUS = "hypothesis: pairwise rigid fits with residuals; not survey truth, not an accepted site registration"


def cap_threads(n: int = 1) -> None:
    """Pin the native thread pools of this process (and children it spawns) to n threads. The env caps must be set
    before numpy/scipy load to take effect. Open3D's ICP and evaluation ignore OMP_NUM_THREADS on this build (measured:
    16 threads, ~10× CPU over wall), so its own limit is set too."""
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


def _init_worker(threads: int) -> None:
    cap_threads(threads)


def run_unordered(dir_a: str, dir_b: str, params: dict, todo: tuple[bool, bool]) -> list[dict]:
    """Register A→B and/or B→A from one set of mutual matches. Runs in a single-threaded worker."""
    import numpy as np

    from cliff_house import lidar_prep as lp

    a, b = Path(dir_a), Path(dir_b)
    cap_threads(1)  # idempotent; the pool initializer already did this
    t0 = time.perf_counter()
    ia, ib = lp.feature_matches(np.load(a / "fpfh_5cm.npy"), np.load(b / "fpfh_5cm.npy"))
    match_s = time.perf_counter() - t0
    rows = []
    for (src, dst, m), want in zip(((a, b, (ia, ib)), (b, a, (ib, ia))), todo):
        if not want:
            continue
        tm = {}
        t1 = time.perf_counter()
        row = lp.register_pair(src, dst, params, matches=m, workers=1, timings=tm)
        rows.append(row | {"match_s_shared": match_s, "register_s": time.perf_counter() - t1,
                           **{f"t_{k}": v for k, v in tm.items()}, "worker_pid": os.getpid()})
    return rows


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
          scans: list[str] | None = None, poll_s: float = 15.0, log=print, limit_pairs: int | None = None) -> Path:
    cap_threads(threads)
    import numpy as np
    import open3d
    import scipy

    from cliff_house import lidar_prep as lp

    dirs = scan_dirs(prep_root)
    if scans:
        dirs = {s: dirs[s] for s in scans}
    params = dict(lp.PARAMS)
    versions = {"open3d": open3d.__version__, "scipy": scipy.__version__, "numpy": np.__version__,
                "python": platform.python_version()}
    log(f"hashing inputs of {len(dirs)} scans …")
    inputs = input_hashes(dirs)
    code = code_hashes()
    run_params = {"register": params, "accept": ACCEPT, "seed": 0, "feature_matching": "tiled exact float64"}
    fp = fingerprint(inputs, run_params, code, versions)
    out = out_root / STAGE / fp
    (out / "pairs").mkdir(parents=True, exist_ok=True)

    # Unordered pairs, largest first so the long ones do not trail at the end.
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
        f"{len(done)} ordered results already present; workers ≤ {workers}, load < {max_load}, threads/worker {threads}")
    log(f"output {out}")
    started = datetime.now(timezone.utc)
    t_start = time.time()
    finished_units = total - len(queue)
    ran_here = 0
    running = {}
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(threads,)) as pool:
        while queue or running:
            load1 = os.getloadavg()[0]
            # Admit one new pair per poll while under the load cap (the first always starts, so the run cannot stall
            # forever on a loaded machine; it just runs one at a time).
            if queue and len(running) < workers and (load1 < max_load or not running):
                a, b, todo = queue.pop(0)
                fut = pool.submit(run_unordered, str(dirs[a]), str(dirs[b]), params, todo)
                running[fut] = (a, b, time.time())
                if len(running) < workers and queue and load1 < max_load - 2:
                    continue  # fill quickly while there is clear headroom
            if not running:
                continue
            fin, _ = wait(list(running), timeout=poll_s, return_when=FIRST_COMPLETED)
            for fut in fin:
                a, b, t0 = running.pop(fut)
                try:
                    result = fut.result()
                except Exception as e:  # keep the run going; the pair stays missing and is retried on resume
                    import traceback

                    (out / "pairs" / f"{pair_name(a, b)}.error.txt").write_text(traceback.format_exc())
                    log(f"FAILED {pair_name(a, b)}: {e!r}")
                    result = []
                for row in result:
                    key = (row["a"], row["b"])
                    f = out / "pairs" / f"{pair_name(*key)}.json"
                    tmp = f.with_suffix(".json.part")
                    tmp.write_text(json.dumps(row, indent=1))
                    tmp.rename(f)
                    done[key] = row
                    log(json.dumps({"pair": pair_name(*key), "icp_rmse_m": round(row["icp_rmse_m"], 4),
                                    "icp_fitness": round(row["icp_fitness"], 3),
                                    "ransac_inlier_ratio": round(row["ransac_fitness"], 3),
                                    "check_fitness_2cm": round(row["check_fitness_2cm"], 3),
                                    "tilt_deg": round(row["tilt_deg"], 2), "register_s": round(row["register_s"], 1)}))
                finished_units += 1
                ran_here += 1
                left = len(queue) + len(running)
                eta_h = (time.time() - t_start) / ran_here * left / 3600  # observed throughput, all workers
                log(f"[{datetime.now():%H:%M:%S}] {finished_units}/{total} unordered pairs done "
                    f"({time.time() - t0:.0f}s this pair), running {len(running)}, load {os.getloadavg()[0]:.1f}, "
                    f"ETA {eta_h:.1f} h")
    rows = summarize(done)
    write_parquet(rows, out / "pairs.parquet")
    manifest = {
        "stage": STAGE, "stage_version": STAGE_VERSION, "fingerprint": fp, "status": STATUS,
        "inputs": {"prep_root": str(prep_root), "scans": {s: {"dir": str(dirs[s].relative_to(prep_root)), **inputs[s]}
                                                          for s in sorted(dirs)}},
        "code_sha256": code, "params": run_params, "versions": versions,
        "machine": {"host": platform.node(), "platform": platform.platform(), "cpu": platform.processor(),
                    "workers_max": workers, "threads_per_worker": threads, "max_load": max_load,
                    "thread_env": {k: os.environ.get(k) for k in THREAD_ENV},
                    "open3d_max_threads": int(open3d.utility.get_max_threads())},
        "started_utc": started.isoformat(), "finished_utc": datetime.now(timezone.utc).isoformat(),
        "ordered_pairs": len(rows), "accepted_pairs": sum(r["accepted"] for r in rows),
        "residual_fields": {"icp_rmse_m": "point-to-plane ICP inlier RMSE on the 5 cm clouds (m)",
                            "icp_fitness": "share of 5 cm source points with a target within icp_dist",
                            "ransac_fitness": "RANSAC inlier ratio of the mutual FPFH matches (ransac_dist)",
                            "check_fitness_2cm": "held-out check: share of 2 cm source points within check_dist",
                            "check_rmse_m": "held-out check RMSE (m)", "colour_error": "mean |ΔRGB| on overlap (0–1)",
                            "recip_deg": "rotation of T_ab·T_ba (deg)", "recip_m": "translation of T_ab·T_ba (m)"},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    log(f"done: {manifest['accepted_pairs']} of {len(rows)} ordered pairs pass the gate {ACCEPT}; {out}")
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
    add = [(src, dst) for src, dst in add if dst not in existing]
    for k in range(0, len(add), 200):
        retry(batch_bucket_files, bucket, add=add[k:k + 200])
        log(f"uploaded {min(k + 200, len(add))}/{len(add)} to hf://buckets/{bucket}/{prefix}/")
    return len(add)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prep", type=Path, required=True, help="lidar_prep stage root (has scans.parquet)")
    ap.add_argument("--out", type=Path, required=True, help="stage root; results go to <out>/lidar_align/<fp>/")
    ap.add_argument("--workers", type=int, default=4, help="most pairs running at once")
    ap.add_argument("--max-load", type=float, default=16.0, help="start no new pair while load1 is at or above this")
    ap.add_argument("--threads", type=int, default=1, help="native threads per worker")
    ap.add_argument("--scans", nargs="*", help="only these scans")
    ap.add_argument("--limit-pairs", type=int)
    ap.add_argument("--bucket", help="HF bucket id; upload results under stages/lidar_align/<fp>/ when given")
    args = ap.parse_args(argv)
    log = lambda m: print(m, flush=True)  # noqa: E731
    out = align(args.prep, args.out, args.workers, args.max_load, args.threads, args.scans, log=log,
                limit_pairs=args.limit_pairs)
    if args.bucket:
        upload(out, args.bucket, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
