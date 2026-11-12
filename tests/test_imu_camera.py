"""Contract: lens geometry from the IMU — blur, gravity and the gyro↔lens fit — is numerically right."""
import json
import math
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from cliff_house import imu_camera, insv_telemetry

REPO = Path(__file__).resolve().parents[1]
CLIP_032 = REPO / "input" / "VID_20261109_174428_032.insv"


def _imu(t_s, gyro, accel):
    gyro, accel = np.broadcast_to(gyro, (len(t_s), 3)), np.broadcast_to(accel, (len(t_s), 3))
    return pl.DataFrame({"t_ms": t_s * 1000, **{f"gyro_{a}": gyro[:, i] for i, a in enumerate("xyz")},
                         **{f"accl_{a}": accel[:, i] for i, a in enumerate("xyz")}})


def test_motion_blur_hand_math():
    t = np.arange(0, 1, 0.001)
    imu = _imu(t, [0.0, 90.0, 0.0], [0.0, 0.0, 0.0])
    exposure = pl.DataFrame({"t_s": [0.0, 0.5], "exposure_s": [0.01, 0.002]})
    m = imu_camera.motion_table(imu, exposure, {"lens0": 1000.0, "lens1": 500.0})
    row = m.filter((pl.col("t_ms") - 250).abs() < 1e-6).row(0, named=True)
    # 90 deg/s = π/2 rad/s for 0.01 s at 1000 px/rad → 15.708 px; lens1 at 500 px/rad → half that.
    assert row["omega_dps"] == pytest.approx(90.0)
    assert row["blur_px_lens0"] == pytest.approx(math.pi / 2 * 0.01 * 1000)
    assert row["blur_px_lens1"] == pytest.approx(math.pi / 2 * 0.01 * 500)
    assert row["weight_lens0"] == pytest.approx(math.exp(-row["blur_px_lens0"] / 8))
    late = m.filter((pl.col("t_ms") - 750).abs() < 1e-6).row(0, named=True)
    assert late["exposure_s"] == 0.002 and late["blur_px_lens0"] == pytest.approx(math.pi / 2 * 0.002 * 1000)


def test_gravity_points_down_each_lens():
    t = np.arange(0, 3, 0.001)
    # At rest the accelerometer reads +1 g along the IMU axis that points up; on the A1 that is +x.
    imu = _imu(t, [0.0, 0.0, 0.0], [imu_camera.STANDARD_GRAVITY, 0.0, 0.0])
    g = imu_camera.gravity_table(imu, imu_camera.A1_CAM_FROM_IMU, np.array([500.0, 1500.0]))
    assert g.select("g_lens0_x", "g_lens0_y", "g_lens0_z").rows() == [(0.0, 0.0, 1.0)] * 2   # lens0 looks down
    assert g.select("g_lens1_x", "g_lens1_y", "g_lens1_z").rows() == [(0.0, 0.0, -1.0)] * 2  # lens1 looks up
    assert g["quasi_static"].all() and g["accel_norm_mps2"].to_list() == pytest.approx([imu_camera.STANDARD_GRAVITY] * 2)


def test_a1_lenses_are_back_to_back():
    rel = imu_camera.A1_CAM_FROM_IMU["lens0"] @ imu_camera.A1_CAM_FROM_IMU["lens1"].T
    assert rel.tolist() == [[-1, 0, 0], [0, 1, 0], [0, 0, -1]]  # 180° about +y
    for m in imu_camera.A1_CAM_FROM_IMU.values():
        assert np.linalg.det(m) == pytest.approx(1.0)


def test_fit_sync_recovers_rotation_and_lag():
    rng = np.random.default_rng(7)
    t = np.arange(0, 20, 0.001)
    g = np.stack([np.convolve(rng.normal(0, 400, len(t)), np.ones(200) / 200, "same") for _ in range(3)], 1)
    imu = _imu(t, g, [0.0, 0.0, 0.0])
    tv = (np.arange(500) + 0.5) / (30000 / 1001) + 1.0
    lag = -0.004
    R = imu_camera.A1_CAM_FROM_IMU["lens1"]
    cam = np.stack([np.interp(tv + lag, t, g[:, k]) for k in range(3)], 1) @ R.T
    fit = imu_camera.fit_sync(cam, tv, imu)
    assert fit["cam_from_imu"] == R.astype(int).tolist()
    assert fit["lag_ms"] == pytest.approx(-4.0, abs=1.0)
    assert min(fit["r_xyz"]) > 0.99


def test_real_clip_rig_motion_gravity(tmp_path):
    assert CLIP_032.stat().st_size > 100_000_000, "clip 032 is a Git LFS pointer: run `git lfs pull`"
    row = insv_telemetry.process(CLIP_032, tmp_path)
    d = tmp_path / row["fingerprint"] / CLIP_032.stem
    rig = json.loads((d / "rig.json").read_text())
    assert [rig["lenses"][k]["stream"] for k in ("lens0", "lens1")] == [0, 1]
    assert 1000 < rig["lenses"]["lens0"]["px_per_rad"] < 1200
    assert rig["lens0_from_lens1"]["rotation_deg"] == pytest.approx(180, abs=2)
    assert rig["lens0_from_lens1"]["baseline_m"] == pytest.approx(0.0713, abs=0.002)
    motion = pl.read_parquet(d / "motion.parquet")
    assert motion.height == pl.read_parquet(d / "imu.parquet").height
    assert motion["weight_lens0"].is_between(0, 1).all()
    gravity = pl.read_parquet(d / "gravity.parquet")
    assert gravity.height == rig["video"]["frames"]
    for lens in ("lens0", "lens1"):
        norm = np.sqrt(sum(gravity[f"g_{lens}_{a}"].to_numpy() ** 2 for a in "xyz"))
        assert norm == pytest.approx(np.ones(gravity.height))
