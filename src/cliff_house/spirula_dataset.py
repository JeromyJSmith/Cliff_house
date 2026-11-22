"""Stage: spirula_dataset — the COLMAP dataset Spirula's `train` reads, assembled from poses, frames and training masks.

Spirula (`spirula train`, preset `360-camera`) reads a COLMAP dataset folder:

    <dataset>/images/<lens>/<clip>__<frame:06d>.jpg
    <dataset>/masks/<lens>/<clip>__<frame:06d>.jpg.png      white (255) = keep, black (0) = ignore
    <dataset>/sparse/0/{cameras,images,points3D}.bin        (+ rigs.bin, frames.bin from the rig solve)

Image names in `images.bin` are relative to the image folder, as COLMAP writes them, and a mask is found by the same
relative name plus `.png` (`frame.jpg.png`; Spirula's `docs/datasets.md`, "Masks"). The poses stage already solves in
exactly this naming (`poses.stage_workspace`), so nothing is renamed or re-solved here. The masks are the training_masks
stage's PNGs, which already use the one polarity (0 = ignore, 255 = use), so none is inverted or rewritten: the dataset
links them. Frames and masks are not copied either (the frames stage is ~GB-scale per clip); `build` links them from
the synced stage folders, and only the small files (sparse model, tables, `dataset.json`, `train.json`) go to the bucket.

**What is checked, and stops the stage** (never defaulted around): every registered image's name parses as
`<lens>/<clip>__<frame>.jpg` with a lens we have; its clip was given; its frame file and its training mask exist; the
frame and the mask are both the size of the camera the model gives that image; the mask holds only 0 and 255; and the
fraction of pixels left to train on is not near-empty and not inverted-looking (median over the dataset). Phone clips
are out of scope (owner, 2026-11-13: 360 footage only): their images are named `<clip>/…`, not `lens0|lens1/…`, and are
refused.

**Fingerprint** = the poses stage's fingerprint + each clip's frames and training-mask fingerprints + the registered
image names + the parameters + this module's code. It is computable before any frame is downloaded.

**What this stage does not decide.** Scale: the model's unit is metres through the 71.3 mm factory rig baseline, a hint
and not a survey measurement, so no `gauge.txt` is written (Spirula's own SfM writes one; this dataset did not come from it)
and `train.json` leaves `--scene-center` at Spirula's default. Held-out evaluation: `train.json` does not set it.

Output: `stages/spirula_dataset/<fp>/` — `sparse/0/*.bin`, `dataset.parquet` (one row per image), `dataset.json`
(inputs, rules, acceptance) and `train.json` (the `spirula train` argv). `images/` and `masks/` exist only in the
working copy, as links.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np
import polars as pl
import pycolmap
from PIL import Image

_MODULE_BYTES = Path(__file__).read_bytes()

IMAGE_NAME = re.compile(r"^(?P<lens>[^/]+)/(?P<clip>.+)__(?P<frame>\d{6})\.jpg$")
SPARSE_FILES = ("cameras.bin", "images.bin", "points3D.bin", "rigs.bin", "frames.bin")
REQUIRED_SPARSE = ("cameras.bin", "images.bin", "points3D.bin")


class DatasetError(ValueError):
    """The poses, frames and masks do not make a trainable Spirula dataset."""


@dataclass(frozen=True)
class Params:
    lenses: tuple[str, ...] = ("lens0", "lens1")   # the A1's two fisheyes; the only cameras this stage accepts
    min_use_fraction: float = 0.05                  # an image with less than this left to train on is an error
    min_median_use_fraction: float = 0.40           # a dataset median below this looks like inverted masks (the
                                                    # masks cover people, gear and aircraft body only: most of a frame is kept)
    preset: str = "360-camera"
    iterations: int = 50_000                        # SPEC §5, quality `high`
    steps_per_save: int = 2000


@dataclass(frozen=True)
class ClipInputs:
    """One clip's frames and training masks, both laid out `<lens>/<frame:06d>.{jpg,png}`."""
    clip: str
    frames_dir: Path
    frames_fingerprint: str
    masks_dir: Path
    masks_fingerprint: str


@dataclass(frozen=True)
class Image_:
    name: str          # as in images.bin: <lens>/<clip>__<frame>.jpg
    lens: str
    clip: str
    frame: int
    camera_id: int
    width: int
    height: int
    frame_file: Path
    mask_file: Path


@dataclass(frozen=True)
class Plan:
    poses_fingerprint: str
    sparse_dir: Path
    params: Params
    clips: tuple[ClipInputs, ...]
    images: tuple[Image_, ...]
    fingerprint: str = field(default="")


def parse_image_name(name: str) -> tuple[str, str, int]:
    """`lens0/VID_…_041__000123.jpg` → (`lens0`, `VID_…_041`, 123)."""
    m = IMAGE_NAME.match(name)
    if not m:
        raise DatasetError(f"{name!r} is not a <lens>/<clip>__<frame:06d>.jpg image name")
    return m["lens"], m["clip"], int(m["frame"])


def fingerprint(poses_fingerprint: str, clips: tuple[ClipInputs, ...], names: list[str], params: Params) -> str:
    digest = hashlib.sha256(hashlib.sha256(_MODULE_BYTES).digest())
    parts = (poses_fingerprint,
             json.dumps(sorted((c.clip, c.frames_fingerprint, c.masks_fingerprint) for c in clips)),
             json.dumps(sorted(names)), json.dumps(asdict(params), sort_keys=True))
    for part in parts:
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


def plan(sparse_dir: Path, poses_fingerprint: str, clips: list[ClipInputs], params: Params = Params()) -> Plan:
    """The registered images of the poses model, each tied to its frame and training-mask file (existence checked)."""
    missing = [f for f in REQUIRED_SPARSE if not (sparse_dir / f).is_file()]
    if missing:
        raise DatasetError(f"{sparse_dir}: missing {missing}; the poses stage writes sparse/0 with all of "
                           f"{REQUIRED_SPARSE}")
    by_clip = {c.clip: c for c in clips}
    rec = pycolmap.Reconstruction(sparse_dir)
    if not rec.images:
        raise DatasetError(f"{sparse_dir}: the model has no registered images")
    images, problems = [], []
    for image in sorted(rec.images.values(), key=lambda i: i.name):
        lens, clip, frame = parse_image_name(image.name)
        if lens not in params.lenses:
            raise DatasetError(f"{image.name}: camera folder {lens!r} is not one of {params.lenses}. Phone clips "
                               f"are out of scope (360 footage only).")
        if clip not in by_clip:
            raise DatasetError(f"{image.name}: no frames/masks were given for clip {clip!r} "
                               f"(given: {sorted(by_clip)})")
        c = by_clip[clip]
        frame_file = c.frames_dir / lens / f"{frame:06d}.jpg"
        mask_file = c.masks_dir / lens / f"{frame:06d}.png"
        for what, path in (("frame", frame_file), ("training mask", mask_file)):
            if not path.is_file():
                problems.append(f"{image.name}: {what} {path} does not exist")
        cam = rec.cameras[image.camera_id]
        images.append(Image_(image.name, lens, clip, frame, image.camera_id, int(cam.width), int(cam.height),
                             frame_file, mask_file))
    if problems:
        raise DatasetError(f"{len(problems)} registered images lack a file; first: {problems[:5]}")
    names = [i.name for i in images]
    return Plan(poses_fingerprint, sparse_dir, params, tuple(clips), tuple(images),
                fingerprint(poses_fingerprint, tuple(clips), names, params))


def check(p: Plan) -> pl.DataFrame:
    """Open every frame header and every mask; returns one row per image. Raises DatasetError on the first class of
    problem found (all offending images listed), never records a bad image as acceptable."""
    rows, bad = [], {"frame size": [], "mask size": [], "mask not 0/255": [], "nearly empty": []}
    for i in p.images:
        with Image.open(i.frame_file) as im:
            if im.size != (i.width, i.height):
                bad["frame size"].append(f"{i.name}: {im.size} vs camera {(i.width, i.height)}")
        mask = cv2.imread(str(i.mask_file), cv2.IMREAD_UNCHANGED)
        if mask is None or mask.ndim != 2 or mask.dtype != np.uint8:
            raise DatasetError(f"{i.mask_file}: not an 8-bit single-channel PNG")
        if mask.shape != (i.height, i.width):
            bad["mask size"].append(f"{i.name}: {mask.shape[::-1]} vs camera {(i.width, i.height)}")
            continue
        use = mask == 255
        if int(use.sum() + (mask == 0).sum()) != mask.size:
            bad["mask not 0/255"].append(i.name)
        fraction = float(use.mean())
        if fraction < p.params.min_use_fraction:
            bad["nearly empty"].append(f"{i.name}: {fraction:.3f} left to train on")
        rows.append({"image": i.name, "lens": i.lens, "clip": i.clip, "frame": i.frame, "camera_id": i.camera_id,
                     "width": i.width, "height": i.height, "use_fraction": fraction,
                     "frame_file": str(i.frame_file), "mask_file": str(i.mask_file)})
    problems = {k: v for k, v in bad.items() if v}
    if problems:
        raise DatasetError("; ".join(f"{k}: {len(v)} (e.g. {v[:3]})" for k, v in problems.items()))
    table = pl.DataFrame(rows)
    median = float(table["use_fraction"].median())
    if median < p.params.min_median_use_fraction:
        raise DatasetError(f"median fraction left to train on is {median:.3f}, below "
                           f"{p.params.min_median_use_fraction}: the masks look inverted (255 must mean use)")
    return table


def train_args(dataset_dir: Path, output_prefix: Path, run_name: str, params: Params = Params()) -> list[str]:
    """The `spirula train` argv (after the binary). Headless: `--disable-viewer 1 --keep-viewer-alive 0`, otherwise the
    process never exits. Checkpoints are the resumable ones, written on every `--steps-per-save`."""
    return ["train", params.preset, "--data", str(dataset_dir), "--data-format", "colmap",
            "--image-dir", "images", "--mask-dir", "masks", "--colmap-recon-dir", "sparse/0",
            "--output-dir-prefix", str(output_prefix), "--output-dir-name", run_name,
            "--num-iterations", str(params.iterations), "--steps-per-save", str(params.steps_per_save),
            "--save-only-latest-checkpoint", "1", "--disable-viewer", "1", "--keep-viewer-alive", "0"]


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.unlink(missing_ok=True)
    os.symlink(src.resolve(), dst)


def build(p: Plan, out_dir: Path, output_prefix: Path = Path("training"), table: pl.DataFrame | None = None) -> dict:
    """Write the dataset into `out_dir` (the working copy of `stages/spirula_dataset/<fp>/`); returns `dataset.json`."""
    table = check(p) if table is None else table
    (out_dir / "sparse" / "0").mkdir(parents=True, exist_ok=True)
    for name in SPARSE_FILES:
        if (p.sparse_dir / name).is_file():
            shutil.copy2(p.sparse_dir / name, out_dir / "sparse" / "0" / name)
    for i in p.images:
        _link(i.frame_file, out_dir / "images" / i.name)
        _link(i.mask_file, out_dir / "masks" / f"{i.name}.png")
    table.drop("frame_file", "mask_file").write_parquet(out_dir / "dataset.parquet")
    argv = train_args(out_dir, output_prefix, f"spirula-{p.fingerprint}", p.params)
    per_lens = {lens: int(n) for lens, n in table["lens"].value_counts().iter_rows()}
    meta = {"stage": "spirula_dataset", "fingerprint": p.fingerprint,
            "code_version": hashlib.sha256(_MODULE_BYTES).hexdigest()[:12],
            "poses_fingerprint": p.poses_fingerprint,
            "clips": {c.clip: {"frames": c.frames_fingerprint, "training_masks": c.masks_fingerprint}
                      for c in sorted(p.clips, key=lambda c: c.clip)},
            "params": asdict(p.params),
            "layout": "COLMAP: images/<lens>/<name>.jpg, masks/<lens>/<name>.jpg.png (255 = use, 0 = ignore), sparse/0",
            "scale": "metres via the 71.3 mm factory rig baseline: a hint, not a survey; no gauge.txt written",
            "acceptance": {"images": table.height, "images_per_lens": per_lens,
                           "images_expected": len(p.images),
                           "median_use_fraction": round(float(table["use_fraction"].median()), 4),
                           "min_use_fraction": round(float(table["use_fraction"].min()), 4),
                           "ok": table.height == len(p.images)}}
    (out_dir / "dataset.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    (out_dir / "train.json").write_text(json.dumps({"binary": "spirula", "argv": argv}, indent=2))
    return meta
