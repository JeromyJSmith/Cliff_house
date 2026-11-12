"""Stage: static_mask — one mask per lens for parts of the aircraft that never move relative to that lens.

    pixi run python -m cliff_house.static_mask configs/resolve/<project>.toml <class>

Mask class "landing_gear" on the A1: the white landing-gear struts and feet sit on the left and right rim of the
downward lens (cam0) in every frame of every clip, because they are bolted to the camera. Tracking them frame by
frame (Magic Mask, SAM) re-discovers the same pixels thousands of times and can drift onto white walls next to them.
A rigid part needs one mask per lens, derived once and checked against every clip.

Derivation (no Resolve, no model):
1. For every clip of the remux manifest, the per-pixel temporal median of `frames_per_clip` evenly spaced frames
   (at `work_size`). The moving scene averages to texture-less mush; parts fixed to the lens stay sharp.
2. The pooled median of those clip medians, across indoor and outdoor clips.
3. Whiteness = V − S (HSV) of the pooled median: the gear is white and unsaturated, the averaged scene is not.
   Candidate = whiteness ≥ `whiteness_min` inside the rim band (r ≥ `rim_band` · R), components ≥ `min_area_px`,
   closed and then dilated by `dilate_px` at full resolution (a conservative ignore-mask).
4. A candidate component is kept only if it is whiter than the ring around it (`contrast_min`) in **every clip's
   own median**: a rigid part is at the same place in every clip, an averaging artefact of the scene is not.
5. Checks: the kept mask passes the same test per clip, and per frame on `check_frames` frames of every clip.

Output (bucket layout `stages/static_mask/<fingerprint>/<lens>/`): `mask.png` (8-bit L, 255 = mask, full source
resolution), `static_mask.json` (inputs with SHA-256, params, per-clip and per-frame checks, acceptance), and
`pooled_median.jpg` for review. The fingerprint covers every input lens file, this code and the parameters.
The config lists the lenses that see the class (`lenses`) and those that must not (`absent_lenses`; cam1 looks up
and never sees the gear): on an absent lens the derivation must find nothing, which checks the method itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
import polars as pl

_MODULE_BYTES = Path(__file__).read_bytes()


@dataclass(frozen=True)
class Params:
    frames_per_clip: int = 48
    work_size: int = 960
    whiteness_min: int = 80
    rim_band: float = 0.85
    min_area_px: int = 150        # at work_size
    close_px: int = 5             # at work_size
    dilate_px: int = 16           # at full resolution
    contrast_min: float = 8.0     # V(mask) − V(ring), 0..255, in each clip median
    check_frames: int = 24        # per clip, for the per-frame check


def fingerprint(lens_sha256s: list[str], params: Params) -> str:
    digest = hashlib.sha256(hashlib.sha256(_MODULE_BYTES).digest())
    for part in (*sorted(lens_sha256s), json.dumps(asdict(params), sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


def _radius(size: int) -> np.ndarray:
    yy, xx = np.mgrid[:size, :size]
    c = (size - 1) / 2
    return np.hypot(xx - c, yy - c)


def sample(path: Path, n_frames: int, count: int, size: int) -> np.ndarray:
    """`count` evenly spaced frames of a video, resized to size², as uint8 BGR (T, size, size, 3)."""
    cap = cv2.VideoCapture(str(path))
    out = []
    for i in np.linspace(0, n_frames - 1, count).round().astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, frame = cap.read()
        if ok:
            out.append(cv2.resize(frame, (size, size), interpolation=cv2.INTER_AREA))
    if not out:
        raise RuntimeError(f"no frames decoded from {path}")
    return np.stack(out)


def whiteness(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.int16)
    return hsv[..., 2] - hsv[..., 1]


def derive(pooled: np.ndarray, p: Params) -> np.ndarray:
    """Candidate mask (uint8 0/1) at work size from the pooled median."""
    size = pooled.shape[0]
    r = _radius(size)
    big_r = size / 2 - 2
    cand = (whiteness(pooled) >= p.whiteness_min) & (r >= p.rim_band * big_r) & (r < big_r)
    cand = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((p.close_px, p.close_px), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand)
    keep = np.zeros_like(cand)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= p.min_area_px:
            keep[lab == i] = 1
    return keep


def keep_static_components(cand: np.ndarray, medians: list[np.ndarray], p: Params) -> tuple[np.ndarray, list]:
    """Keep a candidate component only if it is brighter than its surroundings in EVERY clip's own median: a rigid
    part is there in every clip, an averaging artefact of the scene is not."""
    n, lab = cv2.connectedComponents(cand)
    keep, report = np.zeros_like(cand), []
    for i in range(1, n):
        comp = (lab == i).astype(np.uint8)
        cs = [contrast(m, comp) for m in medians]
        ok = all(c >= p.contrast_min for c in cs)
        ys, xs = np.nonzero(comp)
        report.append({"centroid_uv": [round(float(xs.mean()) / cand.shape[1], 3),
                                       round(float(ys.mean()) / cand.shape[0], 3)],
                       "area_px": int(comp.sum()), "clip_contrast_min": None if np.all(np.isnan(cs)) else round(float(np.nanmin(cs)), 2),
                       "kept": ok})
        if ok:
            keep |= comp
    return keep, report


def contrast(img: np.ndarray, mask: np.ndarray) -> float:
    """Mean V inside the mask minus mean V in a 6-px ring just outside it (inside the image circle)."""
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32)
    ring = cv2.dilate(mask, np.ones((13, 13), np.uint8)) & (1 - mask)
    ring &= (_radius(img.shape[0]) < img.shape[0] / 2 - 2).astype(np.uint8)
    if not mask.any() or not ring.any():
        return float("nan")
    return float(v[mask > 0].mean() - v[ring > 0].mean())


def run(manifest: Path, lens: str, out_root: Path, p: Params, full_size: int, expect_present: bool = True) -> dict:
    df = pl.read_parquet(manifest).filter(pl.col("cam") == lens).sort("clip")
    if df.is_empty():
        raise RuntimeError(f"no {lens} rows in {manifest}")
    fp = fingerprint(df["sha256"].to_list(), p)
    out = out_root / "static_mask" / fp / lens
    if (out / "static_mask.json").exists():
        return json.loads((out / "static_mask.json").read_text()) | {"skipped": True}
    medians, samples = {}, {}
    for row in df.iter_rows(named=True):
        path = manifest.parent / row["fingerprint"] / row["clip"] / f"{lens}.mp4"
        frames = sample(path, row["packets"], p.frames_per_clip, p.work_size)
        medians[row["clip"]] = np.median(frames, axis=0).astype(np.uint8)
        samples[row["clip"]] = frames[:: max(1, len(frames) // p.check_frames)]
    pooled = np.median(np.stack(list(medians.values())), axis=0).astype(np.uint8)
    small, components = keep_static_components(derive(pooled, p), list(medians.values()), p)
    def num(x: float) -> float | None:  # JSON has no NaN: an empty mask has no contrast
        return None if np.isnan(x) else round(float(x), 2)

    per_clip = {clip: num(contrast(m, small)) for clip, m in medians.items()}
    per_frame = {clip: [num(contrast(f, small)) for f in fr] for clip, fr in samples.items()}
    clip_values = [c for c in per_clip.values() if c is not None]
    frame_values = [c for cs in per_frame.values() for c in cs if c is not None]
    full = cv2.resize(small * 255, (full_size, full_size), interpolation=cv2.INTER_LINEAR)
    full = cv2.dilate((full >= 128).astype(np.uint8), cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * p.dilate_px + 1, 2 * p.dilate_px + 1))) * 255
    checks = {
        "coverage": round(float((full > 0).mean()), 5),
        "components": int(cv2.connectedComponents((small > 0).astype(np.uint8))[0] - 1),
        "clip_contrast_min": min(clip_values) if clip_values else None,
        "clips_with_gear": int(sum(c >= p.contrast_min for c in clip_values)),
        "clips": len(per_clip),
        "frame_contrast_p05": round(float(np.percentile(frame_values, 5)), 2) if frame_values else None,
        "frames_checked": len(frame_values),
        "frames_with_gear": int(sum(c >= p.contrast_min for c in frame_values)),
    }
    checks["expect_present"] = expect_present
    if expect_present:
        checks["ok"] = bool(small.any() and checks["clips_with_gear"] == checks["clips"])
    else:  # a lens the class is not in view of: the derivation must find nothing that passes in every clip
        checks["ok"] = not small.any()
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "mask.png"), full)
    cv2.imwrite(str(out / "pooled_median.jpg"), pooled, [cv2.IMWRITE_JPEG_QUALITY, 90])
    meta = {"stage": "static_mask", "lens": lens, "fingerprint": fp, "params": asdict(p),
            "code_version": hashlib.sha256(_MODULE_BYTES).hexdigest()[:12], "full_size": full_size,
            "inputs": [{"clip": r["clip"], "sha256": r["sha256"], "frames": r["packets"]}
                       for r in df.iter_rows(named=True)],
            "components": components, "per_clip_contrast": per_clip, "per_frame_contrast": per_frame, "acceptance": checks}
    (out / "static_mask.json").write_text(json.dumps(meta, indent=2, sort_keys=True, allow_nan=False))
    return meta | {"output_dir": str(out)}


def compare_with_tracked(static_png: Path, tracked_dir: Path) -> dict:
    """Per-frame agreement of a tracked mask sequence (e.g. Magic Mask on the same part) with the static mask.

    recall = share of the static mask the tracked mask covers; leak = share of the tracked mask outside the static
    mask (e.g. onto a white wall next to the gear); iou of the two. Masks are thresholded at 50 %.
    """
    static = cv2.imread(str(static_png), cv2.IMREAD_GRAYSCALE) >= 128
    rows = []
    for f in sorted(tracked_dir.glob("[0-9]*.png")):
        t = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE) >= 128
        inter, union = (t & static).sum(), (t | static).sum()
        rows.append({"frame": int(f.stem), "tracked_coverage": float(t.mean()),
                     "recall": float(inter / max(static.sum(), 1)),
                     "leak": float((t & ~static).sum() / max(t.sum(), 1)),
                     "iou": float(inter / max(union, 1))})
    df = pl.DataFrame(rows)

    def q(col: str) -> dict:
        return {k: round(float(df[col].quantile(x)), 4) for k, x in (("p05", .05), ("median", .5), ("p95", .95))}

    return {"frames": df.height, "iou": q("iou"), "recall": q("recall"), "leak": q("leak"),
            "tracked_coverage": q("tracked_coverage"), "static_coverage": round(float(static.mean()), 4)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    parser.add_argument("mask_class")
    args = parser.parse_args(argv)
    raw = tomllib.loads(args.config.read_text())
    spec = raw.get("static_masks", {}).get(args.mask_class)
    if spec is None:
        print(f"no [static_masks.{args.mask_class}] in {args.config}", file=sys.stderr)
        return 1
    params = Params(**spec.get("params", {}))
    manifest = Path(raw["stages"]["remux_manifest"])
    root, size = Path(raw["stages"]["local_root"]), int(spec["full_size"])
    results = {lens: run(manifest, lens, root, params, size) for lens in spec["lenses"]}
    results |= {lens: run(manifest, lens, root, params, size, expect_present=False)
                for lens in spec.get("absent_lenses", [])}
    print(json.dumps({k: v["acceptance"] | {"fingerprint": v["fingerprint"]} for k, v in results.items()}, indent=2))
    return 0 if all(v["acceptance"]["ok"] for v in results.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
