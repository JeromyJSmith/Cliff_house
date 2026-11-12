"""Stage: telemetry — decode the Insta360 trailer of each `.insv` clip.

The Antigravity A1 (Insta360 X5 camera) writes a trailer after the two H.264 lens streams. telemetry-parser
(Apache-2.0, the parser Gyroflow uses) reads it: GPS fixes, a ~1 kHz gyro/accelerometer stream, exposure, and the
factory per-lens calibration. This stage turns one clip into typed tables plus a summary, keyed by a fingerprint of
(source SHA-256, stage version, parser version) so a rerun skips clips that are already done (SPEC §3.3).

Outputs per clip, under `stages/telemetry/<fingerprint>/<clip>/`:
  gps.parquet      one row per fix: UTC time, lat/lon (WGS84 degrees), altitude (m), reported speed (m/s), track
  imu.parquet      one row per sample: t_ms (clip time), gyro deg/s, accel m/s^2 — normalized by the parser
  exposure.parquet one row per exposure record: t_s (clip time), exposure_s (shutter time)
  lens.json        the parser's Lens/Data and Lens/Rig records (calibration as written by the camera)
  rig.json         per lens (lens0 = stream 0:v:0, lens1 = 0:v:1): intrinsics, factory extrinsics, lens0←lens1
                   relative pose, measured IMU→lens rotation and the IMU-vs-video clock check (cliff_house.imu_camera)
  motion.parquet   per IMU sample: angular speed over the exposure, predicted rotation blur and weight per lens
  gravity.parquet  per video frame time: gravity (down) unit vector in each lens frame, accel norm, quasi_static
  summary.json     derived checks: fix rate, path length, implied vs reported speed, IMU rate, device identity

`manifest.parquet` at the stage root lists exactly one row per clip: the current fingerprint. Older fingerprint
folders (earlier stage versions) are kept, never overwritten, and are not current.

GPS on this camera is a consumer fix: indoors or near buildings it drifts, so path length and speed are evidence
for review, not survey measurements. Nothing here sets reconstruction scale.
"""
import argparse
import hashlib
import json
import math
from importlib.metadata import version
from pathlib import Path

import numpy as np
import polars as pl

from cliff_house import imu_camera

STAGE = "telemetry"
STAGE_VERSION = 4  # 2: GPS km/h -> m/s. 3: exposure.parquet. 4: rig.json, motion.parquet, gravity.parquet
EARTH_RADIUS_M = 6_371_008.8  # IUGG mean radius

GPS_SCHEMA = pl.Schema({
    "time_utc": pl.Datetime("us", "UTC"),
    "lat": pl.Float64,
    "lon": pl.Float64,
    "altitude_m": pl.Float64,
    "speed_mps": pl.Float64,
    "track_deg": pl.Float64,
    "is_acquired": pl.Boolean,
})
IMU_SCHEMA = pl.Schema({
    "t_ms": pl.Float64,
    "gyro_x": pl.Float64, "gyro_y": pl.Float64, "gyro_z": pl.Float64,
    "accl_x": pl.Float64, "accl_y": pl.Float64, "accl_z": pl.Float64,
})


def parser_version() -> str:
    return version("telemetry-parser")


def fingerprint(source_sha256: str) -> str:
    """Work-item identity: same source bytes + same stage code + same parser → same outputs."""
    key = json.dumps({"stage": STAGE, "stage_version": STAGE_VERSION, "parser": parser_version(),
                      "source_sha256": source_sha256}, sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _tags(telemetry: list[dict]) -> dict[str, object]:
    """Flatten the parser's [{group: {tag: value}}] blocks into {"group/tag": value}, concatenating list values."""
    out: dict[str, object] = {}
    for block in telemetry:
        for group, tags in block.items():
            if not isinstance(tags, dict):
                continue
            for tag, value in tags.items():
                key = f"{group}/{tag}"
                if isinstance(value, list) and isinstance(out.get(key), list):
                    out[key] = out[key] + value
                else:
                    out.setdefault(key, value)
    return out


def gps_frame(telemetry: list[dict]) -> pl.DataFrame:
    fixes = _tags(telemetry).get("GPS/Data") or []
    rows = [{
        "time_utc": f["unix_timestamp"] * 1e6, "lat": f["lat"], "lon": f["lon"], "altitude_m": f.get("altitude"),
        # telemetry-parser multiplies the trailer's m/s by 3.6 (src/insta360/record.rs, RecordType::Gps; GpsData.speed
        # "in km/h"), so divide it back to SI here.
        "speed_mps": None if f.get("speed") is None else f["speed"] / 3.6,
        "track_deg": f.get("track"), "is_acquired": f.get("is_acquired"),
    } for f in fixes if isinstance(f, dict) and "lat" in f and "lon" in f]
    frame = pl.DataFrame(rows, schema={**GPS_SCHEMA, "time_utc": pl.Float64})
    return frame.with_columns(pl.col("time_utc").cast(pl.Int64).cast(pl.Datetime("us", "UTC"))).sort("time_utc")


def imu_frame(normalized_imu: list[dict]) -> pl.DataFrame:
    rows = [{"t_ms": s["timestamp_ms"],
             "gyro_x": s["gyro"][0], "gyro_y": s["gyro"][1], "gyro_z": s["gyro"][2],
             "accl_x": s["accl"][0], "accl_y": s["accl"][1], "accl_z": s["accl"][2]}
            for s in normalized_imu if s.get("gyro") and s.get("accl")]
    return pl.DataFrame(rows, schema=IMU_SCHEMA).sort("t_ms")


def exposure_frame(telemetry: list[dict]) -> pl.DataFrame:
    rows = [{"t_s": r["t"], "exposure_s": r["v"]} for r in (_tags(telemetry).get("Exposure/Data") or [])
            if isinstance(r, dict) and "t" in r and "v" in r]
    return pl.DataFrame(rows, schema={"t_s": pl.Float64, "exposure_s": pl.Float64}).sort("t_s")


def haversine_m(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Great-circle distance in metres between consecutive points."""
    p, lam = np.radians(lat), np.radians(lon)
    dp, dl = np.diff(p), np.diff(lam)
    h = np.sin(dp / 2) ** 2 + np.cos(p[:-1]) * np.cos(p[1:]) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(h))


def summarize(gps: pl.DataFrame, imu: pl.DataFrame) -> dict:
    fixed = gps.filter(pl.col("is_acquired") & (pl.col("lat").abs() > 1e-6) & (pl.col("lon").abs() > 1e-6))
    out: dict = {"gps_fixes": gps.height, "gps_fixes_acquired": fixed.height}
    if fixed.height >= 2:
        t = fixed["time_utc"].dt.epoch("us").to_numpy() / 1e6
        steps = haversine_m(fixed["lat"].to_numpy(), fixed["lon"].to_numpy())
        span = float(t[-1] - t[0])
        out |= {
            "gps_first_utc": fixed["time_utc"][0].isoformat(), "gps_last_utc": fixed["time_utc"][-1].isoformat(),
            "gps_span_s": span, "gps_rate_hz": (fixed.height - 1) / span if span > 0 else None,
            "path_length_m": float(steps.sum()),
            "implied_mean_speed_mps": float(steps.sum() / span) if span > 0 else None,
            "reported_mean_speed_mps": fixed["speed_mps"].mean(),
            "lat_range": [fixed["lat"].min(), fixed["lat"].max()],
            "lon_range": [fixed["lon"].min(), fixed["lon"].max()],
            "altitude_range_m": [fixed["altitude_m"].min(), fixed["altitude_m"].max()],
        }
    if imu.height >= 2:
        span_ms = imu["t_ms"][-1] - imu["t_ms"][0]
        accel_norm = (imu["accl_x"] ** 2 + imu["accl_y"] ** 2 + imu["accl_z"] ** 2).sqrt()
        out |= {"imu_samples": imu.height, "imu_span_s": span_ms / 1000,
                "imu_rate_hz": (imu.height - 1) / (span_ms / 1000),
                "accel_norm_median_mps2": float(accel_norm.median())}
    return out


def decode(path: Path) -> dict:
    """Parse one clip. Returns device identity, GPS/IMU tables and the raw lens records."""
    import telemetry_parser

    tp = telemetry_parser.Parser(str(path))
    telemetry = tp.telemetry()
    tags = _tags(telemetry)
    meta = tags.get("Default/Metadata") or {}
    return {
        "camera": tp.camera, "model": tp.model,
        "serial_number": meta.get("serial_number"), "firmware": meta.get("fw_version"),
        "gps": gps_frame(telemetry), "imu": imu_frame(tp.normalized_imu()), "exposure": exposure_frame(telemetry),
        "lens": {"data": tags.get("Lens/Data"), "rig": tags.get("Lens/Rig")},
    }


def process(path: Path, out_root: Path, source_sha256: str | None = None) -> dict:
    """Decode `path` into out_root/<fingerprint>/<clip>/ and return its manifest row."""
    sha = source_sha256 or sha256_file(path)
    fp = fingerprint(sha)
    clip_dir = out_root / fp / path.stem
    if (clip_dir / "summary.json").exists():  # this fingerprint is already done; outputs are never overwritten
        return json.loads((clip_dir / "summary.json").read_text())
    clip_dir.mkdir(parents=True, exist_ok=True)
    result = decode(path)
    result["gps"].write_parquet(clip_dir / "gps.parquet")
    result["imu"].write_parquet(clip_dir / "imu.parquet")
    result["exposure"].write_parquet(clip_dir / "exposure.parquet")
    (clip_dir / "lens.json").write_text(json.dumps(result["lens"], indent=2, default=str))
    rig = rig_record(path, result["lens"], result["imu"])
    (clip_dir / "rig.json").write_text(json.dumps(rig, indent=2))
    ppr = {lens: rig["lenses"][lens]["px_per_rad"] for lens in imu_camera.LENSES}
    imu_camera.motion_table(result["imu"], result["exposure"], ppr).write_parquet(clip_dir / "motion.parquet")
    frame_ms = np.arange(rig["video"]["frames"]) * 1001 / 30
    cam_from_imu = {lens: np.array(rig["lenses"][lens]["cam_from_imu"], dtype=float) for lens in imu_camera.LENSES}
    imu_camera.gravity_table(result["imu"], cam_from_imu, frame_ms).write_parquet(clip_dir / "gravity.parquet")
    summary = {"clip": path.stem, "source_sha256": sha, "fingerprint": fp, "stage_version": STAGE_VERSION,
               "parser": f"telemetry-parser {parser_version()}", "camera": result["camera"],
               "model": result["model"], "serial_number": result["serial_number"], "firmware": result["firmware"],
               **summarize(result["gps"], result["imu"])}
    (clip_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def rig_record(path: Path, lens: dict, imu: pl.DataFrame) -> dict:
    """Lens ↔ stream mapping, calibration and extrinsics from the camera, plus the measured IMU→lens geometry."""
    from scipy.spatial.transform import Rotation

    from cliff_house.remux import video_streams

    streams = video_streams(path)
    cams = lens["rig"]["projection"]["kind"]["Rig"]["cameras"]
    q = [Rotation.from_quat([c["rotation"][k] for k in "xyzw"]) for c in cams]
    t = [np.array(c["translation"], dtype=float) for c in cams]
    out = {"conventions": {
        "lens_frame": "+x right, +y down, +z out of the lens (telemetry-parser Lens/Rig)",
        "q_rig_from_cam": "quaternion [x, y, z, w] rotating lens-frame vectors into the rig frame (factory)",
        "translation_m": "lens origin in the rig frame, metres (factory)",
        "cam_from_imu": "3x3 rotation taking normalized-IMU vectors (gyro, accel) into the lens frame",
        "imu_clock": "imu.parquet t_ms is video-stream time in ms from the first frame; lag_ms = measured offset "
                     "(gyro sampled at t_video + lag matches image motion), not applied"},
        "video": {"fps": streams[0]["r_frame_rate"], "frames": int(streams[0]["nb_frames"]),
                  "width": streams[0]["width"], "height": streams[0]["height"]},
        "lenses": {}}
    for i, cam in enumerate(cams):
        stream = cam["picture"]["input"]
        name = f"lens{stream}"  # named by video stream, as molab's frames stage names them
        ppr = imu_camera.pixels_per_radian(cam)
        rate, tv = imu_camera.camera_rates(path, stream, ppr)
        fit = imu_camera.fit_sync(rate, tv, imu)
        constant = imu_camera.A1_CAM_FROM_IMU[name].astype(int).tolist()
        out["lenses"][name] = {
            "stream": stream, "ffmpeg_map": f"0:v:{stream}", "px_per_rad": ppr,
            "intrinsics": cam["intrinsics"], "calib_to_picture": cam["calib_to_picture"],
            "image_circle": cam.get("image_circle"), "fov_limit_rad": cam.get("fov_limit"), "mirror": cam.get("mirror"),
            "q_rig_from_cam": [float(c) for c in q[i].as_quat()], "translation_m": t[i].tolist(),
            "cam_from_imu": constant, "sync_fit": fit | {"agrees_with_cam_from_imu": fit["cam_from_imu"] == constant}}
    r01 = (q[0].inv() * q[1])
    out["lens0_from_lens1"] = {"R": r01.as_matrix().tolist(), "rotation_deg": float(np.degrees(r01.magnitude())),
                               "t_m": q[0].inv().apply(t[1] - t[0]).tolist(),
                               "baseline_m": float(np.linalg.norm(t[1] - t[0]))}
    out["readout_ms"] = (lens.get("data") or {}).get("frame_readout_time")
    return out


def _sanitize(value):
    return None if isinstance(value, float) and math.isnan(value) else value


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("clips", nargs="+", type=Path, help=".insv files")
    ap.add_argument("--out", type=Path, required=True, help="local stage root (mirrors stages/telemetry/)")
    ap.add_argument("--manifest", type=Path, help="sources.parquet: take SHA-256 from it instead of hashing")
    ap.add_argument("--bucket", help="HF bucket id; upload outputs under stages/telemetry/ when given")
    args = ap.parse_args(argv)

    known: dict[str, str] = {}
    if args.manifest:
        m = pl.read_parquet(args.manifest).select("path", "sha256")
        known = {Path(p).name: s for p, s in m.iter_rows()}
    rows = [process(c, args.out, known.get(c.name)) for c in sorted(args.clips)]
    manifest = pl.DataFrame([{k: _sanitize(v) for k, v in r.items()
                              if not isinstance(v, (list, dict))} for r in rows])
    manifest.write_parquet(args.out / "manifest.parquet")
    print(manifest.select("clip", "fingerprint", "model", "gps_fixes_acquired", "path_length_m",
                          "implied_mean_speed_mps", "reported_mean_speed_mps", "imu_rate_hz"))
    if args.bucket:
        from huggingface_hub import batch_bucket_files

        files = [(str(p), f"stages/{STAGE}/{p.relative_to(args.out).as_posix()}")
                 for p in sorted(args.out.rglob("*")) if p.is_file()]
        batch_bucket_files(args.bucket, add=files)
        print(f"uploaded {len(files)} files to hf://buckets/{args.bucket}/stages/{STAGE}/")


if __name__ == "__main__":
    main()
