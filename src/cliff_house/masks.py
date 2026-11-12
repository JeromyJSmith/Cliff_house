"""Stage: masks — SAM 3 concept masks of things that must not shape the scene (the operator, passers-by).

SAM 3 itself runs as Pixeltable's `sam3_for_segmentation` computed column in the notebook; this module is the pure
part around it: union every instance of every prompt into one "unwanted" mask, grow it so soft person edges do not
leak into training, and write it in the trainers' convention — 0 = ignore the pixel, 255 = use it (3DGRUT, Spirula
and LichtFeld all read single-channel masks this way).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import polars as pl


@dataclass(frozen=True)
class Params:
    prompts: tuple[str, ...] = ("person",)
    model_id: str = "facebook/sam3"
    revision: str = "3c879f39826c281e95690f02c7821c4de09afae7"
    threshold: float = 0.5
    mask_threshold: float = 0.5
    grow_px: int = 12            # dilation at full resolution; people's soft edges and motion blur
    max_side: int = 1920         # frames are segmented at most this large; masks are resized back


def fingerprint(frames_fingerprint: str, params: Params) -> str:
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for part in (frames_fingerprint, json.dumps(asdict(params), sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


def segmentation_size(width: int, height: int, params: Params) -> tuple[int, int]:
    scale = min(1.0, params.max_side / max(width, height))
    return round(width * scale), round(height * scale)


def unwanted(instance_masks: Iterable[np.ndarray], shape: tuple[int, int]) -> np.ndarray:
    """Union of every instance mask (each (n, h, w) bool, n may be 0) resized to `shape` (h, w)."""
    out = np.zeros(shape, dtype=bool)
    for masks in instance_masks:
        for m in np.asarray(masks, dtype=bool).reshape(-1, *np.asarray(masks).shape[-2:]):
            out |= cv2.resize(m.astype(np.uint8), (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    return out


def training_mask(unwanted_px: np.ndarray, grow_px: int) -> np.ndarray:
    """uint8 mask: 255 where the trainer may use the pixel, 0 where it must ignore it (grown unwanted region)."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow_px + 1, 2 * grow_px + 1))
    grown = cv2.dilate(unwanted_px.astype(np.uint8), kernel) > 0
    return np.where(grown, 0, 255).astype(np.uint8)


def write(rows: Iterable[tuple[str, int, np.ndarray]], out_dir: Path) -> pl.DataFrame:
    """rows: (camera, frame, training mask). Writes <camera>/<frame:06d>.png and masks.parquet."""
    records = []
    for camera, frame, mask in rows:
        name = f"{camera}/{frame:06d}.png"
        (out_dir / camera).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_dir / name), mask)
        records.append({"camera": camera, "frame": frame, "ignored_fraction": float((mask == 0).mean()),
                        "file": name})
    table = pl.DataFrame(records, schema={"camera": pl.String, "frame": pl.Int64, "ignored_fraction": pl.Float64,
                                          "file": pl.String})
    table.write_parquet(out_dir / "masks.parquet")
    return table
