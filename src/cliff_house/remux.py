"""Stage: remux — copy each lens stream of an `.insv` into its own `.mp4`, bit for bit.

Resolve and macOS AVFoundation may not open a raw `.insv` (two H.264 lens streams + a subtitle track + the Insta360
trailer). `ffmpeg -c copy` moves each lens's compressed packets into a standard MP4 without decoding, so the
pictures are identical to the source. The stage proves that per stream: same packet count and the same
per-packet MD5 sequence (`-f streamhash`) in source and output.

Outputs per clip under `stages/remux/<fingerprint>/<clip>/`: `cam0.mp4`, `cam1.mp4` (lens = stream order, the
same `cam0`/`cam1` names Spirula uses) and `remux.json` (commands, packet counts, hashes). The MP4s are fully
reproducible from the dataset with the recorded commands, so by default only `remux.json` and the stage manifest
go to the bucket; `--upload-video` sends the MP4s too.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import polars as pl

from cliff_house.insv_telemetry import sha256_file

STAGE = "remux"
STAGE_VERSION = 1


def ffmpeg_version(ffmpeg: str = "ffmpeg") -> str:
    return subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, check=True).stdout.split("\n")[0]


def fingerprint(source_sha256: str, ffmpeg: str = "ffmpeg") -> str:
    key = json.dumps({"stage": STAGE, "stage_version": STAGE_VERSION, "ffmpeg": ffmpeg_version(ffmpeg),
                      "source_sha256": source_sha256}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def video_streams(path: Path, ffprobe: str = "ffprobe") -> list[dict]:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v", "-show_entries",
                          "stream=index,codec_name,width,height,r_frame_rate,start_time,duration,nb_frames",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"]


def stream_hash(path: Path, video_index: int, ffmpeg: str = "ffmpeg") -> tuple[int, str]:
    """(packet count, MD5 over the per-packet MD5 list) of one video stream, from compressed packets."""
    out = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", f"0:v:{video_index}",
                          "-c", "copy", "-f", "framemd5", "-"], capture_output=True, text=True, check=True).stdout
    rows = [line.rsplit(",", 1)[-1].strip() for line in out.splitlines() if line and not line.startswith("#")]
    return len(rows), hashlib.md5("\n".join(rows).encode()).hexdigest()


def remux_clip(path: Path, out_root: Path, source_sha256: str | None = None,
               ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> dict:
    sha = source_sha256 or sha256_file(path)
    fp = fingerprint(sha, ffmpeg)
    clip_dir = out_root / fp / path.stem
    record_path = clip_dir / "remux.json"
    if record_path.exists():  # done for these bytes and this code; never overwritten
        return json.loads(record_path.read_text())
    clip_dir.mkdir(parents=True, exist_ok=True)
    cams = []
    for i, stream in enumerate(video_streams(path, ffprobe)):
        out = clip_dir / f"cam{i}.mp4"
        cmd = [ffmpeg, "-nostdin", "-v", "error", "-n", "-i", str(path), "-map", f"0:v:{i}", "-c", "copy",
               "-map_metadata", "0", "-movflags", "+faststart", str(out)]
        subprocess.run(cmd, check=True)
        src_packets, src_hash = stream_hash(path, i, ffmpeg)
        out_packets, out_hash = stream_hash(out, 0, ffmpeg)
        if (src_packets, src_hash) != (out_packets, out_hash):
            raise RuntimeError(f"{path.name} stream {i}: remux changed the packets "
                               f"({src_packets}/{src_hash} -> {out_packets}/{out_hash})")
        cams.append({"cam": f"cam{i}", "source_stream": stream["index"], "codec": stream["codec_name"],
                     "width": stream["width"], "height": stream["height"], "fps": stream["r_frame_rate"],
                     "start_time": float(stream.get("start_time") or 0.0), "packets": out_packets,
                     "packet_md5": out_hash, "bytes": out.stat().st_size, "sha256": sha256_file(out),
                     "command": [Path(cmd[0]).name, *cmd[1:-1], out.name]})
    record = {"clip": path.stem, "source_sha256": sha, "fingerprint": fp, "stage_version": STAGE_VERSION,
              "ffmpeg": ffmpeg_version(ffmpeg), "cams": cams}
    record_path.write_text(json.dumps(record, indent=2))
    return record


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("clips", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="local stage root (mirrors stages/remux/)")
    ap.add_argument("--manifest", type=Path, help="sources.parquet: take SHA-256 from it instead of hashing")
    ap.add_argument("--bucket", help="HF bucket id; upload remux.json files and the stage manifest")
    ap.add_argument("--upload-video", action="store_true", help="also upload the MP4s")
    args = ap.parse_args(argv)

    known = {}
    if args.manifest:
        known = {Path(p).name: s for p, s in pl.read_parquet(args.manifest).select("path", "sha256").iter_rows()}
    records = [remux_clip(c, args.out, known.get(c.name)) for c in sorted(args.clips)]
    rows = [{"clip": r["clip"], "fingerprint": r["fingerprint"], "source_sha256": r["source_sha256"],
             "cam": c["cam"], "packets": c["packets"], "packet_md5": c["packet_md5"], "bytes": c["bytes"],
             "sha256": c["sha256"]} for r in records for c in r["cams"]]
    manifest = pl.DataFrame(rows)
    manifest.write_parquet(args.out / "manifest.parquet")
    print(manifest.select("clip", "cam", "packets", "bytes"))
    if args.bucket:
        from huggingface_hub import batch_bucket_files

        files = [(str(p), f"stages/{STAGE}/{p.relative_to(args.out).as_posix()}") for p in sorted(args.out.rglob("*"))
                 if p.is_file() and (args.upload_video or p.suffix != ".mp4")]
        batch_bucket_files(args.bucket, add=files)
        print(f"uploaded {len(files)} files to hf://buckets/{args.bucket}/stages/{STAGE}/")


if __name__ == "__main__":
    main()
