"""Contract: the telemetry stage turns an Antigravity A1 .insv trailer into correct GPS/IMU tables and summaries."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from cliff_house import insv_telemetry as tel

REPO = Path(__file__).resolve().parents[1]
CLIP_032 = REPO / "input" / "VID_20261109_174428_032.insv"
METRES_PER_DEGREE = 2 * math.pi * tel.EARTH_RADIUS_M / 360  # along a meridian


def _fix(t, lat, lon, speed, acquired=True):
    return {"is_acquired": acquired, "unix_timestamp": t, "lat": lat, "lon": lon,
            "speed": speed, "track": 0.0, "altitude": 1771.0}


def test_haversine_matches_meridian_arc():
    d = tel.haversine_m(np.array([39.0, 40.0, 40.0]), np.array([-105.0, -105.0, -105.0]))
    assert d[0] == pytest.approx(METRES_PER_DEGREE, rel=1e-12)
    assert d[1] == 0.0


def test_gps_summary_from_parser_blocks():
    # Shape of telemetry_parser.Parser.telemetry(): a list of {group: {tag: value}} blocks; GPS split across two.
    blocks = [
        {"GPS": {"Data": [_fix(1_794_342_200.0, 39.654, -105.19, 10.0), _fix(1_794_342_195.0, 0.0, 0.0, 0.0)]}},
        {"GPS": {"Data": [_fix(1_794_342_210.0, 39.655, -105.19, 12.0),
                          _fix(1_794_342_205.0, 39.6545, -105.19, 9.0, acquired=False)]}},
    ]
    gps = tel.gps_frame(blocks)
    assert gps.height == 4
    assert gps["time_utc"].is_sorted()
    assert str(gps["time_utc"].dtype) == "Datetime(time_unit='us', time_zone='UTC')"

    s = tel.summarize(gps, tel.imu_frame([]))
    # The (0, 0) fix and the unacquired fix are excluded; 0.001 deg of latitude in 10 s remains.
    assert s["gps_fixes_acquired"] == 2
    assert s["gps_span_s"] == pytest.approx(10.0)
    assert s["path_length_m"] == pytest.approx(0.001 * METRES_PER_DEGREE, rel=1e-6)
    assert s["implied_mean_speed_mps"] == pytest.approx(0.001 * METRES_PER_DEGREE / 10, rel=1e-6)
    assert s["reported_mean_speed_mps"] == pytest.approx(11.0)
    assert s["gps_first_utc"] == "2026-11-10T20:23:20+00:00"


def test_imu_rate_and_gravity():
    samples = [{"timestamp_ms": float(i), "gyro": [0.0, 0.0, 1.0], "accl": [0.0, 0.0, 9.80665]} for i in range(1001)]
    s = tel.summarize(tel.gps_frame([]), tel.imu_frame(samples))
    assert s["imu_samples"] == 1001
    assert s["imu_rate_hz"] == pytest.approx(1000.0)
    assert s["accel_norm_median_mps2"] == pytest.approx(9.80665)
    assert s["gps_fixes"] == 0 and "path_length_m" not in s


def test_fingerprint_tracks_source_bytes():
    a, b = tel.fingerprint("a" * 64), tel.fingerprint("b" * 64)
    assert a == tel.fingerprint("a" * 64) and a != b and len(a) == 16


def test_real_a1_clip_decodes(tmp_path):
    assert CLIP_032.stat().st_size > 100_000_000, "clip 032 is a Git LFS pointer: run `git lfs pull`"
    row = tel.process(CLIP_032, tmp_path)
    clip_dir = tmp_path / row["fingerprint"] / CLIP_032.stem

    assert row["model"] == "Antigravity A1"
    assert row["serial_number"] and row["firmware"]
    # Gyro/accel stream is ~1 kHz; the parser normalizes accel to m/s^2, so a near-still drone reads ~1 g.
    assert 900 < row["imu_rate_hz"] < 1100
    assert 8.0 < row["accel_norm_median_mps2"] < 11.6
    lens = json.loads((clip_dir / "lens.json").read_text())
    cameras = lens["rig"]["projection"]["kind"]["Rig"]["cameras"]
    assert len(cameras) == 2  # one calibration per lens
    assert lens["data"]["camera_model"] == "Antigravity A1"
    # A rerun with the same bytes is a no-op that returns the stored summary.
    again = tel.process(CLIP_032, tmp_path, source_sha256=row["source_sha256"])
    assert again == json.loads((clip_dir / "summary.json").read_text())
