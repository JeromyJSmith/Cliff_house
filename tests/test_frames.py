import subprocess

import numpy as np
import polars as pl
import pytest

from cliff_house.frames import (Params, Source, Stream, extract, fingerprint, hlg_inverse_oetf, hlg_to_sdr,
                                 probe)


@pytest.fixture
def two_stream_video(tmp_path):
    # Stream 0 is sharp only on frames n % 4 == 3; stream 1 on n % 4 in {2, 3}. The only candidate in each window of
    # 4 that is sharp on BOTH streams is n % 4 == 3, so rig-consistent selection must pick exactly those.
    path = tmp_path / "rig.mp4"
    blur = "boxblur=8:enable='{}'"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=8:duration=2",
        "-filter_complex",
        f"[0]split[a][b];[a]{blur.format('lt(mod(n,4),3)')}[s0];[b]{blur.format('lt(mod(n,4),2)')}[s1]",
        "-map", "[s0]", "-map", "[s1]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return Source(path=path, sha256="0" * 64, streams=(Stream(0, "lens0"), Stream(1, "lens1")),
                  transfer="sdr", width=320, height=240)


def test_selection_keeps_timestamps_sharp_on_every_stream(two_stream_video, tmp_path):
    params = Params(candidate_fps=8, target_fps=2)
    table = extract(two_stream_video, params, tmp_path / "out")

    assert table.height == 2 * 4  # 2 s × 2 frames/s, for each of two streams
    per_stream = table.group_by("camera").agg(pl.col("candidate").sort())
    assert {row["camera"]: row["candidate"] for row in per_stream.to_dicts()} == {
        "lens0": [3, 7, 11, 15], "lens1": [3, 7, 11, 15]}
    assert table["t_ms"].unique().sort().to_list() == [375, 875, 1375, 1875]
    for f in table["file"]:
        assert (tmp_path / "out" / f).stat().st_size > 0
    assert pl.read_parquet(tmp_path / "out" / "frames.parquet").equals(table)


def test_fingerprint_changes_with_source_and_parameters():
    base = fingerprint("0" * 64, Params())
    assert fingerprint("0" * 64, Params()) == base
    assert fingerprint("0" * 64, Params(target_fps=2)) != base
    assert fingerprint("1" * 64, Params()) != base


def test_hlg_inverse_oetf_matches_bt2100():
    e = np.array([0.0, 0.5, 1.0])
    assert hlg_inverse_oetf(e) == pytest.approx([0.0, 1 / 12, 1.0], abs=1e-6)
    left, right = hlg_inverse_oetf(np.array([0.5 - 1e-6, 0.5 + 1e-6]))
    assert right - left == pytest.approx(0.0, abs=1e-5)  # continuous at the knee
    ramp = hlg_inverse_oetf(np.linspace(0, 1, 101))
    assert np.all(np.diff(ramp) > 0)


def test_hlg_to_sdr_is_bounded_and_monotonic_on_grey():
    grey = np.repeat(np.linspace(0, 65535, 64, dtype=np.uint16)[:, None, None], 3, axis=2)
    out = hlg_to_sdr(grey)
    assert out.dtype == np.uint8 and out[0, 0, 0] == 0
    assert np.all(np.diff(out[:, 0, 0].astype(int)) >= 0)
    assert np.allclose(out[:, 0, 0], out[:, 0, 1], atol=2)  # neutral stays neutral through the primaries matrix


def test_probe_describes_a_two_lens_file(two_stream_video):
    described = probe(two_stream_video.path, two_stream_video.sha256)
    assert described == two_stream_video
