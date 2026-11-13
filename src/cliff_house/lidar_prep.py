"""Stage 7 input: SiteScape LiDAR scans → cleaned clouds, features, gravity-consistent pairwise registrations.

SiteScape writes one binary PLY per scan (float32 x y z + uchar r g b, up to ~24 M points) in the iPhone's ARKit
session frame: metres, gravity-aligned with **+y up**, and an origin and heading of its own. Two scans of the same
site therefore differ by a rotation about the vertical axis plus a translation (4 DOF). That is the key constraint:
the earlier whole-cloud ICP attempt (docs/registration-20261111) was fooled by repeated walls, while a match that
needs to tilt one scan to fit is wrong by construction and is rejected here.

Per scan (`prepare_scan`), under `stages/lidar/<fp>/scans/<scan>/`:
  cloud_2cm.ply   voxel 2 cm, statistical outliers removed, normals; colour kept
  cloud_5cm.ply   voxel 5 cm with normals (registration working set)
  fpfh_5cm.npy    33-D FPFH features of cloud_5cm (float32)
  stats.json      counts, extent, which axis is up (from normals), floor height, density
Per pair (`register_pair`), rows of `pairs.parquet`:
  mutual FPFH matches, a 4-DOF RANSAC (yaw about up + translation, 2-point minimal samples), then point-to-plane ICP; fitness, inlier RMSE, tilt, yaw,
  translation, a check on the 2 cm clouds the fit did not use, and reciprocal consistency (A→B vs B→A).
Units stay metres as captured; nothing here asserts survey accuracy.

Provenance: written by a Claude session on the iMac (2026-11-12, run dir `runs/lidar-prep/9e0e864`), which prepared
the 24 November 9 SiteScape scans with `prepare`. Its `pairs` run oversubscribed that machine (every worker's KD-tree
and ICP used every core). Brought into the repo unchanged apart from: an explicit `workers` thread count for the
KD-tree queries (it was `-1`, all cores, per worker), and `register_pair` accepting precomputed matches, because mutual
nearest neighbours are symmetric and the B→A run can reuse the A→B matches. The pairwise driver with thread caps,
fingerprints and a manifest is `cliff_house.lidar_align`.
"""
import argparse
import hashlib
import json
import math
from importlib.metadata import version
from pathlib import Path

import numpy as np

STAGE = "lidar"
STAGE_VERSION = 1
PARAMS = {"voxel_fine": 0.02, "voxel_reg": 0.05, "sor_neighbors": 20, "sor_std": 2.0,
          "fpfh_radius": 0.25, "ransac_dist": 0.075, "ransac_hypotheses": 40000, "icp_candidates": 24,
          "icp_dist": 0.05, "max_tilt_deg": 1.5, "check_dist": 0.03}


# ---------- reading ----------

_PLY_TYPES = {"float": "f4", "float32": "f4", "double": "f8", "float64": "f8", "uchar": "u1", "uint8": "u1",
              "char": "i1", "int8": "i1", "short": "i2", "ushort": "u2", "int": "i4", "uint": "u4"}


def read_ply_xyzrgb(path: Path) -> tuple[np.ndarray, np.ndarray | None]:
    """Binary little-endian PLY with a vertex element → (N×3 float64 xyz, N×3 uint8 rgb or None), via memmap."""
    with open(path, "rb") as f:
        header, props, count = b"", [], 0
        while True:
            line = f.readline()
            header += line
            parts = line.decode("ascii", "replace").split()
            if not parts:
                continue
            if parts[0] == "format" and parts[1] != "binary_little_endian":
                raise ValueError(f"{path}: {parts[1]} PLY not supported")
            if parts[0] == "element":
                in_vertex = parts[1] == "vertex"
                if in_vertex:
                    count = int(parts[2])
            elif parts[0] == "property" and in_vertex:
                props.append((parts[2], "<" + _PLY_TYPES[parts[1]]))
            elif parts[0] == "end_header":
                break
    data = np.memmap(path, dtype=np.dtype(props), mode="r", offset=len(header), shape=(count,))
    xyz = np.stack([data["x"], data["y"], data["z"]], 1).astype(np.float64)
    rgb = np.stack([data["red"], data["green"], data["blue"]], 1).astype(np.uint8) if "red" in data.dtype.names else None
    return xyz, rgb


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(source_sha256: str) -> str:
    key = json.dumps({"stage": STAGE, "stage_version": STAGE_VERSION, "open3d": version("open3d"), "params": PARAMS,
                      "source_sha256": source_sha256}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ---------- per scan ----------

def up_axis(normals: np.ndarray) -> dict:
    """Which coordinate axis is vertical: the one most surface normals align with (floors and ceilings are the
    largest horizontal surfaces in a scan). Returns the axis and the fraction of normals within 10° of it."""
    frac = {ax: float(np.mean(np.abs(normals[:, i]) > math.cos(math.radians(10)))) for i, ax in enumerate("xyz")}
    axis = max(frac, key=frac.get)
    return {"up_axis": axis, "horizontal_normal_fraction": frac}


def prepare_scan(path: Path, out_dir: Path, params: dict = PARAMS) -> dict:
    import open3d as o3d

    out_dir.mkdir(parents=True, exist_ok=True)
    xyz, rgb = read_ply_xyzrgb(path)
    finite = np.isfinite(xyz).all(1)
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(xyz[finite]))
    if rgb is not None:
        pcd.colors = o3d.utility.Vector3dVector(rgb[finite] / 255.0)
    raw = int(finite.sum())
    fine = pcd.voxel_down_sample(params["voxel_fine"])
    fine, _ = fine.remove_statistical_outlier(params["sor_neighbors"], params["sor_std"])
    fine.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=4 * params["voxel_fine"], max_nn=30))
    reg = fine.voxel_down_sample(params["voxel_reg"])
    reg.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=2 * params["voxel_reg"], max_nn=30))
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        reg, o3d.geometry.KDTreeSearchParamHybrid(radius=params["fpfh_radius"], max_nn=100))
    o3d.io.write_point_cloud(str(out_dir / "cloud_2cm.ply"), fine)
    o3d.io.write_point_cloud(str(out_dir / "cloud_5cm.ply"), reg)
    np.save(out_dir / "fpfh_5cm.npy", np.asarray(fpfh.data, dtype=np.float32).T)
    p = np.asarray(fine.points)
    up = up_axis(np.asarray(fine.normals))
    ui = "xyz".index(up["up_axis"])
    stats = {"scan": path.stem, "points_raw": raw, "points_2cm": len(fine.points), "points_5cm": len(reg.points),
             "bbox_min": p.min(0).tolist(), "bbox_max": p.max(0).tolist(),
             "extent_m": (p.max(0) - p.min(0)).tolist(),
             # Floor/ceiling heights along the up axis: robust low/high percentiles of the clean cloud.
             "up_p02_m": float(np.percentile(p[:, ui], 2)), "up_p98_m": float(np.percentile(p[:, ui], 98)), **up}
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats


# ---------- per pair ----------

def tilt_and_yaw(T: np.ndarray, up: int = 1) -> tuple[float, float]:
    """Tilt = angle between the up axis and its image under R (0 for a pure rotation about up); yaw about up."""
    R = T[:3, :3]
    u = np.zeros(3)
    u[up] = 1.0
    tilt = math.degrees(math.acos(float(np.clip(R[:, up] @ u, -1, 1))))
    # Right-handed angle about `up`: with (i, j, up) cyclic, R[j, i] = sin θ and R[i, j] = −sin θ.
    i, j = (up + 1) % 3, (up + 2) % 3
    yaw = math.degrees(math.atan2(R[j, i] - R[i, j], R[i, i] + R[j, j]))
    return tilt, yaw


def yaw_matrix(theta: np.ndarray, up: int = 1) -> np.ndarray:
    """Batch of rotations about `up` by theta (radians): shape (..., 3, 3)."""
    i, j = (up + 1) % 3, (up + 2) % 3
    c, s = np.cos(theta), np.sin(theta)
    R = np.zeros(np.shape(theta) + (3, 3))
    R[..., up, up] = 1.0
    R[..., i, i] = c
    R[..., j, j] = c
    R[..., j, i] = s
    R[..., i, j] = -s
    return R


def ransac_4dof(src: np.ndarray, dst: np.ndarray, dist: float, iterations: int = 20000, score_sample: int = 5000,
                up: int = 1, seed: int = 0, top_k: int = 1) -> tuple[np.ndarray, float] | list[tuple[np.ndarray, float]]:
    """Yaw-about-up + translation from putative correspondences src[k] ↔ dst[k].

    Gravity-aligned scans differ only by these 4 DOF, so a minimal sample is two correspondences: the yaw that turns
    their horizontal separation in src onto the one in dst, and the translation that then moves the first onto the
    first. Samples whose separations differ in length or in height by more than `dist` are discarded early.
    Returns (4x4 transform, inlier fraction over all correspondences); with top_k > 1, a list of the top_k distinct
    hypotheses (yaw differing by > 2° or translation by > 2·dist), best first."""
    rng = np.random.default_rng(seed)
    n = len(src)
    if n < 3:
        return np.eye(4), 0.0
    i, j = (up + 1) % 3, (up + 2) % 3
    k1, k2 = rng.integers(0, n, iterations), rng.integers(0, n, iterations)
    ds, dd = src[k2] - src[k1], dst[k2] - dst[k1]
    hs, hd = np.hypot(ds[:, i], ds[:, j]), np.hypot(dd[:, i], dd[:, j])
    ok = (k1 != k2) & (np.abs(hs - hd) < dist) & (np.abs(ds[:, up] - dd[:, up]) < dist) & (hs > 5 * dist)
    k1, ds, dd = k1[ok], ds[ok], dd[ok]
    if len(k1) == 0:
        return np.eye(4), 0.0
    # Rotation about up maps (i, j) components by angle θ: θ = angle(dd_ij) − angle(ds_ij).
    theta = np.arctan2(dd[:, j], dd[:, i]) - np.arctan2(ds[:, j], ds[:, i])
    R = yaw_matrix(theta, up)
    t = dst[k1] - np.einsum("hab,hb->ha", R, src[k1])
    sample = rng.choice(n, min(score_sample, n), replace=False)
    scores = np.empty(len(R), dtype=np.int64)
    for start in range(0, len(R), 2000):  # score hypotheses in batches on a correspondence sample
        Rb, tb = R[start:start + 2000], t[start:start + 2000]
        pred = np.einsum("hab,nb->hna", Rb, src[sample]) + tb[:, None, :]
        scores[start:start + 2000] = (np.linalg.norm(pred - dst[sample][None], axis=2) < dist).sum(1)
    picked: list[tuple[np.ndarray, float]] = []
    for h in np.argsort(-scores):
        if len(picked) == top_k:
            break
        if any(abs(math.remainder(theta[h] - th, 2 * math.pi)) < math.radians(2) and np.linalg.norm(t[h] - tt) < 2 * dist
               for th, tt in ((math.atan2(P[(up + 2) % 3, (up + 1) % 3], P[(up + 1) % 3, (up + 1) % 3]), P[:3, 3])
                              for P, _ in picked)):
            continue
        T = np.eye(4)
        T[:3, :3], T[:3, 3] = R[h], t[h]
        inl = np.linalg.norm(src @ R[h].T + t[h] - dst, axis=1) < dist
        picked.append((T, float(inl.mean())))
    return picked if top_k > 1 else picked[0]


def nearest_tiled(fa: np.ndarray, fb: np.ndarray, tile_a: int = 256, tile_b: int = 2048
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Exact Euclidean nearest neighbour both ways (a→b, b→a) by tiled brute force in float64.

    A KD-tree degenerates towards brute force in 33-D FPFH space, and with extra per-node overhead: on two scans of
    61 k and 103 k points this is ~3× less CPU than two cKDTree queries and returns the same neighbours (checked
    against cKDTree in tests). Features are centred first and the squared norms ride inside one GEMM
    ([-2x, |x|², 1]·[y, 1, |y|²]), so float64 cancellation error stays ~1e-10 in squared distance — only exact
    ties (identical features) can resolve differently from a KD-tree, as they can between KD-tree builds.
    Tiles keep the distance block cache-sized; BLAS threading follows VECLIB/OPENBLAS caps."""
    mu = np.concatenate([fa, fb]).astype(np.float64).mean(0)
    X, Y = fa.astype(np.float64) - mu, fb.astype(np.float64) - mu
    xn, yn = np.einsum("ij,ij->i", X, X), np.einsum("ij,ij->i", Y, Y)
    X = np.hstack([-2 * X, xn[:, None], np.ones((len(X), 1))])
    YT = np.ascontiguousarray(np.hstack([Y, np.ones((len(Y), 1)), yn[:, None]]).T)
    best_a, ab = np.full(len(X), np.inf), np.zeros(len(X), np.int64)
    best_b, ba = np.full(len(Y), np.inf), np.zeros(len(Y), np.int64)
    buf = np.empty((tile_a, tile_b))
    for j in range(0, len(Y), tile_b):
        yt = YT[:, j:j + tile_b]
        m = yt.shape[1]
        for i in range(0, len(X), tile_a):
            xi = X[i:i + tile_a]
            n = len(xi)
            D = buf[:n, :m]
            np.matmul(xi, yt, out=D)
            r = D.argmin(1)
            rv = np.take_along_axis(D, r[:, None], 1)[:, 0]
            u = rv < best_a[i:i + n]
            best_a[i:i + n][u], ab[i:i + n][u] = rv[u], r[u] + j
            c = D.argmin(0)
            cv = np.take_along_axis(D, c[None], 0)[0]
            u = cv < best_b[j:j + m]
            best_b[j:j + m][u], ba[j:j + m][u] = cv[u], c[u] + i
    return ab, ba


def feature_matches(fa: np.ndarray, fb: np.ndarray, workers: int = 1, method: str = "tiled"
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Mutual nearest neighbours in FPFH space: index arrays into a and b.

    method "tiled" (default): exact tiled brute force, `nearest_tiled`. "kdtree": the original cKDTree queries with
    `workers` threads each."""
    if method == "tiled":
        ab, ba = nearest_tiled(fa, fb)
    else:
        from scipy.spatial import cKDTree

        _, ab = cKDTree(fb).query(fa, k=1, workers=workers)
        _, ba = cKDTree(fa).query(fb, k=1, workers=workers)
    ia = np.arange(len(fa))
    mutual = ba[ab] == ia
    return ia[mutual], ab[mutual]


def colour_error(a, b, T: np.ndarray, dist: float, workers: int = 1) -> float:
    """Mean absolute RGB difference (0–1) between points of `a` moved by T and their nearest `b` point within
    `dist`; 1.0 when there is no overlap or no colour."""
    from scipy.spatial import cKDTree

    if not (a.has_colors() and b.has_colors()):
        return 0.0
    pa = np.asarray(a.points) @ T[:3, :3].T + T[:3, 3]
    d, nn = cKDTree(np.asarray(b.points)).query(pa, k=1, distance_upper_bound=dist, workers=workers)
    hit = np.isfinite(d)
    if not hit.any():
        return 1.0
    return float(np.abs(np.asarray(a.colors)[hit] - np.asarray(b.colors)[nn[hit]]).mean())


def register_pair(dir_a: Path, dir_b: Path, params: dict = PARAMS, seed: int = 0,
                  matches: tuple[np.ndarray, np.ndarray] | None = None, workers: int = 1,
                  timings: dict | None = None) -> dict:
    """Transform taking scan A into scan B's frame (T_b_a), with acceptance diagnostics.

    `matches`: precomputed (ia, ib) from `feature_matches` for this ordered pair (else computed here).
    `timings`: if given, filled with seconds per phase."""
    import time

    import open3d as o3d

    reg = o3d.pipelines.registration
    tm = timings if timings is not None else {}
    t0 = time.perf_counter()
    a = o3d.io.read_point_cloud(str(dir_a / "cloud_5cm.ply"))
    b = o3d.io.read_point_cloud(str(dir_b / "cloud_5cm.ply"))
    if matches is None:
        matches = feature_matches(np.load(dir_a / "fpfh_5cm.npy"), np.load(dir_b / "fpfh_5cm.npy"), workers)
    ia, ib = matches
    tm["load_and_match_s"] = time.perf_counter() - t0
    pa, pb = np.asarray(a.points)[ia], np.asarray(b.points)[ib]
    # Refine the strongest distinct 4-DOF hypotheses with ICP on the full 5 cm clouds and keep the best fit:
    # correspondence counts alone can prefer a slide along a repeated wall.
    # Which refined candidate to keep: overlap alone is a trap (sliding along long plain walls can overlap *more*
    # than the true fit), so the score is the share of distinctive FPFH matches the refined transform still
    # satisfies, times the colour agreement of the overlap (rectangular rooms also fit turned 180°; SiteScape
    # scans carry RGB). Overlap is still reported and gated separately.
    best = None
    t0 = time.perf_counter()
    hyps = ransac_4dof(pa, pb, params["ransac_dist"], params["ransac_hypotheses"], seed=seed,
                       top_k=params["icp_candidates"])
    hyps = hyps if isinstance(hyps, list) else [hyps]  # top_k > 1 returns a list, except in the degenerate n < 3 case
    tm["ransac_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    for T0, frac in hyps:
        r = reg.registration_icp(a, b, params["icp_dist"], T0, reg.TransformationEstimationPointToPlane(),
                                 reg.ICPConvergenceCriteria(max_iteration=60))
        if tilt_and_yaw(np.asarray(r.transformation))[0] > params["max_tilt_deg"]:
            continue
        Tr = np.asarray(r.transformation)
        color_err = colour_error(a, b, Tr, params["icp_dist"], workers)
        feat_frac = float(np.mean(np.linalg.norm(pa @ Tr[:3, :3].T + Tr[:3, 3] - pb, axis=1) < params["ransac_dist"]))
        score = feat_frac * (1.0 - color_err)
        if best is None or score > best[2]:
            best = (r, frac, score, color_err)
    if best is None:  # every candidate tilted away from gravity: report the strongest, it will be rejected
        T0, frac = ransac_4dof(pa, pb, params["ransac_dist"], params["ransac_hypotheses"], seed=seed)
        r = reg.registration_icp(a, b, params["icp_dist"], T0, reg.TransformationEstimationPointToPlane())
        best = (r, frac, 0.0, colour_error(a, b, np.asarray(r.transformation), params["icp_dist"], workers))
    tm["icp_candidates_s"] = time.perf_counter() - t0
    icp, ransac_fitness, _, color_err = best
    T = np.asarray(icp.transformation)
    tilt, yaw = tilt_and_yaw(T)
    # Check on the 2 cm clouds, which the fit never saw: overlap fraction and RMSE at a tighter threshold.
    fa2 = o3d.io.read_point_cloud(str(dir_a / "cloud_2cm.ply"))
    fb2 = o3d.io.read_point_cloud(str(dir_b / "cloud_2cm.ply"))
    check = reg.evaluate_registration(fa2, fb2, params["check_dist"], T)
    tm["check_s"] = time.perf_counter() - t0 - tm["icp_candidates_s"]
    return {"a": dir_a.name, "b": dir_b.name, "T_b_a": T.tolist(), "matches": int(len(ia)),
            "ransac_fitness": ransac_fitness, "colour_error": color_err,
            "icp_fitness": float(icp.fitness), "icp_rmse_m": float(icp.inlier_rmse), "tilt_deg": tilt,
            "yaw_deg": yaw, "translation_m": T[:3, 3].tolist(), "check_fitness_2cm": float(check.fitness),
            "check_rmse_m": float(check.inlier_rmse)}


def reciprocal_error(T_ab: np.ndarray, T_ba: np.ndarray) -> tuple[float, float]:
    """Rotation (deg) and translation (m) of T_ab·T_ba, which is identity for consistent fits."""
    E = np.asarray(T_ab) @ np.asarray(T_ba)
    ang = math.degrees(math.acos(float(np.clip((np.trace(E[:3, :3]) - 1) / 2, -1, 1))))
    return ang, float(np.linalg.norm(E[:3, 3]))


def accept(row: dict, params: dict = PARAMS, min_check_fitness: float = 0.25,
           max_recip_deg: float = 1.0, max_recip_m: float = 0.05) -> bool:
    return (row["tilt_deg"] <= params["max_tilt_deg"] and row["check_fitness_2cm"] >= min_check_fitness
            and row.get("recip_deg", 0.0) <= max_recip_deg and row.get("recip_m", 0.0) <= max_recip_m)


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("prepare", help="clean, downsample and featurize scans")
    p1.add_argument("scans", nargs="+", type=Path)
    p1.add_argument("--out", type=Path, required=True, help="stage root; scans go to <out>/<fp>/scans/<scan>/")
    p1.add_argument("--manifest", type=Path, help="sources.parquet for SHA-256 (else hash the file)")
    p2 = sub.add_parser("pairs", help="register every pair of prepared scans in both directions")
    p2.add_argument("--out", type=Path, required=True)
    p2.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)

    if args.cmd == "prepare":
        import polars as pl

        known = {}
        if args.manifest:
            known = {Path(p).name: s for p, s in pl.read_parquet(args.manifest).select("path", "sha256").iter_rows()}
        rows = []
        for scan in sorted(args.scans):
            sha = known.get(scan.name) or sha256_file(scan)
            fp = fingerprint(sha)
            d = args.out / fp / "scans" / scan.stem
            if (d / "stats.json").exists():
                stats = json.loads((d / "stats.json").read_text())
            else:
                stats = prepare_scan(scan, d)
            rows.append({"scan": scan.stem, "fingerprint": fp, "source_sha256": sha, **{k: stats[k] for k in (
                "points_raw", "points_2cm", "points_5cm", "up_axis", "up_p02_m", "up_p98_m")},
                "extent_x": stats["extent_m"][0], "extent_y": stats["extent_m"][1], "extent_z": stats["extent_m"][2]})
            print(json.dumps(rows[-1]), flush=True)
        pl.DataFrame(rows).write_parquet(args.out / "scans.parquet")
    else:
        import itertools
        from concurrent.futures import ProcessPoolExecutor

        import polars as pl

        scans = pl.read_parquet(args.out / "scans.parquet")
        dirs = [args.out / fp / "scans" / s for s, fp in scans.select("scan", "fingerprint").iter_rows()]
        jobs = [(a, b) for a, b in itertools.permutations(dirs, 2)]
        done = {}
        with ProcessPoolExecutor(args.workers) as pool:
            for (a, b), row in zip(jobs, pool.map(register_pair, *zip(*jobs))):
                done[(a.name, b.name)] = row
                print(json.dumps({k: row[k] for k in ("a", "b", "icp_fitness", "tilt_deg", "check_fitness_2cm")}), flush=True)
        rows = []
        for (a, b), row in done.items():
            if a < b:
                ang, dist = reciprocal_error(np.array(row["T_b_a"]), np.array(done[(b, a)]["T_b_a"]))
                row |= {"recip_deg": ang, "recip_m": dist}
                row["accepted"] = accept(row)
                rows.append(row)
        pl.DataFrame([{k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()} for r in rows]
                     ).write_parquet(args.out / "pairs.parquet")
        print(f"{sum(r['accepted'] for r in rows)} of {len(rows)} pairs accepted")


if __name__ == "__main__":
    main()
