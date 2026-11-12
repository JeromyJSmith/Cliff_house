"""IMU ↔ lens geometry for the Antigravity A1: axis mapping, clock check, motion blur and gravity per lens.

Frames and conventions
- Lens camera frame: +x right, +y down, +z forward (out of the lens), the frame telemetry-parser's Lens/Rig uses
  (`q_rig_from_cam`, src/insta360/rig.rs `rotation`). `lens0` is video stream 0:v:0, `lens1` is 0:v:1 (the rig's
  `picture.input`). On the A1 lens0 looks down and lens1 looks up.
- IMU frame: the axes of `telemetry_parser.Parser.normalized_imu()` (gyro deg/s, accel m/s²).
- `A1_CAM_FROM_IMU[lens]` rotates an IMU-frame vector into that lens's camera frame. It was measured, not assumed:
  near a fisheye's centre the image moves by (angular rate × pixels-per-radian), so the mean optical flow of the
  central crop gives the lens's pan/tilt rate and its curl gives roll. A signed-permutation fit of gyro to those
  rates over lags of ±200 ms gave the same two matrices on 15 of 16 clip/lens pairs of the Frasier Nov-10 clips
  (correlations 0.52–0.99 per axis). The odd one, clip 041 lens1, faces a blank ceiling, and its fit is noise.
  The two matrices differ by 180° about +y, which is exactly the factory relative rotation between the lenses.
- Clock: the best lag was −1 to −5 ms on every good fit (gyro sampled at t_video − 1…5 ms matches the image motion
  at t_video), smaller than the 21 ms sensor readout spread, so the parser's IMU `t_ms` is treated as the video
  stream clock (ms from the first frame, every stream starts at 0) and no offset is applied. `fit_sync` re-measures
  it per clip and the result is written to rig.json.
"""
import itertools
import subprocess
from pathlib import Path

import numpy as np
import polars as pl

LENSES = ("lens0", "lens1")
A1_CAM_FROM_IMU = {
    "lens0": np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=float),
    "lens1": np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], dtype=float),
}
STANDARD_GRAVITY = 9.80665


def pixels_per_radian(camera: dict) -> float:
    """Image scale at the optical axis of the unified (Mei) model, in output pixels: f·s / (1 + ξ)."""
    intr = camera["intrinsics"]
    return sum(intr["focal"]) / 2 * camera["calib_to_picture"]["a"][0][0] / (1 + intr["model"]["Mei"]["xi"])


def _window_mean(t: np.ndarray, v: np.ndarray, half: np.ndarray) -> np.ndarray:
    """Mean of v over [t-half, t+half] for every t (v sampled at sorted times t), via cumulative sums."""
    c = np.concatenate([[0.0], np.cumsum(v)])
    lo = np.searchsorted(t, t - half, side="left")
    hi = np.searchsorted(t, t + half, side="right")
    return (c[hi] - c[lo]) / np.maximum(hi - lo, 1)


def motion_table(imu: pl.DataFrame, exposure: pl.DataFrame, ppr: dict[str, float],
                 blur_reject_px: float = 8.0) -> pl.DataFrame:
    """Per IMU sample: angular speed averaged over the exposure centred there, predicted rotation blur per lens
    (|ω| · exposure · pixels-per-radian at the lens centre) and weight = exp(-blur / blur_reject_px)."""
    t = imu["t_ms"].to_numpy() / 1000
    speed = np.sqrt(sum(imu[c].to_numpy() ** 2 for c in ("gyro_x", "gyro_y", "gyro_z")))
    et, ev = exposure["t_s"].to_numpy(), exposure["exposure_s"].to_numpy()
    exp_s = ev[np.clip(np.searchsorted(et, t, side="right") - 1, 0, len(ev) - 1)]
    omega = _window_mean(t, speed, exp_s / 2)
    cols = {"t_ms": t * 1000, "omega_dps": omega, "exposure_s": exp_s}
    for lens in LENSES:
        blur = np.radians(omega) * exp_s * ppr[lens]
        cols[f"blur_px_{lens}"] = blur
        cols[f"weight_{lens}"] = np.exp(-blur / blur_reject_px)
    return pl.DataFrame(cols)


def gravity_table(imu: pl.DataFrame, cam_from_imu: dict[str, np.ndarray], t_ms: np.ndarray,
                  window_s: float = 1.0) -> pl.DataFrame:
    """Gravity (pointing down) as a unit vector in each lens frame at the requested times.

    The accelerometer measures specific force, which at rest points up, so down = -mean(accel) over a centred
    window of `window_s` (it averages out hand motion). `accel_norm_mps2` near 9.81 and low `omega_dps` mark the
    samples where the estimate is trustworthy (`quasi_static`)."""
    ti = imu["t_ms"].to_numpy() / 1000
    a = np.stack([imu[c].to_numpy() for c in ("accl_x", "accl_y", "accl_z")], 1)
    speed = np.sqrt(sum(imu[c].to_numpy() ** 2 for c in ("gyro_x", "gyro_y", "gyro_z")))
    half = np.full(len(ti), window_s / 2)
    a_lp = np.stack([_window_mean(ti, a[:, k], half) for k in range(3)], 1)
    w_lp = _window_mean(ti, speed, half)
    q = np.asarray(t_ms, dtype=float) / 1000
    a_q = np.stack([np.interp(q, ti, a_lp[:, k]) for k in range(3)], 1)
    w_q = np.interp(q, ti, w_lp)
    norm = np.linalg.norm(a_q, axis=1)
    down_imu = -a_q / norm[:, None]
    cols = {"t_ms": q * 1000, "accel_norm_mps2": norm, "omega_dps": w_q,
            "quasi_static": (np.abs(norm - STANDARD_GRAVITY) < 0.5) & (w_q < 30.0)}
    for lens in LENSES:
        g = down_imu @ cam_from_imu[lens].T
        for k, ax in enumerate("xyz"):
            cols[f"g_{lens}_{ax}"] = g[:, k]
    return pl.DataFrame(cols)


def camera_rates(clip: Path, stream: int, ppr: float, seconds: float = 90.0, size: int = 480,
                 ffmpeg: str = "ffmpeg") -> tuple[np.ndarray, np.ndarray]:
    """Lens angular rate (deg/s, lens frame x/y/z) between consecutive frames, from central optical flow,
    and the mid-interval video time of each estimate (s)."""
    import cv2

    raw = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(clip), "-map", f"0:v:{stream}", "-t",
                          str(seconds), "-vf", f"scale={size}:{size},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, size, size)
    fps = 30000 / 1001
    p = ppr * size / 3840
    c0, c1 = int(size * 0.35), int(size * 0.65)
    yy, xx = np.mgrid[c0:c1, c0:c1].astype(float) - size / 2
    r2 = np.maximum(xx ** 2 + yy ** 2, 1)
    rates = []
    for a, b in zip(frames[:-1], frames[1:]):
        f = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 21, 3, 5, 1.1, 0)[c0:c1, c0:c1]
        fx, fy = f[..., 0], f[..., 1]
        # A static point at the centre moves by -ω×ẑ = (-ω_y, ω_x) per radian; roll ω_z gives flow (ω_z·y, -ω_z·x).
        rates.append((fy.mean() / p * fps, -fx.mean() / p * fps, -((xx * fy - yy * fx) / r2).mean() * fps))
    return np.degrees(np.array(rates)), (np.arange(len(rates)) + 0.5) / fps


def fit_sync(cam_rate: np.ndarray, t_video: np.ndarray, imu: pl.DataFrame,
             max_lag_s: float = 0.2) -> dict:
    """Best proper signed permutation R (cam = R · imu) and lag L (gyro sampled at t_video + L) in least squares."""
    ti = imu["t_ms"].to_numpy() / 1000
    g = np.stack([imu[c].to_numpy() for c in ("gyro_x", "gyro_y", "gyro_z")], 1)
    lags = np.round(np.arange(-max_lag_s, max_lag_s + 1e-9, 0.001), 3)
    sampled = {L: np.stack([np.interp(t_video + L, ti, g[:, k]) for k in range(3)], 1) for L in lags}
    candidates = []
    for perm in itertools.permutations(range(3)):
        for sg in itertools.product((1, -1), repeat=3):
            M = np.zeros((3, 3))
            for i in range(3):
                M[i, perm[i]] = sg[i]
            if np.linalg.det(M) > 0:
                candidates.append(M)
    coarse = min(((np.mean((sampled[L] @ M.T - cam_rate) ** 2), i, L) for i, M in enumerate(candidates)
                  for L in lags[::10]))
    M = candidates[coarse[1]]
    err, lag = min((np.mean((sampled[L] @ M.T - cam_rate) ** 2), L) for L in lags if abs(L - coarse[2]) <= 0.0105)
    pred = sampled[lag] @ M.T
    r = [float(np.corrcoef(pred[:, i], cam_rate[:, i])[0, 1]) for i in range(3)]
    return {"cam_from_imu": M.astype(int).tolist(), "lag_ms": round(float(lag) * 1000, 1),
            "r_xyz": [round(v, 3) for v in r], "rms_dps": round(float(np.sqrt(err)), 2), "frames": int(len(cam_rate))}
