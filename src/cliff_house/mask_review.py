"""Review sheets of the full ignore-mask a frame gets: rigid parts (gear template of its position plus the rim),
the aircraft body and people. They show footage: write them to the stage drive or the private bucket, never the repo.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import polars as pl


def review_sheet(out_dir: Path, manifest: Path, lens: str, clips: list[str], sheet: Path, per_clip: int = 4,
                 body_mask: Path | None = None, people: dict[str, Path] | None = None) -> Path:
    """Review sheet of the mask each frame really gets: the gear template of its position plus the rim (green), the
    aircraft-body mask (blue) and, where given, the people masks of that clip (red, one PNG per source frame).
    Frames are spread evenly over each clip. It shows footage: keep it out of the public repo."""
    man = pl.read_parquet(manifest).filter(pl.col("cam") == lens)
    tmpl = {f.stem: cv2.imread(str(f), cv2.IMREAD_GRAYSCALE) > 0
            for f in out_dir.glob("*.png") if f.stem != "rim"}
    body = cv2.imread(str(body_mask), cv2.IMREAD_GRAYSCALE) > 0 if body_mask else None
    rows = []
    for suffix in clips:
        r = man.filter(pl.col("clip").str.ends_with(f"_{suffix}")).row(0, named=True)
        pos = pl.read_parquet(out_dir / "positions" / f"{r['clip']}.parquet")
        cap = cv2.VideoCapture(str(manifest.parent / r["fingerprint"] / r["clip"] / f"{lens}.mp4"))
        tiles = []
        for i in np.linspace(0, r["packets"] - 1, per_clip).round().astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
            ok, frame = cap.read()
            name = pos["position"][int(i)]
            layers = [(tmpl[name], (0, 255, 0))]
            if body is not None:
                layers.append((body, (255, 80, 0)))
            pdir = (people or {}).get(suffix)
            if pdir and (pdir / f"{i:06d}.png").exists():
                layers.append((cv2.imread(str(pdir / f"{i:06d}.png"), cv2.IMREAD_GRAYSCALE) >= 128, (0, 0, 255)))
            for m, colour in layers:
                frame[m] = (0.45 * frame[m] + 0.55 * np.array(colour)).astype(np.uint8)
            tile = cv2.resize(frame, (480, 480), interpolation=cv2.INTER_AREA)
            cv2.putText(tile, f"{suffix} f{i} {name}", (8, 28), 0, 0.8, (255, 255, 255), 2)
            tiles.append(tile)
        rows.append(np.hstack(tiles))
    sheet.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(sheet), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return sheet
