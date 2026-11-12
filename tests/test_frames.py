"""Contract: the frames stage keeps the lenses in sync, times every frame exactly and predicts blur from the gyro."""
import math
import os
from fractions import Fraction
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from cliff_house import frames, insv_telemetry

REPO = Path(__file__).resolve().parents[1]
CLIP_032 = REPO / "input" / "VID_20261109_174428_032.insv"
FPS = Fraction(30000, 1001)


def _lens(focal=3000.0, scale=0.5, xi=0.5, readout_ms=20.0):
    cam = {"intrinsics": {"model": {"Mei": {"xi": xi}}, "focal": [focal, focal]},
           "calib_to_picture": {"a": [[scale, 0.0], [0.0, scale]]}}
    return {"data": {"frame_readout_time": readout_ms}, "rig": {"projection": {"kind": {"Rig": {"cameras": [cam, cam]}}}}}


def _imu(dps_z: float, seconds: float = 2.0) -> pl.DataFrame:
    t = np.arange(0, seconds * 1000)  # 1 kHz
    z = np.full_like(t, dps_z, dtype=float)
    zeros = np.zeros_like(z)
    return pl.DataFrame({"t_ms": t.astype(float), "gyro_x": zeros, "gyro_y": zeros, "gyro_z": z,
                         "accl_x": zeros, "accl_y": zeros, "accl_z": zeros + 9.80665})


def test_pixels_per_radian_is_mei_axis_scale():
    # Near the axis the unified model maps angle θ to f·θ/(1+ξ): 3000 · 0.5 / 1.5 = 1000 px per radian.
    assert frames.pixels_per_radian(_lens()) == {"cam0": pytest.approx(1000.0), "cam1": pytest.approx(1000.0)}


def test_gyro_blur_and_weight(tmp_path):
    for cam in ("cam0", "cam1"):
        (tmp_path / cam).mkdir()
        for i in (0, 15, 30):
            (tmp_path / cam / f"{i:05d}.jpg").write_bytes(b"")
    report = pl.DataFrame({"frame": [0, 15, 30], "edge_width_px": [7.0, 8.0, 9.0], "blur_px": [0.0, 1.0, 2.0]})
    exposure = pl.DataFrame({"t_s": [0.0, 0.5], "exposure_s": [0.01, 0.004]})
    table = frames.frame_table("clipA", "a" * 64, tmp_path, FPS, 0.0, report, _imu(90.0), exposure, _lens(), 8.0)

    assert table.height == 6 and not table.select("cam", "frame_index").is_duplicated().any()
    cam0 = table.filter(pl.col("cam") == "cam0")
    # Frame n is at n·1001/30000 s.
    assert cam0["t_s"].to_list() == pytest.approx([0.0, 15 * 1001 / 30000, 30 * 1001 / 30000])
    # Exposure is the last record at or before the frame: frame 0 → 0.01 s; frames 15 (t = 0.5005 s) and 30 → 0.004 s.
    assert cam0["exposure_s"].to_list() == pytest.approx([0.01, 0.004, 0.004])
    # 90 deg/s = π/2 rad/s; blur = π/2 · exposure · 1000 px/rad; weight = exp(-blur / 8).
    expected = [math.pi / 2 * e * 1000 for e in (0.01, 0.004, 0.004)]
    assert cam0["gyro_dps"].to_list() == pytest.approx([90.0] * 3)
    assert cam0["predicted_blur_px"].to_list() == pytest.approx(expected)
    assert cam0["weight"].to_list() == pytest.approx([math.exp(-b / 8) for b in expected])
    assert cam0["rs_skew_px"].to_list() == pytest.approx([math.pi / 2 * 0.020 * 1000] * 3)
    assert cam0["blur_px"].to_list() == [0.0, 1.0, 2.0]
    # A still camera predicts no blur and full weight.
    still = frames.frame_table("clipA", "a" * 64, tmp_path, FPS, 0.0, report, _imu(0.0), exposure, _lens(), 8.0)
    assert still["predicted_blur_px"].max() == 0.0 and still["weight"].min() == 1.0


def test_unsynced_lenses_are_refused(tmp_path):
    for cam, stems in (("cam0", (0, 15)), ("cam1", (0, 16))):
        (tmp_path / cam).mkdir()
        for i in stems:
            (tmp_path / cam / f"{i:05d}.jpg").write_bytes(b"")
    report = pl.DataFrame({"frame": [0, 15], "edge_width_px": [7.0, 8.0], "blur_px": [0.0, 1.0]})
    exposure = pl.DataFrame({"t_s": [0.0], "exposure_s": [0.01]})
    with pytest.raises(RuntimeError, match="not in sync"):
        frames.frame_table("clipA", "a" * 64, tmp_path, FPS, 0.0, report, _imu(0.0), exposure, _lens(), 8.0)


def test_real_clip_frames(tmp_path):
    spirula = os.environ.get("SPIRULA", frames.DEFAULT_SPIRULA)
    assert Path(spirula).exists(), f"Spirula CLI not found at {spirula}: install Spirula Studio or set SPIRULA"
    assert CLIP_032.stat().st_size > 100_000_000, "clip 032 is a Git LFS pointer: run `git lfs pull`"
    tel = insv_telemetry.process(CLIP_032, tmp_path / "telemetry")
    table = frames.extract_clip(CLIP_032, tmp_path / "telemetry" / tel["fingerprint"] / CLIP_032.stem,
                                tel["fingerprint"], tmp_path / "frames", spirula, tel["source_sha256"])
    cam0, cam1 = (table.filter(pl.col("cam") == c) for c in ("cam0", "cam1"))
    assert cam0.height > 0 and cam0["frame_index"].to_list() == cam1["frame_index"].to_list()
    for image in table["image"]:
        assert (tmp_path / "frames" / image).stat().st_size > 100_000
    # Spirula measured every frame it wrote (it may keep up to two blurred frames in a row, so no upper bound here).
    assert table["blur_px"].null_count() == 0 and table["blur_px"].min() >= 0
    # This A1's axis scale is about 1,100 px/rad, the focal the spec records from the clip 041 solve.
    assert 1000 < table["px_per_rad"].min() <= table["px_per_rad"].max() < 1200
    assert table["weight"].is_between(0, 1).all()
