"""Shapes stage outputs into what the workbench draws: arrays and tables in, arrays and tables out.

Pure, so what a chart shows is testable without a notebook; plotting libraries stay in the notebook.
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pycolmap

IGNORED_TINT = np.array([230, 40, 40], np.float32)


def overlay(rgb: np.ndarray, mask: np.ndarray, alpha: float = 0.55) -> np.ndarray:
    """Tint the pixels a training mask ignores (0) so a mask can be judged by eye against its frame."""
    ignored = (mask == 0)[..., None]
    tinted = (1 - alpha) * rgb + alpha * IGNORED_TINT
    return np.where(ignored, tinted, rgb).astype(np.uint8)


def cameras(rec: pycolmap.Reconstruction) -> pl.DataFrame:
    """One row per registered image: its workspace folder (= COLMAP camera), clip, frame and centre in the solve."""
    images = [rec.images[i] for i in rec.reg_image_ids()]
    folder_clip_frame = [(im.name.split("/")[0], *im.name.split("/")[1].removesuffix(".jpg").rsplit("__", 1))
                         for im in images]
    centres = np.array([im.projection_center() for im in images]).reshape(-1, 3)
    return pl.DataFrame({
        "camera": [f for f, _, _ in folder_clip_frame], "clip": [c for _, c, _ in folder_clip_frame],
        "frame": [int(n) for _, _, n in folder_clip_frame],
        "x": centres[:, 0], "y": centres[:, 1], "z": centres[:, 2]}).sort("clip", "camera", "frame")


def points(rec: pycolmap.Reconstruction, limit: int) -> pl.DataFrame:
    """At most `limit` sparse points, evenly strided so the cloud's shape survives the thinning."""
    xyz = np.array([p.xyz for p in rec.points3D.values()]).reshape(-1, 3)
    kept = xyz[:: max(1, -(-len(xyz) // limit))]
    return pl.DataFrame({"x": kept[:, 0], "y": kept[:, 1], "z": kept[:, 2]})
