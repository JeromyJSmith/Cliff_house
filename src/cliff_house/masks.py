"""Stage: masks — SAM 3 concept masks of things that must not shape the scene: people and what they carry.

SAM 3 itself runs as Pixeltable's `sam3_for_segmentation` computed column in the notebook, one column per prompt;
this module is the pure part around it. It turns every prompt's instances into one "unwanted" region and writes it
in the trainers' convention — 0 = ignore the pixel, 255 = use it (3DGRUT, Spirula and LichtFeld all read
single-channel masks this way).

The rules below were each settled by checking clip 041 by eye with the owner (2026-11-12); `person` alone left the
hand with the controller, the belt keys and the yellow strap unmasked, and masked the posters on the walls.

1. **people** — every instance of `people` (`person`, `hand`) scoring ≥ `person_threshold`.
2. **carried** — instances of `carried` (keys, controller, phone, strap, …) scoring ≥ `carried_threshold`, kept only
   if they **overlap** the people region by ≥ `attach_overlap_px` and cover ≤ `carried_max_frac` of the frame.
   Touching is not enough: a pool-skimmer net in a bucket, a bag on the floor and a phone on a counter all sat within
   25 px of the operator in the image with no overlap, while every real item overlapped (the strap at the body's edge
   by 150 px, keys and pockets by thousands).
3. **not pictures of people** — a people instance lying mostly (`depiction_overlap`) inside a `depictions` instance
   (artwork, painting, picture; each ≤ `depiction_max_frac` of the frame) is dropped: posters are walls.
4. **holes filled** — enclosed background pockets ≤ `max_hole_frac` of the frame (a chest device, a strap the
   silhouette went around).
5. **grown** by `grow_px`: SAM 3's 288² mask logits are coarse at full resolution and cut shadowed edges (the dark
   side of a boot) by up to ~40 px.
6. **out to the rim** (fisheye sources only) — within the outer band (radius ≥ `rim_frac` of the half-width) the
   region grows a further `rim_px`, because a person at the edge of the fisheye runs into the image circle where
   SAM 3 stops short (the operator's shoulders and head on both A1 lenses).

Growing only ever removes more pixels from reconstruction.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np
import polars as pl
from scipy import ndimage as ndi


@dataclass(frozen=True)
class Params:
    people: tuple[str, ...] = ("person", "hand")
    carried: tuple[str, ...] = ("keys", "controller", "phone", "radio", "tag", "bag", "strap", "handle", "lanyard")
    depictions: tuple[str, ...] = ("artwork", "painting", "picture")
    model_id: str = "facebook/sam3"
    revision: str = "3c879f39826c281e95690f02c7821c4de09afae7"
    person_threshold: float = 0.5   # SAM 3's default detection threshold
    carried_threshold: float = 0.4  # carried items are small; the overlap rule guards against false hits
    depiction_threshold: float = 0.5
    mask_threshold: float = 0.5
    attach_overlap_px: int = 64     # at full resolution
    carried_max_frac: float = 0.01
    depiction_max_frac: float = 0.25  # a "picture" covering the whole fisheye is a false detection, not a veto
    depiction_overlap: float = 0.5
    max_hole_frac: float = 0.01
    grow_px: int = 24               # at full resolution
    rim_frac: float = 0.9
    rim_px: int = 96
    max_side: int = 1920            # frames are segmented at most this large; masks are resized back

    @property
    def prompts(self) -> tuple[str, ...]:
        """Every prompt, in column order: people, carried, depictions."""
        return (*self.people, *self.carried, *self.depictions)

    @property
    def detection_threshold(self) -> float:
        """The lowest per-group threshold: what SAM 3 is asked for; each group is then filtered to its own."""
        return min(self.person_threshold, self.carried_threshold, self.depiction_threshold)

    def threshold(self, prompt: str) -> float:
        if prompt in self.people:
            return self.person_threshold
        return self.carried_threshold if prompt in self.carried else self.depiction_threshold


def fingerprint(frames_fingerprint: str, params: Params) -> str:
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for part in (frames_fingerprint, json.dumps(asdict(params), sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


def segmentation_size(width: int, height: int, params: Params) -> tuple[int, int]:
    scale = min(1.0, params.max_side / max(width, height))
    return round(width * scale), round(height * scale)


def resize(masks: np.ndarray, shape: tuple[int, int]) -> list[np.ndarray]:
    """(n, h, w) instance masks (n may be 0) → list of bool masks of `shape` (h, w), nearest-neighbour."""
    masks = np.asarray(masks)
    if masks.size == 0:
        return []
    masks = masks.reshape(-1, *masks.shape[-2:])
    return [cv2.resize(m.astype(np.uint8), (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST) > 0
            for m in masks]


def by_group(results: dict[str, dict], shape: tuple[int, int], params: Params) -> dict[str, list[np.ndarray]]:
    """SAM 3 results per prompt ({"scores", "masks"}, as Pixeltable's sam3_for_segmentation returns them) →
    {"people", "carried", "depictions"} instance masks at `shape`, each kept at its group's threshold."""
    groups = {"people": params.people, "carried": params.carried, "depictions": params.depictions}
    out: dict[str, list[np.ndarray]] = {g: [] for g in groups}
    for prompt, res in results.items():
        group = next(g for g, prompts in groups.items() if prompt in prompts)
        keep = np.asarray(res["scores"], dtype=float).reshape(-1) >= params.threshold(prompt)
        out[group].extend(m for m, k in zip(resize(res["masks"], shape), keep) if k)
    return out


def grow(mask: np.ndarray, px: int) -> np.ndarray:
    """Pixels within Euclidean distance `px` of the mask (computed on the mask's bounding box only)."""
    if px <= 0 or not mask.any():
        return mask.copy()
    ys, xs = np.nonzero(mask)
    y0, y1 = max(0, ys.min() - px), min(mask.shape[0], ys.max() + px + 1)
    x0, x1 = max(0, xs.min() - px), min(mask.shape[1], xs.max() + px + 1)
    out = np.zeros_like(mask)
    out[y0:y1, x0:x1] = ndi.distance_transform_edt(~mask[y0:y1, x0:x1]) <= px
    return out


def fill_holes(mask: np.ndarray, max_px: int) -> tuple[np.ndarray, int]:
    """Fill background components that do not touch the image border and have at most `max_px` pixels."""
    labels, n = ndi.label(~mask)
    if n == 0:
        return mask.copy(), 0
    sizes = np.bincount(labels.ravel(), minlength=n + 1)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    fill = sizes <= max_px
    fill[0] = False
    fill[border] = False
    filled = fill[labels]
    return mask | filled, int(filled.sum())


def rim_band(shape: tuple[int, int], frac: float) -> np.ndarray:
    """Pixels at or beyond `frac` of the half-width from the image centre (the fisheye's outer band)."""
    h, w = shape
    y, x = np.ogrid[:h, :w]
    return np.hypot(x - (w - 1) / 2, y - (h - 1) / 2) >= frac * min(h, w) / 2


def combine(people: Sequence[np.ndarray], carried: Sequence[np.ndarray], depictions: Sequence[np.ndarray],
            shape: tuple[int, int], params: Params, fisheye: bool) -> tuple[np.ndarray, dict]:
    """One frame's unwanted region (bool, `shape`) from full-resolution instance masks, and what each rule did."""
    pictures = np.zeros(shape, bool)
    for m in depictions:
        if m.sum() <= params.depiction_max_frac * m.size:
            pictures |= m
    union = np.zeros(shape, bool)
    kept_people = depicted = 0
    for m in people:
        area = m.sum()
        if not area:
            continue
        if (m & pictures).sum() >= params.depiction_overlap * area:
            depicted += 1
            continue
        union |= m
        kept_people += 1
    kept = rejected = 0
    person = union.copy()
    for m in carried:
        if (m & person).sum() >= params.attach_overlap_px and m.sum() <= params.carried_max_frac * m.size:
            union |= m
            kept += 1
        elif m.any():
            rejected += 1
    union, filled = fill_holes(union, int(params.max_hole_frac * union.size))
    union = grow(union, params.grow_px)
    rim = 0
    if fisheye and params.rim_px > 0 and union.any():
        band = rim_band(shape, params.rim_frac)
        if (union & band).any():
            extra = grow(union & band, params.rim_px) & band & ~union
            rim = int(extra.sum())
            union |= extra
    return union, {"people": kept_people, "depicted": depicted, "carried": kept, "carried_rejected": rejected,
                   "filled_px": filled, "rim_px": rim}


def unwanted(instance_masks: Iterable[np.ndarray], shape: tuple[int, int]) -> np.ndarray:
    """Plain union of every instance mask (each (n, h, w) bool, n may be 0) resized to `shape` (h, w)."""
    out = np.zeros(shape, dtype=bool)
    for masks in instance_masks:
        for m in resize(masks, shape):
            out |= m
    return out


def training_mask(unwanted_px: np.ndarray, grow_px: int = 0) -> np.ndarray:
    """uint8 mask: 255 where the trainer may use the pixel, 0 where it must ignore it. `combine` already grows its
    region; `grow_px` is for a plain `unwanted` union."""
    region = grow(unwanted_px.astype(bool), grow_px)
    return np.where(region, 0, 255).astype(np.uint8)


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
