"""Tables the explorer notebook draws: a COLMAP model and any point-cloud or splat PLY, reduced to Polars frames.

Pure (files in, frames out) so what the explorer shows is reproducible outside a notebook. Clouds are sampled with
an even stride so their shape survives; browsers draw a few hundred thousand points, not tens of millions.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

SH_C0 = 0.28209479177387814   # degree-0 spherical-harmonic constant: splat colour = 0.5 + SH_C0 * f_dc
PLY_TYPES = {"float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8", "uchar": "u1", "uint8": "u1",
             "char": "i1", "int8": "i1", "ushort": "<u2", "short": "<i2", "uint": "<u4", "int": "<i4"}


def _ply_vertices(path: Path) -> np.ndarray:
    """Memory-mapped vertex records of a binary little-endian PLY whose only element is `vertex`."""
    with open(path, "rb") as f:
        header = []
        while (line := f.readline().decode("ascii").strip()) != "end_header":
            header.append(line)
        offset = f.tell()
    if "format binary_little_endian 1.0" not in header:
        raise ValueError(f"{path}: only binary little-endian PLY is read, header says {header[:2]}")
    count = int(next(h.split()[2] for h in header if h.startswith("element vertex")))
    fields = [(h.split()[2], PLY_TYPES[h.split()[1]]) for h in header if h.startswith("property ")]
    return np.memmap(path, dtype=np.dtype(fields), mode="r", offset=offset, shape=(count,))


def _stride(n: int, limit: int) -> slice:
    return slice(None, None, max(1, -(-n // limit)))


def cloud_sample(path: Path, limit: int) -> pl.DataFrame:
    """A coloured point cloud (x, y, z, red, green, blue) → at most `limit` rows: x, y, z, r, g, b."""
    all_vertices = _ply_vertices(path)
    v = all_vertices[_stride(len(all_vertices), limit)]
    return pl.DataFrame({"x": v["x"].astype(np.float32), "y": v["y"].astype(np.float32),
                         "z": v["z"].astype(np.float32), "r": v["red"], "g": v["green"], "b": v["blue"]})


def splat_sample(path: Path, limit: int, min_opacity: float = 0.1) -> pl.DataFrame:
    """A 3D-Gaussian-splat PLY → its visible Gaussians' centres with degree-0 colour, opacity and largest scale.

    Gaussians below `min_opacity` are dropped first: near-transparent ones make no image. On the clip-033 splats
    0.1 keeps 1.3–1.7 M of 5 M; 0.5 kept only 41–100 k, too few to show the scene's shape.
    """
    v = _ply_vertices(path)
    opacity = 1 / (1 + np.exp(-np.asarray(v["opacity"], np.float64)))
    kept = np.flatnonzero(opacity >= min_opacity)
    kept = kept[_stride(len(kept), limit)]
    s = v[kept]
    rgb = np.clip(0.5 + SH_C0 * np.stack([s["f_dc_0"], s["f_dc_1"], s["f_dc_2"]], 1), 0, 1) * 255
    scale = np.exp(np.max(np.stack([s["scale_0"], s["scale_1"], s["scale_2"]], 1), 1))
    return pl.DataFrame({"x": s["x"], "y": s["y"], "z": s["z"], "r": rgb[:, 0].astype(np.uint8),
                         "g": rgb[:, 1].astype(np.uint8), "b": rgb[:, 2].astype(np.uint8),
                         "opacity": opacity[kept].astype(np.float32), "scale_m": scale.astype(np.float32)})


def model_tables(rec) -> tuple[pl.DataFrame, pl.DataFrame]:
    """A pycolmap Reconstruction → (cameras, points).

    cameras: one row per registered image — lens, clip, frame, centre, viewing direction, observed-point count.
    points: every 3D point — position, colour, reprojection error, track length (how many images see it).
    """
    rows = []
    for image_id in rec.reg_image_ids():
        im = rec.images[image_id]
        lens, stem = im.name.split("/")
        clip, frame = stem.removesuffix(".jpg").rsplit("__", 1)
        centre = im.projection_center()
        look = im.viewing_direction()
        rows.append((image_id, lens, clip, int(frame), *centre, *look, im.num_points3D))
    cameras = pl.DataFrame(rows, orient="row", schema={
        "image_id": pl.Int64, "lens": pl.String, "clip": pl.String, "frame": pl.Int64, "x": pl.Float64,
        "y": pl.Float64, "z": pl.Float64, "dx": pl.Float64, "dy": pl.Float64, "dz": pl.Float64,
        "n_points": pl.Int64}).sort("clip", "lens", "frame")
    ids = np.fromiter(rec.points3D.keys(), np.int64)
    pts = [rec.points3D[i] for i in ids]
    xyz = np.array([p.xyz for p in pts]).reshape(-1, 3)
    rgb = np.array([p.color for p in pts], np.uint8).reshape(-1, 3)
    points = pl.DataFrame({"point_id": ids, "x": xyz[:, 0], "y": xyz[:, 1], "z": xyz[:, 2],
                           "r": rgb[:, 0], "g": rgb[:, 1], "b": rgb[:, 2],
                           "error_px": np.array([p.error for p in pts], np.float32),
                           "track_length": np.array([p.track.length() for p in pts], np.int32)})
    return cameras, points
