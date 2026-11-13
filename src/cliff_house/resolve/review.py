"""Contact sheets of analysis layers for review by eye: each row is one sampled frame, the source then each layer.

They show footage: write them to the stage drive or the private bucket, never the repo.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import polars as pl


def _tile(img: np.ndarray, size: int, label: str) -> np.ndarray:
    if img.ndim == 2:
        img = img.astype(np.float32)
        img = (255 * img / max(float(img.max()), 1.0)).astype(np.uint8) if img.max() > 255 else img.astype(np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    tile = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    cv2.putText(tile, label, (8, 26), 0, 0.7, (255, 255, 255), 2)
    return tile


def layer_sheet(sample_dir: Path, layer_dirs: dict[str, Path], sheet: Path, rows: int = 3, size: int = 360) -> Path:
    """Rows of evenly spaced samples: the sample JPEG, then each layer's PNG for the same index."""
    table = pl.read_parquet(sample_dir / "frames.parquet")
    picks = np.linspace(0, table.height - 1, rows).round().astype(int)
    lines = []
    for k in picks:
        row = table.row(int(k), named=True)
        tiles = [_tile(cv2.imread(str(sample_dir / row["file"])), size, f"src f{row['frame']}")]
        for name, d in layer_dirs.items():
            img = cv2.imread(str(d / f"{int(k):06d}.png"), cv2.IMREAD_UNCHANGED)
            tiles.append(_tile(img, size, name))
        lines.append(np.hstack(tiles))
    sheet.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(sheet), np.vstack(lines), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return sheet
