"""Stage: gear_mask — the aircraft's landing gear, masked per frame from one rigid template per gear position.

    pixi run python -m cliff_house.gear_mask configs/resolve/<project>.toml

The gear does not move relative to the lens while it holds a position, but it has more than one position. On the
A1's downward lens (cam0) it is folded along the left and right rim in some clips and lowered into the upper left
and right of the image in others. So:

1. **Templates.** For each position the config names, one mask per lens, built from the frames of every clip the
   config assigns to that position (`frames_per_position` in total). Rigid parts are the pixels that agree with
   their clip's median in at least `agree_min` of frames and are white-ish, in the outer band of the image circle,
   in parts that reach the rim (`derive_template`). A template that passes the geometry check is completed with
   its mirror image, since the aircraft is symmetric (fills a leg that is shaded on one side).
2. **Geometry check** (`gear_geometry`): left/right symmetric about the image circle's centre line, balanced
   sides, mostly near the rim and at most `coverage_max` of the frame, leaving out the lens-guard edge at the top
   rim. A wall painting, a single leg or a sky patch fails; these are the masks that went wrong on 2026-11-12, and
   the tests load them.
3. **Per frame.** A position is told apart by its distinguishing parts (the lowered legs; the rim struts are in
   every position). Each frame is scored by the correlation of its edge strength with the position median's along
   each part's outline, taking the weaker part. This is lighting-independent: a white leg has its outline in the
   same place against bright sky or dark ground. The parts are visible at ≥ `present_min` and absent at
   ≤ `absent_max`; with none visible, the default position (folded) applies. Unsure frames take the position that
   dominates the surrounding second, and a position held for less than `min_run_s` is a blip (the gear takes
   seconds to move) and takes the surrounding position. So a mid-clip raise or lower is followed, and the
   clip-level config assignment is only a cross-check.
4. **Rim band.** Everything beyond `rim_mask` of the image circle's radius is masked too, on every lens: the struts
   hug the very edge, and fisheye edge pixels are unreliable for SfM.

Lenses that never see the gear (the upward cam1) get no gear template, by explicit rule in the config
(`rim_only_lenses`), only the rim band.

Output (bucket layout `stages/gear_mask/<fingerprint>/<lens>/`): `<position>.png` (8-bit L, 255 = mask: the gear in
that position plus the rim band, full source resolution), `rim.png`, `<position>_median.jpg` (review),
`templates.json` (inputs, params, components, geometry, per-clip results, acceptance) and `positions/<clip>.parquet`
(frame, t_ms, a score per position, position, confident). The rigid mask of a frame is the template of its
position. The fingerprint covers every input lens file, the position assignment, this code and the parameters.
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

from . import static_mask as sm

_MODULE_BYTES = Path(__file__).read_bytes()


@dataclass(frozen=True)
class Params:
    frames_per_position: int = 420
    work_size: int = 960
    agree_tol: int = 20              # a pixel "agrees" in a frame when its V is within this of its clip's median V
    agree_min: float = 0.38          # gear parts agree in 0.40–0.52 of frames, the moving scene in 0.22–0.33 (042)
    whiteness_min: int = 40          # loose: the agreement does the work; this only keeps white parts, not dark ones
    rim_band: float = 0.55           # lowered legs reach about 0.6 R into the image
    edge_px: int = 6                 # the image circle's own edge also "agrees" (vignette ring): leave it out
    min_area_px: int = 150
    close_px: int = 5
    dilate_px: int = 16              # at full resolution
    rim_reach: float = 0.95          # a gear part reaches the rim (fraction of the image-circle radius); a white thing
                                     # on the operator's chest does not
    rim_mask: float = 0.96           # everything beyond this fraction of the image-circle radius is masked as well:
                                     # the struts hug the very edge, and fisheye edge pixels are unreliable for SfM
    contrast_min: float = 8.0        # template components must stand out by this in V (keep_static_components)
    present_min: float = 0.12        # edge correlation at which a position's distinguishing parts count as visible
    absent_max: float = 0.06         # ... and at or below which they count as absent (between: unsure)
    part_min_share: float = 0.1      # distinguishing parts smaller than this share of the largest are ignored
    keep_fraction: float = 0.6       # a template component must stand out in this share of its frames
    # geometry of a gear template (the lens-guard edge at the top rim is left out of all three)
    symmetry_min: float = 0.5        # IoU of the mask with its mirror image about the image circle's centre line
    mirror_tol_px: int = 9           # at work_size: both are dilated by this before the IoU
    balance_max: float = 2.0         # larger side's mass / smaller side's mass
    rim_fraction_min: float = 0.5    # share of the mask at r ≥ 0.75 R: gear hugs the rim, a central patch does not
    coverage_max: float = 0.12       # share of the frame: the gear is a few percent (folded ≈ 3 %), sky is not
    smooth_s: float = 1.0            # unsure frames take the dominant position within ± this many seconds
    min_run_s: float = 1.0           # the gear takes seconds to move: a position held for less than this is a blip and
                                     # takes the surrounding position (seen: 1–3-frame blips at the score cut-offs)


def fingerprint(lens_sha256s: list[str], positions: dict, params: Params) -> str:
    digest = hashlib.sha256(hashlib.sha256(_MODULE_BYTES).digest())
    for part in (*sorted(lens_sha256s), json.dumps(positions, sort_keys=True),
                 json.dumps(asdict(params), sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


def _components(mask: np.ndarray) -> list[dict]:
    """Connected components of a 0/1 mask with centroid (u, v), area and radial extent (fraction of radius)."""
    size = mask.shape[0]
    r = sm._radius(size) / (size / 2)
    n, lab, stats, cen = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    out = []
    for i in range(1, n):
        sel = lab == i
        out.append({"index": i, "u": float(cen[i][0] / size), "v": float(cen[i][1] / size),
                    "area": int(stats[i, cv2.CC_STAT_AREA]), "r_max": float(r[sel].max()),
                    "r_min": float(r[sel].min())})
    return out


def _top_edge(size: int) -> np.ndarray:
    """The lens-guard edge region at the top rim (always white, always there, not gear)."""
    yy, xx = np.mgrid[:size, :size]
    return (np.abs(xx / size - 0.5) < 0.15) & (yy / size < 0.06)


def mirror(mask: np.ndarray, cx: float) -> np.ndarray:
    """Mirror image of a mask about the vertical line x = cx (the image circle need not be centred in the frame)."""
    shift = int(round(2 * cx - (mask.shape[1] - 1)))
    return np.roll(np.fliplr(mask), shift, axis=1)


def gear_geometry(mask: np.ndarray, p: Params, cx: float | None = None) -> dict:
    """Is this mask a landing gear? The aircraft is left/right symmetric about the lens axis, and its gear hugs the
    rim. So the mask (without the top-rim lens-guard edge) must match its own mirror image (symmetry IoU), carry
    similar mass on both sides (balance), lie mostly near the rim (rim fraction) and cover a few percent of the frame at
    most (coverage). A wall painting, a single leg or a sky patch fails at least one.
    Returns {ok, reason, symmetry, balance, rim_fraction, coverage}."""
    size = mask.shape[0]
    cx = (size - 1) / 2 if cx is None else cx
    core = (mask > 0) & ~_top_edge(size)
    if not core.any():
        return {"ok": False, "reason": "empty", "symmetry": 0.0, "balance": None, "rim_fraction": 0.0}
    r = np.hypot(*(np.mgrid[:size, :size] - np.array([(size - 1) / 2, cx])[:, None, None])) / (size / 2)
    rim_fraction = float(core[r >= 0.75].sum() / core.sum())
    left, right = float(core[:, : int(round(cx))].sum()), float(core[:, int(round(cx)):].sum())
    balance = max(left, right) / max(min(left, right), 1.0)
    k = np.ones((2 * p.mirror_tol_px + 1,) * 2, np.uint8)
    a = cv2.dilate(core.astype(np.uint8), k) > 0
    b = mirror(a, cx)
    symmetry = float((a & b).sum() / max((a | b).sum(), 1))
    reasons = []
    if symmetry < p.symmetry_min:
        reasons.append(f"not left/right symmetric (IoU with mirror {symmetry:.2f})")
    if min(left, right) == 0 or balance > p.balance_max:
        reasons.append("one side only" if min(left, right) == 0 else f"sides unbalanced ×{balance:.1f}")
    if rim_fraction < p.rim_fraction_min:
        reasons.append(f"only {rim_fraction:.0%} near the rim")
    coverage = float(core.mean())
    if coverage > p.coverage_max:
        reasons.append(f"covers {coverage:.0%} of the frame")
    return {"ok": not reasons, "reason": "; ".join(reasons) or "symmetric and at the rim",
            "symmetry": round(symmetry, 3), "balance": round(balance, 2), "rim_fraction": round(rim_fraction, 3),
            "coverage": round(coverage, 4)}


def circle_centre_x(area: np.ndarray) -> float:
    """x of the image circle's centre, from its measured area."""
    xs = np.nonzero(area)[1]
    return float((xs.min() + xs.max()) / 2) if len(xs) else (area.shape[1] - 1) / 2


def derive_template(frames_by_clip: list[np.ndarray], p: Params) -> tuple[np.ndarray, np.ndarray, list]:
    """Template for one gear position from the frames of the clips in that position: pixels that agree with their
    clip's median in at least `agree_min` of frames (rigid) and are white-ish, in the rim band of the image circle.
    Returns (template 0/1, pooled median, component report)."""
    agree, medians = [], []
    for frames in frames_by_clip:
        med = _median(frames)
        medians.append(med)
        mv = cv2.cvtColor(med, cv2.COLOR_BGR2HSV)[..., 2].astype(np.int16)
        hits = np.zeros(mv.shape, np.float32)
        for f in frames:
            hits += np.abs(cv2.cvtColor(f, cv2.COLOR_BGR2HSV)[..., 2].astype(np.int16) - mv) <= p.agree_tol
        agree.append(hits / len(frames))
    agreement = cv2.GaussianBlur(np.mean(agree, axis=0), (5, 5), 0)
    pooled = _median(np.concatenate(frames_by_clip))
    smp = sm.Params(criterion="white", edge_px=p.edge_px, rim_band=p.rim_band, work_size=p.work_size)
    size = pooled.shape[0]
    cand = ((agreement >= p.agree_min) & (sm.whiteness(pooled) >= p.whiteness_min)
            & (sm._radius(size) >= p.rim_band * size / 2) & (sm.image_area(pooled, smp) > 0)).astype(np.uint8)
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, np.ones((p.close_px, p.close_px), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand)
    keep = np.zeros_like(cand)
    for c in _components(cand):
        if c["area"] >= p.min_area_px and c["r_max"] >= p.rim_reach:
            keep[lab == c["index"]] = 1
    return keep, pooled, _components(keep)


def rim_band(area: np.ndarray, frac: float, full_size: int) -> np.ndarray:
    """0/1 mask at full_size of everything beyond `frac` of the measured image circle's radius (outside included)."""
    ys, xs = np.nonzero(area)
    scale = full_size / area.shape[0]
    cx, cy = (xs.min() + xs.max()) / 2 * scale, (ys.min() + ys.max()) / 2 * scale
    radius = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2 * scale
    yy, xx = np.mgrid[:full_size, :full_size]
    return (np.hypot(xx - cx, yy - cy) >= frac * radius).astype(np.uint8)


def run_rim(manifest: Path, lens: str, out_root: Path, p: Params, full_size: int) -> dict:
    """A lens with no gear in view (cam1): only the rim band, from the image circle measured on its clips."""
    df = pl.read_parquet(manifest).filter(pl.col("cam") == lens).sort("clip")
    fp = fingerprint(df["sha256"].to_list(), {}, p)
    out = out_root / "gear_mask" / fp / lens
    if (out / "templates.json").exists():
        return json.loads((out / "templates.json").read_text()) | {"skipped": True}
    groups = _sample_group(list(df.iter_rows(named=True)), manifest, lens, 96, p.work_size)
    med = _median(np.concatenate(groups))
    area = sm.image_area(med, sm.Params(edge_px=0, work_size=p.work_size))
    rim = rim_band(area, p.rim_mask, full_size) * 255
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "rim.png"), rim)
    meta = {"stage": "gear_mask", "lens": lens, "fingerprint": fp, "params": asdict(p), "positions": {},
            "note": "no gear in view on this lens (config rule); rim band only",
            "rim_coverage": round(float((rim > 0).mean()), 5), "acceptance": {"ok": True}}
    (out / "templates.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    return meta | {"output_dir": str(out)}


def _median(frames: np.ndarray, rows: int = 64) -> np.ndarray:
    """Per-pixel median of (T, H, W, 3) uint8 frames, in row blocks so T × H × W × 3 never becomes float64."""
    out = np.empty(frames.shape[1:], np.uint8)
    for y in range(0, frames.shape[1], rows):
        out[y:y + rows] = np.median(frames[:, y:y + rows], axis=0)
    return out


def sample_sequential(path: Path, n_frames: int, count: int, size: int) -> np.ndarray:
    """`count` evenly spaced frames, read sequentially (decoding every frame is faster than seeking in H.264)."""
    want = set(np.linspace(0, n_frames - 1, count).round().astype(int).tolist())
    cap, out, i = cv2.VideoCapture(str(path)), [], 0
    while cap.grab():
        if i in want:
            ok, frame = cap.retrieve()
            if ok:
                out.append(cv2.resize(frame, (size, size), interpolation=cv2.INTER_AREA))
        i += 1
    if not out:
        raise RuntimeError(f"no frames decoded from {path}")
    return np.stack(out)


def _sample_group(rows: list[dict], manifest: Path, lens: str, total: int, size: int) -> list[np.ndarray]:
    per = max(1, total // len(rows))
    return [sample_sequential(manifest.parent / r["fingerprint"] / r["clip"] / f"{lens}.mp4", r["packets"], per, size)
            for r in rows]


@dataclass(frozen=True)
class Leg:
    band: tuple[np.ndarray, np.ndarray]     # pixel indices of a band along the part's outline
    reference: np.ndarray                   # edge strength of the position's median image on that band


def edge_strength(img: np.ndarray) -> np.ndarray:
    """Gradient magnitude of the blurred grey image. A rigid part's outline is in the same place whether it is lit
    or shaded, and against bright sky or dark ground, so its edges are a lighting-independent signature."""
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32), (5, 5), 0)
    return cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))


def make_legs(template: np.ndarray, median: np.ndarray, others: list[np.ndarray], rim: np.ndarray,
              p: "Params") -> list[Leg]:
    """The parts that tell this position apart: template pixels no other position's template covers (dilated), off
    the rim band, split into connected parts (the lowered legs; the struts are in every position). A template with no
    such parts is the default position."""
    rest = template.astype(bool) & ~rim
    k = np.ones((19, 19), np.uint8)
    for o in others:
        rest &= ~(cv2.dilate(o.astype(np.uint8), k) > 0)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(rest.astype(np.uint8))
    areas = stats[1:, cv2.CC_STAT_AREA] if n > 1 else np.array([])
    ref = edge_strength(median)
    legs = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < max(p.min_area_px, p.part_min_share * areas.max()):
            continue
        leg = (lab == i).astype(np.uint8)
        band = (cv2.dilate(leg, np.ones((15, 15), np.uint8)) > 0) & ~(cv2.erode(leg, np.ones((15, 15), np.uint8)) > 0)
        band &= ~rim
        idx = np.nonzero(band)
        legs.append(Leg(idx, ref[idx]))
    return legs


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-9))


def leg_score(edges: np.ndarray, legs: list[Leg]) -> float:
    """Normalised correlation of the frame's edge strength with the position's median along each part's outline,
    for the weaker part (every part must be visible). NaN for a position with no distinguishing parts."""
    if not legs:
        return float("nan")
    return min(_ncc(edges[lg.band], lg.reference) for lg in legs)


def assign(scores: dict[str, np.ndarray], fps: float, p: Params) -> tuple[np.ndarray, np.ndarray]:
    """Per frame. A position with distinguishing parts (score not NaN) wins when its weaker part stands out by
    `present_min`; otherwise the position without distinguishing parts (the default, e.g. folded) applies, confidently
    when every distinguishing score is at most `absent_max`. Unsure frames take the dominant confident
    position within ± smooth_s, then the clip's dominant one."""
    names = list(scores)
    n = len(next(iter(scores.values())))
    default = [k for k, nm in enumerate(names) if np.all(np.isnan(scores[nm]))]
    scored = [k for k in range(len(names)) if k not in default]
    stack = np.stack([np.nan_to_num(scores[names[k]], nan=-1e9) for k in scored]) if scored else np.full((1, n), -1e9)
    best_k = np.array(scored)[stack.argmax(axis=0)] if scored else np.zeros(n, int)
    best = stack.max(axis=0)
    pos = np.full(n, -1)
    pos[best >= p.present_min] = best_k[best >= p.present_min]
    if default:
        low = best <= p.absent_max
        pos[low] = default[0]
    confident = pos >= 0
    if not confident.any():
        fallback = default[0] if default else 0
        return np.full(n, names[fallback], dtype=object), confident
    clip_mode = np.bincount(pos[confident], minlength=len(names)).argmax()
    half = max(1, int(round(p.smooth_s * fps)))
    filled = pos.copy()
    for i in np.nonzero(~confident)[0]:
        window = pos[max(0, i - half): i + half + 1]
        window = window[window >= 0]
        filled[i] = np.bincount(window, minlength=len(names)).argmax() if len(window) else clip_mode
    filled = _drop_blips(filled, max(1, int(round(p.min_run_s * fps))))
    return np.array([names[k] for k in filled], dtype=object), confident


def _drop_blips(pos: np.ndarray, min_run: int) -> np.ndarray:
    """Runs shorter than min_run frames take the position of the run before them (the one after, at the start)."""
    pos = pos.copy()
    changed = True
    while changed:
        changed = False
        starts = np.r_[0, np.nonzero(np.diff(pos))[0] + 1]
        ends = np.r_[starts[1:], len(pos)]
        if len(starts) == 1:
            break
        for k, (a, b) in enumerate(zip(starts, ends)):
            if b - a < min_run:
                pos[a:b] = pos[starts[k - 1]] if k > 0 else pos[ends[k]]
                changed = True
                break
    return pos


def run(manifest: Path, lens: str, positions: dict[str, list[str]], out_root: Path, p: Params,
        full_size: int, fps: float) -> dict:
    df = pl.read_parquet(manifest).filter(pl.col("cam") == lens).sort("clip")
    by_suffix = {r["clip"].rsplit("_", 1)[-1]: r for r in df.iter_rows(named=True)}
    unassigned = sorted(set(by_suffix) - {c for cs in positions.values() for c in cs})
    if unassigned:
        raise RuntimeError(f"clips {unassigned} have no gear position in the config")
    fp = fingerprint(df["sha256"].to_list(), positions, p)
    out = out_root / "gear_mask" / fp / lens
    if (out / "templates.json").exists():
        return json.loads((out / "templates.json").read_text()) | {"skipped": True}
    smp = sm.Params(criterion="white", whiteness_min=p.whiteness_min, rim_band=p.rim_band, edge_px=p.edge_px,
                    min_area_px=p.min_area_px, close_px=p.close_px, contrast_min=p.contrast_min,
                    min_clip_fraction=p.keep_fraction, work_size=p.work_size)
    out.mkdir(parents=True, exist_ok=True)
    templates, legs, report, areas, medians, rims = {}, {}, {}, {}, {}, {}
    for name, clips in positions.items():
        groups = _sample_group([by_suffix[c] for c in clips], manifest, lens, p.frames_per_position, p.work_size)
        derived, med, comps = derive_template(groups, p)
        area = sm.image_area(med, smp)
        cx = circle_centre_x(area)
        geo = gear_geometry(derived, p, cx)
        # The aircraft is symmetric: a template that passed the symmetry check is completed with its mirror image,
        # which fills a leg the agreement test only half found (shaded on one side).
        small = ((derived > 0) | (mirror(derived > 0, cx) & (area > 0))).astype(np.uint8) if geo["ok"] else derived
        templates[name] = small
        areas[name], medians[name] = area, med
        frames = sum(len(g) for g in groups)
        full = cv2.resize(small * 255, (full_size, full_size), interpolation=cv2.INTER_LINEAR)
        full = cv2.dilate((full >= 128).astype(np.uint8), cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (2 * p.dilate_px + 1, 2 * p.dilate_px + 1)))
        rim = rim_band(sm.image_area(med, sm.Params(edge_px=0, work_size=p.work_size)), p.rim_mask, full_size)
        gear_coverage = float(full.mean())
        rims[name] = rim
        full = (full | rim) * 255  # a frame's rigid mask is one lookup: gear of its position plus the rim band
        cv2.imwrite(str(out / f"{name}.png"), full)
        if name == next(iter(positions)):
            cv2.imwrite(str(out / "rim.png"), rim * 255)
        cv2.imwrite(str(out / f"{name}_median.jpg"), med, [cv2.IMWRITE_JPEG_QUALITY, 90])
        report[name] = {"clips": clips, "frames": int(frames), "coverage": round(float((full > 0).mean()), 5),
                        "gear_coverage": round(gear_coverage, 5), "rim_coverage": round(float(rim.mean()), 5),
                        "components": comps, "geometry": {k: v for k, v in geo.items() if k != "components"}}
    for name in positions:
        others = [t for n, t in templates.items() if n != name]
        rim_small = cv2.resize(rims[name], (p.work_size, p.work_size), interpolation=cv2.INTER_NEAREST) > 0
        legs[name] = make_legs(templates[name], medians[name], others, rim_small, p)
        report[name]["distinguishing_parts"] = len(legs[name])
    if sum(1 for lg in legs.values() if not lg) > 1:
        raise RuntimeError("more than one position has no distinguishing parts; positions cannot be told apart")
    rows_out = {}
    for suffix, row in by_suffix.items():
        scores = score_clip(manifest.parent / row["fingerprint"] / row["clip"] / f"{lens}.mp4", legs, p.work_size)
        position, confident = assign(scores, fps, p)
        idx = np.arange(len(position))
        table = pl.DataFrame({"frame": idx, "t_ms": np.round(idx * 1001 / 30, 3),
                              **{f"score_{n}": np.round(s, 2) for n, s in scores.items()},
                              "position": position.astype(str), "confident": confident})
        (out / "positions").mkdir(exist_ok=True)
        table.write_parquet(out / "positions" / f"{row['clip']}.parquet")
        counts = table["position"].value_counts().to_dicts()
        expected = next(n for n, cs in positions.items() if suffix in cs)
        rows_out[row["clip"]] = {"frames": table.height, "frames_expected": row["packets"],
                                 "confident": round(float(confident.mean()), 4), "positions": counts,
                                 "expected": expected,
                                 "matches_expected": round(float((table["position"] == expected).mean()), 4)}
    acceptance = {
        "templates_ok": all(r["geometry"]["ok"] for r in report.values()),
        "frames_ok": all(r["frames"] == r["frames_expected"] for r in rows_out.values()),
        "confident_min": min(r["confident"] for r in rows_out.values()),
        "matches_expected_min": min(r["matches_expected"] for r in rows_out.values()),
    }
    acceptance["ok"] = bool(acceptance["templates_ok"] and acceptance["frames_ok"]
                            and acceptance["confident_min"] >= 0.8 and acceptance["matches_expected_min"] >= 0.9)
    meta = {"stage": "gear_mask", "lens": lens, "fingerprint": fp, "params": asdict(p), "positions": positions,
            "code_version": hashlib.sha256(_MODULE_BYTES).hexdigest()[:12], "full_size": full_size,
            "inputs": [{"clip": r["clip"], "sha256": r["sha256"], "frames": r["packets"]}
                       for r in by_suffix.values()],
            "templates": report, "clips": rows_out, "acceptance": acceptance}
    (out / "templates.json").write_text(json.dumps(meta, indent=2, sort_keys=True, allow_nan=False, default=float))
    return meta | {"output_dir": str(out)}


def score_clip(path: Path, legs: dict[str, list[Leg]], size: int) -> dict[str, np.ndarray]:
    """Score every frame of a clip (sequential decode) against each position's distinguishing parts."""
    cap = cv2.VideoCapture(str(path))
    scores = {n: [] for n in legs}
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        edges = edge_strength(cv2.resize(frame, (size, size), interpolation=cv2.INTER_AREA))
        for n, lg in legs.items():
            scores[n].append(leg_score(edges, lg))
    return {n: np.array(s, dtype=float) for n, s in scores.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    args = parser.parse_args(argv)
    raw = tomllib.loads(args.config.read_text())
    spec = raw["gear_mask"]
    params = Params(**spec.get("params", {}))
    fps = float(str(raw["settings"]["timelineFrameRate"]).split()[0])
    manifest, root = Path(raw["stages"]["remux_manifest"]), Path(raw["stages"]["local_root"])
    size = int(spec["full_size"])
    results = {lens: run(manifest, lens, spec["positions"], root, params, size, fps) for lens in spec["lenses"]}
    results |= {lens: run_rim(manifest, lens, root, params, size) for lens in spec.get("rim_only_lenses", [])}
    print(json.dumps({k: v["acceptance"] | {"fingerprint": v["fingerprint"]} for k, v in results.items()}, indent=2))
    return 0 if all(v["acceptance"]["ok"] for v in results.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
