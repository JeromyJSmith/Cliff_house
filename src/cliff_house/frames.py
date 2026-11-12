"""Stage: frames — sharpness-selected frames from each source video, one rig-consistent set per clip.

A source is one file with one or more synchronized video streams (the A1's two fisheye lenses, or one phone stream).
Frames are chosen per time window as the candidate whose *least* sharp stream is sharpest, so every chosen timestamp
is usable on every stream and the lenses stay paired as a rig. Selection follows the sharpness-aware extraction of
lichtfeld-360-plugin (Laplacian scoring of candidates within each interval), reimplemented here.

The transfer to SDR is part of the source description, not a branch: SDR sources pass through, HLG (iPhone HDR)
goes through the BT.2100 HLG inverse OETF, BT.2020→BT.709 primaries, a Reinhard tone map and the BT.709 OETF —
done in NumPy because the available ffmpeg builds lack zscale and molab cannot run libplacebo (Vulkan).
"""
from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator, Literal

import cv2
import numpy as np
import polars as pl

Transfer = Literal["sdr", "hlg"]

SCORE_WIDTH = 640


@dataclass(frozen=True)
class Stream:
    index: int     # ffmpeg video stream index within the file (0:v:<index>)
    camera: str    # stable camera id within the source, e.g. "lens0", "phone"


@dataclass(frozen=True)
class Source:
    path: Path
    sha256: str
    streams: tuple[Stream, ...]
    transfer: Transfer
    width: int
    height: int


@dataclass(frozen=True)
class Params:
    candidate_fps: float = 4.0   # frames scored per second of video
    target_fps: float = 1.0      # frames kept per second of video (one per window)
    jpeg_quality: int = 95


_TRANSFER_BY_COLOR_TRC = {"arib-std-b67": "hlg"}  # anything else is treated as SDR BT.709


def probe(path: Path, sha256: str, ffprobe: str = "ffprobe") -> Source:
    """Describe a video file from its own metadata: every picture stream (cover art excluded), size and transfer."""
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v", "-show_entries",
                          "stream=index,width,height,color_transfer:stream_disposition=attached_pic",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    streams = [s for s in json.loads(out.stdout)["streams"] if not s.get("disposition", {}).get("attached_pic")]
    sizes = {(s["width"], s["height"]) for s in streams}
    transfers = {_TRANSFER_BY_COLOR_TRC.get(s.get("color_transfer"), "sdr") for s in streams}
    if len(sizes) != 1 or len(transfers) != 1:
        raise ValueError(f"{path}: streams differ in size {sizes} or transfer {transfers}; not one rig")
    (width, height), (transfer,) = sizes.pop(), transfers
    return Source(path=path, sha256=sha256, transfer=transfer, width=width, height=height,
                  streams=tuple(Stream(i, f"lens{i}") for i in range(len(streams))))


def fingerprint(source_sha256: str, params: Params) -> str:
    """Identity of one source's frames: the source bytes, this module's code and the parameters. Stream layout and
    transfer are functions of the source bytes, so they need not appear — and the fingerprint is computable before
    the (large) source is downloaded."""
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for part in (source_sha256, json.dumps(asdict(params), sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


# --- decoding -------------------------------------------------------------------------------------------------------

_PIX_FMTS = {(1, np.dtype(np.uint8)): "gray", (3, np.dtype(np.uint8)): "rgb24", (3, np.dtype(np.uint16)): "rgb48le"}


def _decode(path: Path, stream: int, vf: str, width: int, height: int, channels: int, dtype: np.dtype,
            ffmpeg: str) -> Iterator[np.ndarray]:
    pix_fmt = _PIX_FMTS[(channels, np.dtype(dtype))]
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", f"0:v:{stream}", "-vf", vf,
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", pix_fmt, "-"]
    frame_bytes = width * height * channels * np.dtype(dtype).itemsize
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        while chunk := proc.stdout.read(frame_bytes):
            if len(chunk) != frame_bytes:
                raise RuntimeError(f"short frame from {path} stream {stream}: {len(chunk)} of {frame_bytes} bytes")
            yield np.frombuffer(chunk, dtype=dtype).reshape(height, width, channels)
        err = proc.stderr.read().decode()
    if proc.returncode:
        raise RuntimeError(f"ffmpeg failed on {path} stream {stream}: {err[-2000:]}")


def sharpness(rgb: np.ndarray) -> float:
    """Laplacian variance of a downscaled grey image; comparable across frames of one stream."""
    grey = cv2.cvtColor((rgb >> 8).astype(np.uint8) if rgb.dtype == np.uint16 else rgb, cv2.COLOR_RGB2GRAY)
    w = min(SCORE_WIDTH, grey.shape[1])
    small = cv2.resize(grey, (w, round(grey.shape[0] * w / grey.shape[1])), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


def best_in_window(scores: np.ndarray) -> int:
    """Index of the candidate whose least-sharp stream is sharpest; scores has shape (candidates, streams)."""
    return int(np.argmax(scores.min(axis=1)))


# --- transfer to SDR ------------------------------------------------------------------------------------------------

_BT2020_TO_BT709 = np.array([[1.6605, -0.5876, -0.0728],
                             [-0.1246, 1.1329, -0.0083],
                             [-0.0182, -0.1006, 1.1187]])


def hlg_inverse_oetf(e: np.ndarray) -> np.ndarray:
    """BT.2100 HLG non-linear signal E' in [0, 1] → normalized scene-linear light E in [0, 1]."""
    a, b, c = 0.17883277, 0.28466892, 0.55991073
    e = np.clip(e, 0.0, 1.0)
    return np.where(e <= 0.5, e * e / 3.0, (np.exp((e - c) / a) + b) / 12.0)


def bt709_oetf(l: np.ndarray) -> np.ndarray:
    l = np.clip(l, 0.0, 1.0)
    return np.where(l < 0.018, 4.5 * l, 1.099 * np.power(l, 0.45) - 0.099)


def hlg_to_sdr(rgb16: np.ndarray, exposure: float = 4.0) -> np.ndarray:
    """16-bit HLG/BT.2020 RGB → 8-bit BT.709 RGB (Reinhard tone map on scene-linear light)."""
    linear = hlg_inverse_oetf(rgb16.astype(np.float32) / 65535.0) @ _BT2020_TO_BT709.T
    mapped = (linear * exposure) / (1.0 + linear * exposure)
    return np.round(bt709_oetf(mapped) * 255.0).astype(np.uint8)


_TRANSFERS: dict[Transfer, tuple[np.dtype, Callable[[np.ndarray], np.ndarray]]] = {
    "sdr": (np.dtype(np.uint8), lambda rgb: rgb),
    "hlg": (np.dtype(np.uint16), hlg_to_sdr),
}


# --- extraction -----------------------------------------------------------------------------------------------------

def extract(source: Source, params: Params, out_dir: Path, ffmpeg: str = "ffmpeg") -> pl.DataFrame:
    """One pass: decode all streams in lockstep, keep each window's best candidate, write it; returns the frame table
    (one row per stream per kept frame). Memory is bounded by one window of full-resolution frames."""
    dtype, to_sdr = _TRANSFERS[source.transfer]
    window = max(1, round(params.candidate_fps / params.target_fps))
    vf = f"fps={params.candidate_fps}"
    decoders = [_decode(source.path, s.index, vf, source.width, source.height, 3, dtype, ffmpeg)
                for s in source.streams]
    for s in source.streams:
        (out_dir / s.camera).mkdir(parents=True, exist_ok=True)
    # Streams of one file can end a frame apart; zip stops at the shortest, which drops only that trailing frame.
    candidates = enumerate(zip(*decoders))
    rows = []
    for k, batch in enumerate(itertools.batched(candidates, window)):
        scores = np.array([[sharpness(frame) for frame in frames] for _, frames in batch])
        pick = best_in_window(scores)
        candidate, frames = batch[pick]
        for col, (s, frame) in enumerate(zip(source.streams, frames, strict=True)):
            name = f"{s.camera}/{k:06d}.jpg"
            cv2.imwrite(str(out_dir / name), cv2.cvtColor(to_sdr(frame), cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_JPEG_QUALITY, params.jpeg_quality])
            rows.append({"camera": s.camera, "frame": k, "candidate": candidate,
                         "t_ms": round(candidate * 1000 / params.candidate_fps),
                         "sharpness": float(scores[pick, col]), "file": name})
    table = pl.DataFrame(rows, schema={"camera": pl.String, "frame": pl.Int64, "candidate": pl.Int64,
                                       "t_ms": pl.Int64, "sharpness": pl.Float64, "file": pl.String})
    table.write_parquet(out_dir / "frames.parquet")
    return table
