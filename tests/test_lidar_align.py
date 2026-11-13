"""Contract: pairwise LiDAR registration recovers a known 4-DOF transform, and the capped driver is reproducible.

All data here is synthetic (a gravity-aligned L-shaped room with furniture-like boxes and colour), so the tests are
safe for a public repo and need no project files."""
import json
import math

import numpy as np
import pytest

from cliff_house import lidar_align as la
from cliff_house import lidar_prep as lp


def _yaw_T(deg: float, t) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = lp.yaw_matrix(math.radians(deg))
    T[:3, 3] = t
    return T


def _room(rng: np.random.Generator, n: int = 160_000) -> tuple[np.ndarray, np.ndarray]:
    """Points on an asymmetric L-shaped room (+y up, metres) with boxes; colour varies by surface."""
    pts, cols = [], []

    def plane(origin, u, v, count, colour):
        a, b = rng.random((count, 1)), rng.random((count, 1))
        pts.append(origin + a * u + b * v)
        cols.append(np.tile(colour, (count, 1)) + rng.normal(0, 0.03, (count, 3)))

    k = n // 16
    plane(np.array([0, 0, 0.]), np.array([6, 0, 0.]), np.array([0, 0, 3.]), 2 * k, [0.55, 0.45, 0.35])  # floor
    plane(np.array([0, 0, 3.]), np.array([2.5, 0, 0.]), np.array([0, 0, 2.5]), k, [0.55, 0.45, 0.35])  # L leg floor
    for o, u, c in [((0, 0, 0), (6, 0, 0), [0.8, 0.8, 0.75]), ((6, 0, 0), (0, 0, 3), [0.7, 0.75, 0.8]),
                    ((6, 0, 3), (-3.5, 0, 0), [0.8, 0.7, 0.6]), ((2.5, 0, 3), (0, 0, 2.5), [0.6, 0.8, 0.6]),
                    ((2.5, 0, 5.5), (-2.5, 0, 0), [0.75, 0.6, 0.8]), ((0, 0, 5.5), (0, 0, -5.5), [0.6, 0.6, 0.9])]:
        plane(np.array(o, float), np.array(u, float), np.array([0, 2.5, 0.]), 2 * k, c)
    for (x, z, w, h, d), c in [((1.0, 0.6, 0.8, 0.9, 0.5), [0.9, 0.2, 0.2]), ((4.2, 1.8, 1.2, 0.5, 0.7), [0.2, 0.3, 0.9]),
                               ((0.6, 4.2, 0.5, 1.6, 0.4), [0.2, 0.8, 0.3]), ((3.5, 0.3, 0.4, 0.4, 0.4), [0.9, 0.8, 0.1])]:
        o = np.array([x, 0, z])
        W, H, D = np.array([w, 0, 0.]), np.array([0, h, 0.]), np.array([0, 0, d])
        for off, u, v in [(0, W, H), (D, W, H), (0, D, H), (W, D, H), (H, W, D)]:  # 4 sides and the top
            plane(o + off, u, v, k // 5, c)
    p = np.concatenate(pts)
    return p, np.clip(np.concatenate(cols), 0, 1)


def _write_ply(path, xyz, rgb):
    v = np.empty(len(xyz), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    v["x"], v["y"], v["z"] = xyz.T
    v["red"], v["green"], v["blue"] = (rgb * 255).astype(np.uint8).T
    header = (f"ply\nformat binary_little_endian 1.0\nelement vertex {len(v)}\nproperty float x\nproperty float y\n"
              "property float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    path.write_bytes(header.encode() + v.tobytes())


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    """Two scans of the same room: B is A moved by a known yaw + translation (B ← A), each with its own noise and
    partial view. Returns (prep_root, T_b_a_true)."""
    rng = np.random.default_rng(7)
    root = tmp_path_factory.mktemp("prep")
    room, colour = _room(rng)
    T_true = _yaw_T(37.0, [1.3, 0.0, -0.8])
    keep_a = room[:, 2] < 4.6   # scan A misses the far end of the L leg
    keep_b = room[:, 0] > 0.4   # scan B misses a strip along x = 0
    a = room[keep_a] + rng.normal(0, 0.004, (keep_a.sum(), 3))
    b = room[keep_b] @ T_true[:3, :3].T + T_true[:3, 3] + rng.normal(0, 0.004, (keep_b.sum(), 3))
    rows = []
    for name, xyz, rgb in (("SCAN_A", a, colour[keep_a]), ("SCAN_B", b, colour[keep_b])):
        ply = root / f"{name}.ply"
        _write_ply(ply, xyz, rgb)
        sha = lp.sha256_file(ply)
        fp = lp.fingerprint(sha)
        stats = lp.prepare_scan(ply, root / fp / "scans" / name)
        rows.append({"scan": name, "fingerprint": fp, "source_sha256": sha, "points_5cm": stats["points_5cm"]})
    import polars as pl

    pl.DataFrame(rows).write_parquet(root / "scans.parquet")
    return root, T_true


def test_yaw_matrix_and_tilt_yaw_round_trip():
    for deg in (-170.0, -12.5, 0.0, 33.0, 179.0):
        tilt, yaw = lp.tilt_and_yaw(_yaw_T(deg, [0, 0, 0]))
        assert tilt == pytest.approx(0.0, abs=1e-6)
        assert yaw == pytest.approx(deg, abs=1e-9)
    tilted = _yaw_T(10, [0, 0, 0])
    c, s = math.cos(math.radians(2)), math.sin(math.radians(2))
    tilted[:3, :3] = np.array([[1, 0, 0], [0, c, -s], [0, s, c]]) @ tilted[:3, :3]
    assert lp.tilt_and_yaw(tilted)[0] == pytest.approx(2.0, abs=1e-6)


def test_ransac_4dof_recovers_transform_with_60_percent_outliers():
    rng = np.random.default_rng(1)
    src = rng.uniform(-5, 5, (2000, 3))
    T = _yaw_T(-71.0, [0.4, -0.2, 2.5])
    dst = src @ T[:3, :3].T + T[:3, 3] + rng.normal(0, 0.005, src.shape)
    bad = rng.random(len(src)) < 0.6
    dst[bad] = rng.uniform(-5, 5, (bad.sum(), 3))
    est, inl = lp.ransac_4dof(src, dst, 0.05, 5000)
    assert np.abs(est[:3, 3] - T[:3, 3]).max() < 0.03
    assert abs(lp.tilt_and_yaw(est)[1] - (-71.0)) < 0.5
    assert inl == pytest.approx(0.4, abs=0.05)


def test_feature_matches_are_symmetric():
    rng = np.random.default_rng(3)
    fa, fb = rng.random((500, 33)).astype(np.float32), rng.random((450, 33)).astype(np.float32)
    ia, ib = lp.feature_matches(fa, fb)
    ja, jb = lp.feature_matches(fb, fa)
    assert sorted(zip(ia, ib)) == sorted(zip(jb, ja))
    assert len(ia) > 0


def test_tiled_nearest_neighbours_equal_kdtree_on_fpfh_like_features():
    # FPFH-like: three 11-bin histograms each summing to 200, sizes not multiples of the tiles.
    rng = np.random.default_rng(11)

    def feats(n):
        h = rng.dirichlet(np.full(11, 0.3), (n, 3)) * 200
        return h.reshape(n, 33).astype(np.float32)
    fa, fb = feats(3001), feats(2503)
    from scipy.spatial import cKDTree

    ab, ba = lp.nearest_tiled(fa, fb, tile_a=256, tile_b=1000)
    assert np.array_equal(ab, cKDTree(fb).query(fa, k=1)[1])
    assert np.array_equal(ba, cKDTree(fa).query(fb, k=1)[1])
    tiled = lp.feature_matches(fa, fb)
    kd = lp.feature_matches(fa, fb, method="kdtree")
    assert np.array_equal(tiled[0], kd[0]) and np.array_equal(tiled[1], kd[1]) and len(kd[0]) > 100


def test_reciprocal_error_is_zero_for_inverse_pair():
    T = _yaw_T(25, [1, 0.5, -2])
    assert lp.reciprocal_error(T, np.linalg.inv(T)) == pytest.approx((0.0, 0.0), abs=1e-6)
    deg, m = lp.reciprocal_error(T, np.linalg.inv(_yaw_T(27, [1, 0.5, -2])))
    assert deg == pytest.approx(2.0, abs=1e-6) and m > 0


def test_register_pair_recovers_known_transform(prepared):
    root, T_true = prepared
    dirs = la.scan_dirs(root)
    row = lp.register_pair(dirs["SCAN_A"], dirs["SCAN_B"], workers=1)
    T = np.array(row["T_b_a"])
    err = np.linalg.inv(T_true) @ T
    rot_err = math.degrees(math.acos(np.clip((np.trace(err[:3, :3]) - 1) / 2, -1, 1)))
    assert rot_err < 0.5, row
    assert np.linalg.norm(T[:3, 3] - T_true[:3, 3]) < 0.03, row
    assert row["tilt_deg"] < 0.5
    assert row["icp_rmse_m"] < 0.03 and row["icp_fitness"] > 0.5
    assert row["check_fitness_2cm"] > 0.5


def test_driver_runs_both_directions_and_resumes_without_rewriting(prepared, tmp_path):
    root, T_true = prepared
    out = la.align(root, tmp_path, workers=2, max_load=1e9, poll_s=0.5, log=lambda m: None)
    rows = {(r["a"], r["b"]): r for r in json.loads(json.dumps(
        [json.loads(p.read_text()) for p in sorted((out / "pairs").glob("*.json"))]))}
    assert set(rows) == {("SCAN_A", "SCAN_B"), ("SCAN_B", "SCAN_A")}
    T_ab, T_ba = np.array(rows[("SCAN_A", "SCAN_B")]["T_b_a"]), np.array(rows[("SCAN_B", "SCAN_A")]["T_b_a"])
    assert np.linalg.norm(T_ab[:3, 3] - T_true[:3, 3]) < 0.03
    deg, m = lp.reciprocal_error(T_ab, T_ba)
    assert deg < 0.5 and m < 0.03
    man = json.loads((out / "manifest.json").read_text())
    assert man["fingerprint"] == out.name and man["status"].startswith("hypothesis")
    assert set(man["inputs"]["scans"]) == {"SCAN_A", "SCAN_B"}
    assert man["machine"]["thread_env"]["OMP_NUM_THREADS"] == "1"
    import polars as pl

    df = pl.read_parquet(out / "pairs.parquet")
    assert df.height == 2 and df["accepted"].all() and (df["status"] == "hypothesis").all()
    # Same inputs, code and parameters → same fingerprint; nothing re-registered, existing results untouched.
    mtimes = {p: p.stat().st_mtime_ns for p in (out / "pairs").glob("*.json")}
    msgs = []
    out2 = la.align(root, tmp_path, workers=2, max_load=1e9, poll_s=0.5, log=msgs.append)
    assert out2 == out
    assert any("0 to run" in m for m in msgs)
    assert {p: p.stat().st_mtime_ns for p in (out / "pairs").glob("*.json")} == mtimes


def test_fingerprint_changes_with_inputs_params_and_code():
    base = dict(inputs={"s": {"f": "aa"}}, params={"p": 1}, code={"c": "x"}, versions={"v": "1"})
    fp = la.fingerprint(**base)
    assert fp == la.fingerprint(**base)
    for k, v in (("inputs", {"s": {"f": "ab"}}), ("params", {"p": 2}), ("code", {"c": "y"}), ("versions", {"v": "2"})):
        assert la.fingerprint(**(base | {k: v})) != fp
