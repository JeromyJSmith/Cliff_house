"""Stage: equirect — stitch the two fisheye lenses of each clip into a levelled 2:1 equirectangular 360 video.

    pixi run python -m cliff_house.equirect configs/resolve/<project>.toml [clip ...]

Uses the camera's own factory calibration and the measured rig, not a stitcher's guess:
- each lens is the unified (Mei) model with Brown distortion from the telemetry stage's `rig.json`
  (`xi`, focal, centre, k1..k3, p1, p2, then `calib_to_picture` into the 3840² picture);
- the lenses' orientations are `q_rig_from_cam` (factory); the 71 mm baseline is ignored, as every single-centre
  stitch does, so nearby objects show parallax at the seam (visible, aligned for distant scenery);
- the horizon is levelled per frame from the IMU gravity vector (`gravity.parquet`, smoothed over `gravity_sigma_s`
  because the accelerometer also measures the drone's own acceleration); heading follows the rig.

Each output pixel is a ray in the level frame (z up). It is rotated into the rig, then into each lens, and projected
by that lens's model. The two lenses are blended with a feather across the overlap (each lens sees 95° from its axis,
so the overlap is ±`feather_deg` around the 90° boundary). Remap tables are computed at 1/`map_step` resolution per
lens and interpolated, which is exact enough because the maps are smooth within a lens.

Output (bucket layout `stages/equirect/<fingerprint>/<clip>/`): `equirect.mov`, H.265 Main10 at `width × width/2` and
the source frame rate (one output frame per source frame), `frames.parquet` (frame, t_ms, roll/pitch removed), a few
review frames `review/<frame>.jpg`, and `pass.json` (inputs with SHA-256, params, encoder, acceptance). It is an
analysis/presentation product (`use = analysis`): reconstruction keeps using the original fisheye frames.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import tomllib
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np
import polars as pl
from scipy.ndimage import gaussian_filter1d

_MODULE_BYTES = Path(__file__).read_bytes()


@dataclass(frozen=True)
class Params:
    width: int = 7680                 # equirect width; height = width / 2. Source detail is ~1100 px/rad ≈ 6900 px/360°
    map_step: int = 8                 # remap tables computed at 1/map_step resolution, then interpolated
    feather_deg: float = 5.0          # blend band either side of the 90° lens boundary (lenses reach 95°)
    gravity_sigma_s: float = 0.5      # smoothing of the accelerometer's down vector before levelling
    bitrate_mbps: int = 150           # H.265 Main10 (hevc_videotoolbox)
    review_frames: int = 4            # stitched JPEGs saved per clip for the seam/horizon check


def fingerprint(input_shas: list[str], p: Params) -> str:
    digest = hashlib.sha256(hashlib.sha256(_MODULE_BYTES).digest())
    for part in (*input_shas, json.dumps(asdict(p), sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------- geometry

def quat_to_matrix(q: list[float]) -> np.ndarray:
    """[x, y, z, w] quaternion to a rotation matrix."""
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


@dataclass(frozen=True)
class Lens:
    xi: float
    k: tuple[float, float, float]
    p: tuple[float, float]
    focal: tuple[float, float]
    centre: tuple[float, float]
    skew: float
    a: np.ndarray            # 2×2 calib → picture
    t: np.ndarray            # 2 calib → picture offset
    cam_from_rig: np.ndarray  # 3×3
    fov_rad: float

    @classmethod
    def from_rig(cls, lens: dict) -> "Lens":
        intr = lens["intrinsics"]
        mei = intr["model"]["Mei"]
        brown = mei["dist"]["BrownV3"]
        return cls(xi=mei["xi"], k=tuple(brown["k"]), p=tuple(brown["p"]), focal=tuple(intr["focal"]),
                   centre=tuple(intr["centre"]), skew=intr.get("skew", 0.0),
                   a=np.array(lens["calib_to_picture"]["a"]), t=np.array(lens["calib_to_picture"]["t"]),
                   cam_from_rig=quat_to_matrix(lens["q_rig_from_cam"]).T, fov_rad=lens["fov_limit_rad"])

    def project(self, rays_cam: np.ndarray) -> np.ndarray:
        """(..., 3) rays in the lens frame (+z out of the lens) → (..., 2) picture pixels (x, y)."""
        n = rays_cam / np.linalg.norm(rays_cam, axis=-1, keepdims=True)
        denom = n[..., 2] + self.xi
        mu, mv = n[..., 0] / denom, n[..., 1] / denom
        r2 = mu * mu + mv * mv
        radial = 1 + self.k[0] * r2 + self.k[1] * r2 ** 2 + self.k[2] * r2 ** 3
        du = mu * radial + 2 * self.p[0] * mu * mv + self.p[1] * (r2 + 2 * mu * mu)
        dv = mv * radial + self.p[0] * (r2 + 2 * mv * mv) + 2 * self.p[1] * mu * mv
        cx = self.focal[0] * du + self.skew * dv + self.centre[0]
        cy = self.focal[1] * dv + self.centre[1]
        calib = np.stack([cx, cy], axis=-1)
        return calib @ self.a.T + self.t


def level_from_rig(down_rig: np.ndarray) -> np.ndarray:
    """Rotation taking rig vectors into a level frame with z up. Heading follows the rig: the level frame's x axis is
    the rig's x axis projected onto the horizontal plane."""
    up = -down_rig / np.linalg.norm(down_rig)
    x = np.array([1.0, 0.0, 0.0]) - up * up[0]
    if np.linalg.norm(x) < 1e-6:          # rig x axis vertical: use rig y instead
        x = np.array([0.0, 1.0, 0.0]) - up * up[1]
    x /= np.linalg.norm(x)
    y = np.cross(up, x)
    return np.stack([x, y, up])           # rows: level axes in rig coordinates → level_from_rig


def equirect_rays(width: int, height: int) -> np.ndarray:
    """Unit rays of an equirect grid in the level frame: longitude 0 at +x, increasing to the left; latitude +90 up."""
    lon = (0.5 - (np.arange(width) + 0.5) / width) * 2 * np.pi
    lat = (0.5 - (np.arange(height) + 0.5) / height) * np.pi
    lon, lat = np.meshgrid(lon, lat)
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=-1)


def frame_maps(rays_level: np.ndarray, level_from_rig_m: np.ndarray, lenses: list[Lens], p: Params,
               out_size: tuple[int, int]) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Per lens: (map_x, map_y, weight) at full output size, from rays at 1/map_step resolution."""
    rays_rig = rays_level @ level_from_rig_m          # level → rig: v_rig = Rᵀ v_level, i.e. v_level @ R
    feather = np.radians(p.feather_deg)
    out = []
    angles = []
    for lens in lenses:
        cam = rays_rig @ lens.cam_from_rig.T
        xy = lens.project(cam).astype(np.float32)
        angle = np.arccos(np.clip(cam[..., 2] / np.linalg.norm(cam, axis=-1), -1, 1))
        angles.append(angle)
        out.append(xy)
    # weight: 1 inside 90° − feather, 0 beyond 90° + feather, linear between; the two lenses' weights sum to ~1
    w = [np.clip((np.pi / 2 + feather - a) / (2 * feather), 0, 1) for a in angles]
    total = np.maximum(sum(w), 1e-6)
    res = []
    for xy, wi in zip(out, w):
        mx = cv2.resize(xy[..., 0], out_size, interpolation=cv2.INTER_LINEAR)
        my = cv2.resize(xy[..., 1], out_size, interpolation=cv2.INTER_LINEAR)
        ww = cv2.resize((wi / total).astype(np.float32), out_size, interpolation=cv2.INTER_LINEAR)
        res.append((mx, my, ww))
    return res


# ---------------------------------------------------------------- video I/O

def _reader(path: Path, size: int):
    """Decode a lens MP4 to BGR frames through ffmpeg (VideoToolbox decode) as a generator."""
    cmd = ["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", "-i", str(path), "-f", "rawvideo",
           "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=size * size * 3)
    n = size * size * 3
    while True:
        buf = proc.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(size, size, 3)
    proc.wait()


def _writer(path: Path, width: int, height: int, fps: str, p: Params):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
           "-r", fps, "-i", "-", "-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-pix_fmt", "p010le",
           "-b:v", f"{p.bitrate_mbps}M", "-tag:v", "hvc1", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-colorspace", "bt709", str(path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


# ---------------------------------------------------------------- stage

def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def run(clip_dir_remux: Path, clip_dir_telemetry: Path, lens_shas: dict[str, str], frames: int, out_root: Path,
        p: Params) -> dict:
    rig = json.loads((clip_dir_telemetry / "rig.json").read_text())
    clip = clip_dir_remux.name
    inputs = [lens_shas["cam0"], lens_shas["cam1"], _sha(clip_dir_telemetry / "rig.json"),
              _sha(clip_dir_telemetry / "gravity.parquet")]
    fp = fingerprint(inputs, p)
    out = out_root / "equirect" / fp / clip
    if (out / "pass.json").exists():
        return json.loads((out / "pass.json").read_text()) | {"skipped": True}
    out.mkdir(parents=True, exist_ok=True)
    (out / "review").mkdir(exist_ok=True)
    lenses = [Lens.from_rig(rig["lenses"]["lens0"]), Lens.from_rig(rig["lenses"]["lens1"])]
    fps_str = rig["video"]["fps"]
    fps = float(Fraction(fps_str))  # "30000/1001"
    size = int(rig["video"]["width"])
    width, height = p.width, p.width // 2
    small = equirect_rays(width // p.map_step, height // p.map_step)

    g = pl.read_parquet(clip_dir_telemetry / "gravity.parquet")
    g0 = g.select("g_lens0_x", "g_lens0_y", "g_lens0_z").to_numpy()
    down_rig = g0 @ lenses[0].cam_from_rig        # lens0 → rig: v_rig = cam_from_rigᵀ v_cam
    down_rig = gaussian_filter1d(down_rig, sigma=p.gravity_sigma_s * fps, axis=0, mode="nearest")
    down_rig /= np.linalg.norm(down_rig, axis=1, keepdims=True)

    review_at = set(np.linspace(0, frames - 1, p.review_frames).round().astype(int).tolist())
    writer = _writer(out / "equirect.mov", width, height, fps_str, p)
    rows, n = [], 0
    started = time.time()
    for i, (a, b) in enumerate(zip(_reader(clip_dir_remux / "cam0.mp4", size),
                                   _reader(clip_dir_remux / "cam1.mp4", size))):
        R = level_from_rig(down_rig[min(i, len(down_rig) - 1)])
        maps = frame_maps(small, R, lenses, p, (width, height))
        (mx0, my0, w0), (mx1, my1, w1) = maps
        frame = cv2.blendLinear(cv2.remap(a, mx0, my0, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT),
                                cv2.remap(b, mx1, my1, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT), w0, w1)
        writer.stdin.write(frame.tobytes())
        if i in review_at:
            cv2.imwrite(str(out / "review" / f"{i:06d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        # tilt of the down-looking lens's axis from true down: what the levelling removed in this frame
        axis0_rig = lenses[0].cam_from_rig[2]
        rows.append({"frame": i, "t_ms": round(i * 1000 / fps, 3),
                     "tilt_deg": float(np.degrees(np.arccos(np.clip(axis0_rig @ down_rig[min(i, len(down_rig) - 1)],
                                                                    -1, 1))))})
        n += 1
    writer.stdin.close()
    writer.wait()
    seconds = round(time.time() - started, 1)
    pl.DataFrame(rows).write_parquet(out / "frames.parquet")
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_packets,width,height,codec_name,pix_fmt", "-of", "json",
                            str(out / "equirect.mov")], capture_output=True, text=True)
    stream = json.loads(probe.stdout or "{}").get("streams", [{}])[0]
    acceptance = {"frames_decoded": n, "frames_expected": frames, "frames_written": int(stream.get("nb_read_packets",
                                                                                                  0)),
                  "size": [stream.get("width"), stream.get("height")], "codec": stream.get("codec_name"),
                  "pix_fmt": stream.get("pix_fmt")}
    acceptance["ok"] = acceptance["frames_decoded"] == frames == acceptance["frames_written"]
    meta = {"stage": "equirect", "use": "analysis", "clip": clip, "fingerprint": fp, "params": asdict(p),
            "code_version": hashlib.sha256(_MODULE_BYTES).hexdigest()[:12],
            "inputs": {"cam0_sha256": inputs[0], "cam1_sha256": inputs[1], "rig_json_sha256": inputs[2],
                       "gravity_sha256": inputs[3]},
            "rig": {"lens0_from_lens1_deg": rig["lens0_from_lens1"]["rotation_deg"],
                    "baseline_m": rig["lens0_from_lens1"]["baseline_m"]},
            "seconds": seconds, "fps_processed": round(n / max(seconds, 1e-6), 2),
            "bytes": (out / "equirect.mov").stat().st_size, "acceptance": acceptance}
    (out / "pass.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    return meta | {"output_dir": str(out)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    parser.add_argument("clips", nargs="*", help="clip names or suffixes (default: every clip)")
    args = parser.parse_args(argv)
    raw = tomllib.loads(args.config.read_text())
    remux = Path(raw["stages"]["remux_manifest"])
    stage_root = Path(raw["stages"]["local_root"])
    tele = pl.read_parquet(stage_root / "telemetry" / "manifest.parquet")
    man = pl.read_parquet(remux)
    p = Params(**raw.get("equirect", {}).get("params", {}))
    clips = sorted(man["clip"].unique().to_list())
    if args.clips:
        clips = [c for c in clips if any(c == s or c.endswith(f"_{s}") for s in args.clips)]
    ok = True
    for clip in clips:
        rows = man.filter(pl.col("clip") == clip)
        shas = {r["cam"]: r["sha256"] for r in rows.iter_rows(named=True)}
        fp_remux = rows["fingerprint"][0]
        fp_tele = tele.filter(pl.col("clip") == clip)["fingerprint"][0]
        res = run(remux.parent / fp_remux / clip, stage_root / "telemetry" / fp_tele / clip, shas,
                  int(rows["packets"][0]), stage_root, p)
        print(json.dumps({"clip": clip, "fingerprint": res["fingerprint"], **res["acceptance"],
                          "seconds": res.get("seconds"), "fps": res.get("fps_processed")}), flush=True)
        ok &= res["acceptance"]["ok"]
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
