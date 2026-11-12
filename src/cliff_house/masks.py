"""Stage: masks — SAM 3 people masks (the person and everything on them) for every source frame of one lens.

SAM 3 (`facebook/sam3`) segments every instance of a text concept. This stage asks it, frame by frame, for people
and for the things people carry, and writes one mask per source frame at the source resolution. The rigid landing
gear has its own static per-lens mask (`cliff_house.static_mask`); the final ignore-mask for a frame is
people ∪ gear (docs/resolve-pipeline.md §2a).

What goes into the mask, per frame:

1. **people**: every instance of the `people` prompts (`person`, `hand`) above `person_threshold`. `hand` is there
   because a hand holding something at the edge of the body can fall outside the `person` silhouette.
2. **carried**: instances of the `carried` prompts (keys, controller, phone, a strap, a bag, …) above
   `carried_threshold`, kept **only if they touch the people mask** grown by `attach_px` and are no larger than
   `carried_max_frac` of the frame. A carried thing hangs on someone; the same prompts elsewhere in the room (a
   speaker reads as an "electronic device") are not people, and a large neighbour (a sofa cushion read as a "bag")
   is not carried.
3. **holes filled**: background pockets fully enclosed by the mask and smaller than `max_hole_frac` of the frame
   (a strap or a chest device the silhouette went around) become mask.
4. **grown** by `grow_px` (Euclidean), for soft edges and motion blur. Growing only ever removes more pixels from
   reconstruction.

The prompts are project data: the project TOML's `[masks]` table sets `people` and `carried` (what the people in
that footage carry), overriding the defaults below; they are part of the parameters and so of the fingerprint.

Why per frame and not SAM 3's video tracker: on clip 041 the tracker's mask for the operator lost the hand holding
the controller (frame 0), while the per-frame detector kept it. The stage keeps only the union, so object identities
across frames are not needed, and the per-frame check "a mask on every cam0 frame" is in the acceptance.

It runs on this Mac's GPU through PyTorch MPS, in the `sam3` pixi environment. Meta's own `sam3` package requires
CUDA, so the model runs through the Transformers port (`Sam3Model`, same checkpoint). The vision backbone runs once
per frame and every prompt reuses its features. Frames are decoded by ffmpeg straight to SAM 3's 1008² input, and
masks are upsampled from SAM 3's output to the source size. Run it with
`pixi run -e sam3 masks <project.toml> <clip> <lens>`.

Contract (same as the Resolve mask passes, docs/resolve-pipeline.md §2):

    stages/masks/<fingerprint>/<clip>/<lens>/
        000000.png …   one per SOURCE frame, 0-based; frame i is at t_ms = round(i·1001/30) (29.97 fps);
                       8-bit L, 255 = person, 0 = keep; full source resolution (3840² fisheye, unrectified)
        frames.parquet frame, t_ms, file, coverage, people, carried, carried_rejected, filled_px
        pass.json      pass, use = reconstruction, fingerprint, input, params, versions, seconds, acceptance

Fingerprint = SHA-256 of (lens MP4 SHA-256, this module's code, parameters), first 16 hex — computable from the remux
manifest before anything runs. A fingerprint directory that exists is never written again: with `pass.json` it is
done and skipped; without it, it is an interrupted run, kept for inspection, and the stage refuses to touch it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np
import polars as pl
from PIL import Image
from scipy import ndimage as ndi

STAGE = "masks"
PASS = "mask_people"   # the class this stage fills; acceptance comes from the project config's [acceptance.mask_people]
USE = "reconstruction"
FPS_NUM, FPS_DEN = 30000, 1001


@dataclass(frozen=True)
class Params:
    people: tuple[str, ...] = ("person", "hand")
    carried: tuple[str, ...] = ("keys", "controller", "phone", "radio", "tag", "bag", "strap", "handle", "lanyard")
    person_threshold: float = 0.5   # SAM 3's default detection threshold
    carried_threshold: float = 0.4  # lower: carried items are small, and the attach rule guards against false hits
    mask_threshold: float = 0.5
    attach_px: int = 48             # a carried instance must come within this distance of the people mask
    carried_max_frac: float = 0.01  # and be no larger than this fraction of the frame
    max_hole_frac: float = 0.01     # enclosed background pockets up to this fraction of the frame are filled
    grow_px: int = 8
    model_id: str = "facebook/sam3"
    revision: str = "3c879f39826c281e95690f02c7821c4de09afae7"
    model_size: int = 1008          # SAM 3's input size; frames are decoded straight to it
    dtype: str = "float32"
    device: str = "mps"


# --- pure parts (tested without torch) ------------------------------------------------------------------------------

def code_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def fingerprint(input_sha256: str, params: Params, code: str | None = None) -> str:
    """Identity of one lens's masks: the lens MP4's bytes, this module's code and the parameters."""
    digest = hashlib.sha256()
    for part in (code or code_sha256(), input_sha256, json.dumps(asdict(params), sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


def t_ms(frame: int) -> int:
    """Presentation time of 0-based source frame `frame` at 29.97 fps, in whole milliseconds."""
    return round(frame * 1000 * FPS_DEN / FPS_NUM)


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
    """Fill background components that do not touch the image border and have at most `max_px` pixels.
    Returns (filled mask, pixels filled)."""
    labels, n = ndi.label(~mask)
    if n == 0:
        return mask.copy(), 0
    sizes = np.bincount(labels.ravel(), minlength=n + 1)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    fill = (sizes <= max_px)
    fill[0] = False
    fill[border] = False
    filled = fill[labels]
    return mask | filled, int(filled.sum())


def combine(people: Sequence[np.ndarray], carried: Sequence[np.ndarray], params: Params) -> tuple[np.ndarray, dict]:
    """One frame's mask (uint8, 255 = subject) from bool instance masks of the people and carried prompts."""
    shape = (people[0] if len(people) else carried[0]).shape if (len(people) or len(carried)) else None
    if shape is None:
        raise ValueError("combine needs the frame shape: pass at least one (possibly empty) instance mask")
    union = np.zeros(shape, bool)
    for m in people:
        union |= m
    kept = rejected = 0
    if union.any() and len(carried):
        near = grow(union, params.attach_px)
        limit = params.carried_max_frac * union.size
        for m in carried:
            if (m & near).any() and m.sum() <= limit:
                union |= m
                kept += 1
            else:
                rejected += 1
    else:
        rejected = sum(1 for m in carried if m.any())
    union, filled = fill_holes(union, int(params.max_hole_frac * union.size))
    union = grow(union, params.grow_px)
    stats = {"people": sum(1 for m in people if m.any()), "carried": kept, "carried_rejected": rejected,
             "filled_px": filled}
    return np.where(union, 255, 0).astype(np.uint8), stats


def coverage(mask: np.ndarray) -> float:
    """Fraction of the frame that is subject (> 50 %), the same measure the Resolve passes use."""
    return float((mask > 127).mean())


def write_png(path: Path, mask: np.ndarray) -> None:
    if mask.dtype != np.uint8 or mask.ndim != 2:
        raise ValueError(f"mask must be 2-D uint8, got {mask.dtype} {mask.shape}")
    Image.fromarray(mask).save(path, compress_level=6)  # 2-D uint8 is mode L


def acceptance(table: pl.DataFrame, expected_frames: int, rule: dict) -> dict:
    """The stage's acceptance from its frame table and the project's `[acceptance.mask_people]` rule:
    one mask per source frame; a mask on every frame when `every_frame`; median coverage inside `coverage`."""
    n = table.height
    frames_ok = n == expected_frames and table["frame"].to_list() == list(range(expected_frames))
    empty = table.filter(pl.col("coverage") == 0)["frame"].to_list()
    median = float(table["coverage"].median()) if n else 0.0
    every = rule.get("every_frame", False)
    checks = {
        "frame_count": {"ok": frames_ok, "frames": n, "expected": expected_frames},
        "every_frame": {"ok": not (every and empty), "required": every, "empty_frames": len(empty),
                        "first_empty": empty[:20]},
    }
    if "coverage" in rule:
        lo, hi = rule["coverage"]
        checks["coverage"] = {"ok": lo <= median <= hi, "median": median, "band": [lo, hi],
                              "min": float(table["coverage"].min()) if n else 0.0,
                              "max": float(table["coverage"].max()) if n else 0.0}
    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


def compare(a_dir: Path, b_dir: Path, frames: list[int] | None = None) -> pl.DataFrame:
    """Per-frame agreement of two mask folders with the same `<frame:06d>.png` naming (subject > 127):
    IoU, and each side's pixels the other lacks as a fraction of the frame. Frames missing on either side are
    skipped."""
    names = sorted(p.name for p in a_dir.glob("[0-9]*.png"))
    if frames is not None:
        names = [f"{f:06d}.png" for f in frames]
    rows = []
    for name in names:
        if not (a_dir / name).exists() or not (b_dir / name).exists():
            continue
        a = np.asarray(Image.open(a_dir / name)) > 127
        b = np.asarray(Image.open(b_dir / name)) > 127
        inter, union = int((a & b).sum()), int((a | b).sum())
        rows.append({"frame": int(name[:6]), "iou": inter / union if union else 1.0,
                     "a_coverage": float(a.mean()), "b_coverage": float(b.mean()),
                     "a_only": float((a & ~b).mean()), "b_only": float((b & ~a).mean())})
    return pl.DataFrame(rows, schema={"frame": pl.Int64, "iou": pl.Float64, "a_coverage": pl.Float64,
                                      "b_coverage": pl.Float64, "a_only": pl.Float64, "b_only": pl.Float64})


# --- decoding -------------------------------------------------------------------------------------------------------

def decode(path: Path, size: int, ffmpeg: str = "ffmpeg") -> Iterator[np.ndarray]:
    """Every frame of the file's first video stream in order (no frame-rate conversion), resized to size² RGB uint8,
    from one ffmpeg process."""
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", "0:v:0", "-vf",
           f"scale={size}:{size}:flags=area", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    frame_bytes = size * size * 3
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        while chunk := proc.stdout.read(frame_bytes):
            if len(chunk) != frame_bytes:
                raise RuntimeError(f"short frame from {path}: {len(chunk)} of {frame_bytes} bytes")
            yield np.frombuffer(chunk, np.uint8).reshape(size, size, 3)
        err = proc.stderr.read().decode()
    if proc.returncode:
        raise RuntimeError(f"ffmpeg failed on {path}: {err[-2000:]}")


def probe_size(path: Path, ffprobe: str = "ffprobe") -> tuple[int, int]:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["height"]), int(s["width"])


# --- model ----------------------------------------------------------------------------------------------------------

class Segmenter:
    """SAM 3 on one device: the backbone once per frame, then every prompt on the cached features."""

    def __init__(self, params: Params):
        import torch
        from transformers import Sam3Model, Sam3Processor

        self.torch, self.params = torch, params
        dtype = getattr(torch, params.dtype)
        self.model = Sam3Model.from_pretrained(params.model_id, revision=params.revision, dtype=dtype)
        self.model = self.model.to(params.device).eval()
        self.processor = Sam3Processor.from_pretrained(params.model_id, revision=params.revision)
        prompts = list(params.people) + list(params.carried)
        self.text = {p: self.processor(text=p, return_tensors="pt").to(params.device) for p in prompts}

    def __call__(self, rgb: np.ndarray, size: tuple[int, int]) -> tuple[list[np.ndarray], list[np.ndarray]]:
        """(people instance masks, carried instance masks) at `size` (h, w), bool, on the CPU."""
        torch, p = self.torch, self.params
        inputs = self.processor(images=rgb, return_tensors="pt").to(p.device)
        out: dict[str, list[np.ndarray]] = {}
        with torch.inference_mode():
            vision = self.model.get_vision_features(pixel_values=inputs.pixel_values.to(self.model.dtype))
            for prompt, text in self.text.items():
                o = self.model(vision_embeds=vision, **text)
                threshold = p.person_threshold if prompt in p.people else p.carried_threshold
                r = self.processor.post_process_instance_segmentation(
                    o, threshold=threshold, mask_threshold=p.mask_threshold, target_sizes=[list(size)])[0]
                out[prompt] = list(r["masks"].bool().cpu().numpy())
        return ([m for q in p.people for m in out[q]], [m for q in p.carried for m in out[q]])


# --- stage ----------------------------------------------------------------------------------------------------------

def _finish(out_dir: Path, frame: int, people, carried, params: Params) -> dict:
    mask, stats = combine(people, carried, params)
    name = f"{frame:06d}.png"
    write_png(out_dir / name, mask)
    return {"frame": frame, "t_ms": t_ms(frame), "file": name, "coverage": coverage(mask), **stats}


def run(lens_mp4: Path, input_sha256: str, n_frames: int, out_root: Path, clip: str, lens: str, rule: dict,
        params: Params = Params(), ffmpeg: str = "ffmpeg", extra: dict | None = None,
        frames: Sequence[int] | None = None) -> dict:
    """Mask one lens of one clip into out_root/<fp>/<clip>/<lens>/; returns the pass record (existing or new).
    `frames` limits the run to those source frames (a spot check, which then fails the frame-count acceptance)."""
    fp = fingerprint(input_sha256, params)
    out_dir = out_root / fp / clip / lens
    record_path = out_dir / "pass.json"
    if record_path.exists():  # done for these bytes, this code and these parameters; never overwritten
        return json.loads(record_path.read_text())
    if out_dir.exists():
        raise FileExistsError(f"{out_dir} exists without pass.json (an interrupted run). It is kept as it is; "
                              "inspect it and move it aside yourself before rerunning.")
    out_dir.mkdir(parents=True)

    import torch
    import transformers

    wanted = set(frames) if frames is not None else None
    size = probe_size(lens_mp4)
    t0 = time.monotonic()
    seg = Segmenter(params)
    t_loaded = time.monotonic()
    decoded = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = []
        for frame, rgb in enumerate(decode(lens_mp4, params.model_size, ffmpeg)):
            decoded += 1
            if wanted is not None and frame not in wanted:
                continue
            people, carried = seg(rgb, size)
            pending.append(pool.submit(_finish, out_dir, frame, people, carried, params))
            if frame % 50 == 0:
                print(f"{clip}/{lens} frame {frame}/{n_frames} {time.monotonic() - t_loaded:.0f}s", flush=True)
        rows = [f.result() for f in pending]
    t_done = time.monotonic()
    if decoded != n_frames:
        raise RuntimeError(f"{lens_mp4}: decoded {decoded} frames, the remux manifest counts {n_frames}")
    table = pl.DataFrame(rows, schema={"frame": pl.Int64, "t_ms": pl.Int64, "file": pl.String,
                                       "coverage": pl.Float64, "people": pl.Int64, "carried": pl.Int64,
                                       "carried_rejected": pl.Int64, "filled_px": pl.Int64}).sort("frame")
    table.write_parquet(out_dir / "frames.parquet")
    record = {
        "stage": STAGE, "pass": PASS, "use": USE, "fingerprint": fp, "clip": clip, "lens": lens,
        "input": {"path": str(lens_mp4), "sha256": input_sha256, "frames": n_frames, "size": list(size)},
        "params": asdict(params), "code_sha256": code_sha256(),
        "versions": {"torch": torch.__version__, "transformers": transformers.__version__,
                     "python": sys.version.split()[0]},
        "format": {"mask": "8-bit L PNG, 255 = person, source resolution", "frame": "0-based source frame",
                   "t_ms": "round(frame * 1001 / 30)"},
        "seconds": {"load": round(t_loaded - t0, 1), "segment": round(t_done - t_loaded, 1),
                    "per_frame": round((t_done - t_loaded) / max(1, table.height), 3)},
        "acceptance": acceptance(table, n_frames, rule),
        **(extra or {}),
    }
    record_path.write_text(json.dumps(record, indent=2))
    return record


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("config", type=Path, help="project TOML ([stages] local_root, remux_manifest; [acceptance.mask_people])")
    ap.add_argument("clip", help="clip name or unique suffix, e.g. 041")
    ap.add_argument("lens", help="cam0 or cam1")
    ap.add_argument("--out", type=Path, help="stage root to write to instead of <local_root>/masks (spot checks)")
    ap.add_argument("--frames", help="comma-separated source frames only (a spot check; fails frame-count acceptance)")
    args = ap.parse_args(argv)

    config = tomllib.loads(args.config.read_text())
    prompts = {k: tuple(v) for k, v in config.get(STAGE, {}).items() if k in ("people", "carried")}
    params = Params(**prompts)
    stages = Path(config["stages"]["local_root"])
    remux_manifest = Path(config["stages"]["remux_manifest"])
    # The rule is per lens: the operator is in view on the lens listed in `lenses` (default every lens).
    rule = dict(config.get("acceptance", {}).get(PASS, {}))
    if args.lens not in rule.pop("lenses", [args.lens]):
        rule = {}
    manifest = pl.read_parquet(remux_manifest)
    rows = manifest.filter(pl.col("clip").str.ends_with(args.clip) & (pl.col("cam") == args.lens))
    if rows.height != 1:
        sys.exit(f"{args.clip}/{args.lens}: {rows.height} matches in {remux_manifest}")
    row = rows.row(0, named=True)
    lens_mp4 = remux_manifest.parent / row["fingerprint"] / row["clip"] / f"{args.lens}.mp4"
    extra = {"config": {"path": str(args.config), "sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
                        "rule": rule},
             "remux": {"manifest": str(remux_manifest), "fingerprint": row["fingerprint"], "packets": row["packets"]}}
    frames = [int(f) for f in args.frames.split(",")] if args.frames else None
    record = run(lens_mp4, row["sha256"], row["packets"], args.out or stages / STAGE, row["clip"], args.lens, rule,
                 params=params, extra=extra, frames=frames)
    print(json.dumps({k: record[k] for k in ("fingerprint", "clip", "lens", "seconds", "acceptance")}, indent=2))
    if not record["acceptance"]["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
