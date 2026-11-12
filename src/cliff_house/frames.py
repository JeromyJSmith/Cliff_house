"""Stage 2: frames — synchronized per-lens frames with sharpness and a motion-based reliability weight.

Extraction is Spirula's (`spirula sam extract --sync`, SPEC §5 and docs/research/spirula-settings §4.1): both lenses
are decoded in lockstep, so the two images of one stem are one rig instant, and the sharpest frame of each window is
kept. Spirula's report gives the measured blur of every kept frame.

This stage adds what the camera itself knows. For each frame time it reads the telemetry stage's gyro (≈1 kHz) over
the frame's own exposure interval and predicts the motion blur that rotation causes:

    predicted_blur_px = |ω| (rad/s) × exposure (s) × pixels-per-radian at the lens centre

For the Insta360 unified (Mei) model the image scale near the optical axis is f / (1 + ξ): f and ξ come from the
camera's own calibration in the telemetry stage's lens.json (≈1,100 px/rad for this A1, matching the SfM focal the
spec records). Rotation is the dominant blur source for a hand-carried or slow drone; translation blur is not
modelled. The reliability weight is exp(-predicted_blur_px / blur_reject_px), using the same threshold Spirula
rejects on. `rs_skew_px` is the same rotation over the sensor's readout time (rolling-shutter skew across the frame).

Assumption: the parser's IMU and exposure clocks are clip time with 0 at the first video frame (Gyroflow treats
them this way); no extra offset is applied.

Outputs per clip under `stages/frames/<fingerprint>/<clip>/`: `cam0/*.jpg`, `cam1/*.jpg` (stem = 0-based source
frame index), `report.csv` (Spirula), `frames.parquet`, `spirula.log`.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import polars as pl

from cliff_house.insv_telemetry import sha256_file
from cliff_house.remux import video_streams

STAGE = "frames"
STAGE_VERSION = 1
DEFAULT_SPIRULA = "/Applications/Spirula Studio.app/Contents/MacOS/spirula"
PARAMS = {"skip": 15, "adaptive": True, "blur_reject": 8.0, "similar": 4}


def spirula_version(spirula: str) -> str:
    out = subprocess.run([spirula, "--help"], capture_output=True, text=True).stdout
    return next((line.strip() for line in out.splitlines() if line.startswith("Spirula")), "unknown")


def fingerprint(source_sha256: str, telemetry_fingerprint: str, spirula: str, params: dict) -> str:
    key = json.dumps({"stage": STAGE, "stage_version": STAGE_VERSION, "spirula": spirula_version(spirula),
                      "params": params, "source_sha256": source_sha256, "telemetry": telemetry_fingerprint},
                     sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def pixels_per_radian(lens: dict) -> dict[str, float]:
    """Image scale at the optical axis for each lens of the camera's Mei calibration, in output pixels per radian."""
    out = {}
    for i, cam in enumerate(lens["rig"]["projection"]["kind"]["Rig"]["cameras"]):
        mei = cam["intrinsics"]["model"]["Mei"]
        focal_calib = sum(cam["intrinsics"]["focal"]) / 2
        scale = cam["calib_to_picture"]["a"][0][0]
        out[f"cam{i}"] = focal_calib * scale / (1 + mei["xi"])
    return out


def gyro_over_exposure(imu: pl.DataFrame, exposure: pl.DataFrame, t_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean angular speed (deg/s) during each frame's exposure, and that exposure (s)."""
    it = imu["t_ms"].to_numpy() / 1000
    speed = np.sqrt(imu["gyro_x"].to_numpy() ** 2 + imu["gyro_y"].to_numpy() ** 2 + imu["gyro_z"].to_numpy() ** 2)
    et, ev = exposure["t_s"].to_numpy(), exposure["exposure_s"].to_numpy()
    exp_s = ev[np.clip(np.searchsorted(et, t_s, side="right") - 1, 0, len(ev) - 1)]
    out = np.empty(len(t_s))
    for k, (t, e) in enumerate(zip(t_s, exp_s)):
        lo, hi = np.searchsorted(it, t - e / 2), np.searchsorted(it, t + e / 2, side="right")
        out[k] = speed[lo:hi].mean() if hi > lo else speed[min(np.searchsorted(it, t), len(it) - 1)]
    return out, exp_s


def frame_table(clip: str, source_sha256: str, clip_dir: Path, fps: Fraction, start_time: float,
                report: pl.DataFrame, imu: pl.DataFrame, exposure: pl.DataFrame, lens: dict,
                blur_reject_px: float) -> pl.DataFrame:
    stems = {cam: sorted(int(p.stem) for p in (clip_dir / cam).glob("*.jpg")) for cam in ("cam0", "cam1")}
    if stems["cam0"] != stems["cam1"]:
        raise RuntimeError(f"{clip}: lenses are not in sync ({len(stems['cam0'])} vs {len(stems['cam1'])} frames)")
    idx = np.array(stems["cam0"], dtype=np.int64)
    t_s = start_time + idx * float(1 / fps)
    gyro_dps, exp_s = gyro_over_exposure(imu, exposure, t_s)
    readout_s = (lens.get("data") or {}).get("frame_readout_time", 0.0) / 1000
    ppr = pixels_per_radian(lens)
    measured = report.select(pl.col("frame").alias("frame_index"), "edge_width_px", "blur_px")
    parts = []
    for cam in ("cam0", "cam1"):
        omega = np.radians(gyro_dps)
        predicted = omega * exp_s * ppr[cam]
        parts.append(pl.DataFrame({
            "clip": clip, "source_sha256": source_sha256, "cam": cam, "frame_index": idx, "t_s": t_s,
            "image": [f"{clip}/{cam}/{i:05d}.jpg" for i in idx], "exposure_s": exp_s, "gyro_dps": gyro_dps,
            "px_per_rad": ppr[cam], "predicted_blur_px": predicted, "rs_skew_px": omega * readout_s * ppr[cam],
            "weight": np.exp(-predicted / blur_reject_px),
        }))
    table = pl.concat(parts).join(measured, on="frame_index", how="left")
    if table.select("cam", "frame_index").is_duplicated().any():
        raise RuntimeError(f"{clip}: duplicate frame timestamps")
    return table.sort("cam", "frame_index")


def extract_clip(path: Path, telemetry_dir: Path, telemetry_fp: str, out_root: Path, spirula: str,
                 source_sha256: str | None = None, params: dict = PARAMS) -> pl.DataFrame:
    sha = source_sha256 or sha256_file(path)
    fp = fingerprint(sha, telemetry_fp, spirula, params)
    clip_dir = out_root / fp / path.stem
    table_path = clip_dir / "frames.parquet"
    if table_path.exists():
        return pl.read_parquet(table_path)
    # Spirula writes into a fresh folder that is renamed into place only after the table is built, so an
    # interrupted run never leaves a half-filled fingerprint folder (its partial folder is kept for inspection).
    work = clip_dir.with_name(f"{clip_dir.name}.partial-{os.getpid()}")
    work.mkdir(parents=True)
    ffmpeg = shutil.which("ffmpeg")
    env = {**os.environ, "PATH": f"{Path(ffmpeg).parent}{os.pathsep}{os.environ.get('PATH', '')}"} if ffmpeg else None
    cmd = [spirula, "sam", "extract", str(path), "-o", str(work), "--sync", "--skip", str(params["skip"]),
           "--blur-reject", str(params["blur_reject"]), "--similar", str(params["similar"]),
           "--report", str(work / "report.csv")] + (["--adaptive"] if params["adaptive"] else [])
    with (work / "spirula.log").open("w") as log:
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT, env=env)
    stream = video_streams(path)[0]
    table = frame_table(
        path.stem, sha, work, Fraction(stream["r_frame_rate"]), float(stream.get("start_time") or 0.0),
        pl.read_csv(work / "report.csv").filter(pl.col("verdict") == "kept"),
        pl.read_parquet(telemetry_dir / "imu.parquet"), pl.read_parquet(telemetry_dir / "exposure.parquet"),
        json.loads((telemetry_dir / "lens.json").read_text()), params["blur_reject"])
    table = table.with_columns(pl.lit(fp).alias("fingerprint"),
                               (pl.lit(f"{fp}/") + pl.col("image")).alias("image"))
    table.write_parquet(work / "frames.parquet")
    work.rename(clip_dir)
    return pl.read_parquet(table_path)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("clips", nargs="+", type=Path)
    ap.add_argument("--telemetry", type=Path, required=True, help="local telemetry stage root (with manifest.parquet)")
    ap.add_argument("--out", type=Path, required=True, help="local stage root (mirrors stages/frames/)")
    ap.add_argument("--manifest", type=Path, help="sources.parquet: take SHA-256 from it instead of hashing")
    ap.add_argument("--spirula", default=os.environ.get("SPIRULA", DEFAULT_SPIRULA))
    ap.add_argument("--bucket", help="HF bucket id; upload frames, tables and the stage manifest")
    args = ap.parse_args(argv)

    tel = pl.read_parquet(args.telemetry / "manifest.parquet").select("clip", "fingerprint")
    tel_fp = dict(tel.iter_rows())
    known = {}
    if args.manifest:
        known = {Path(p).name: s for p, s in pl.read_parquet(args.manifest).select("path", "sha256").iter_rows()}
    tables = []
    for clip in sorted(args.clips):
        fp = tel_fp[clip.stem]
        tables.append(extract_clip(clip, args.telemetry / fp / clip.stem, fp, args.out, args.spirula,
                                   known.get(clip.name)))
        print(f"{clip.stem}: {tables[-1].height // 2} rig frames")
    frames = pl.concat(tables)
    frames.write_parquet(args.out / "frames.parquet")
    summary = (frames.filter(pl.col("cam") == "cam0").group_by("clip").agg(
        pl.len().alias("rig_frames"), pl.col("blur_px").median().alias("blur_px_median"),
        pl.col("predicted_blur_px").median().alias("predicted_blur_px_median"),
        pl.col("weight").mean().alias("weight_mean"), pl.col("fingerprint").first()).sort("clip"))
    summary.write_parquet(args.out / "manifest.parquet")
    print(summary)
    if args.bucket:
        from huggingface_hub import batch_bucket_files

        files = [(str(p), f"stages/{STAGE}/{p.relative_to(args.out).as_posix()}")
                 for p in sorted(args.out.rglob("*")) if p.is_file()]
        for start in range(0, len(files), 500):
            batch_bucket_files(args.bucket, add=files[start:start + 500])
        print(f"uploaded {len(files)} files to hf://buckets/{args.bucket}/stages/{STAGE}/")


if __name__ == "__main__":
    main()
