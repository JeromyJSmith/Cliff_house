"""Contract: remux copies each lens stream into its own MP4 without changing a single compressed packet."""
import json
import subprocess
from pathlib import Path

from cliff_house import remux

REPO = Path(__file__).resolve().parents[1]
CLIP_032 = REPO / "input" / "VID_20261109_174428_032.insv"


def _two_stream_clip(path: Path) -> None:
    """A 30-frame, two-video-stream file shaped like an .insv (two H.264 streams of the same size and rate)."""
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30000/1001",
                    "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=30000/1001", "-map", "0:v", "-map", "1:v",
                    "-frames:v", "30", "-c:v", "libx264", "-g", "10", str(path)], check=True)


def test_remux_is_packet_identical(tmp_path):
    src = tmp_path / "VID_test.mp4"
    _two_stream_clip(src)
    record = remux.remux_clip(src, tmp_path / "out")

    assert [c["cam"] for c in record["cams"]] == ["cam0", "cam1"]
    for i, cam in enumerate(record["cams"]):
        assert cam["packets"] == 30
        assert (cam["packets"], cam["packet_md5"]) == remux.stream_hash(src, i)
        out = tmp_path / "out" / record["fingerprint"] / src.stem / f"{cam['cam']}.mp4"
        assert [s["width"] for s in remux.video_streams(out)] == [64]  # one stream per output
    # The two lenses are different pictures, so their packet hashes must differ.
    assert record["cams"][0]["packet_md5"] != record["cams"][1]["packet_md5"]
    # Rerun is a no-op that returns the stored record.
    assert remux.remux_clip(src, tmp_path / "out", record["source_sha256"]) == record


def test_real_clip_remux(tmp_path):
    assert CLIP_032.stat().st_size > 100_000_000, "clip 032 is a Git LFS pointer: run `git lfs pull`"
    record = remux.remux_clip(CLIP_032, tmp_path)
    streams = remux.video_streams(CLIP_032)
    assert len(record["cams"]) == 2
    for cam, stream in zip(record["cams"], streams):
        assert (cam["width"], cam["height"], cam["fps"]) == (3840, 3840, "30000/1001")
        assert cam["packets"] == int(stream["nb_frames"])
    stored = json.loads((tmp_path / record["fingerprint"] / CLIP_032.stem / "remux.json").read_text())
    assert stored == record
