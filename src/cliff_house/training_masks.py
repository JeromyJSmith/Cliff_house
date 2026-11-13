"""Stage: training_masks — the one ignore-mask per frame that poses and training read.

For a frame of an A1 clip (`.insv`, two fisheye lenses):

    ignore = people (masks stage, that frame)
           ∪ gear template of the frame's gear position, with its rim band (gear_mask; cam1: rim band only)
           ∪ aircraft-body arc of the lens (static_mask)

A source that is not an A1 (one phone stream) has no aircraft in view: its ignore-mask is the people mask alone, and
`training_masks.json` records that rule. Unioning only ever removes pixels from reconstruction.

**Polarity — one convention.** Everything this stage writes, and everything poses and training read, is 8-bit L
with **0 = ignore, 255 = use** (COLMAP, Spirula and the trainers read masks this way; the masks stage already
writes it). The rigid-mask stages (gear_mask, static_mask) and Resolve's passes write the opposite, 255 = subject.
`ignore_region` is the only place either polarity is turned into "pixels to ignore"; nothing else inverts a mask.

**Inputs, pinned.** The rigid masks are named by fingerprint in `Templates` (the CURRENT entries of the bucket's
`stages/gear_mask/README.txt` and `stages/static_mask/README.txt`) and are checked on load: the record's own
fingerprint and lens must match and its `acceptance.ok` must be true. People masks are read by the notebook masks
stage's fingerprint (`cliff_house.masks`, layout `<camera>/<frame:06d>.png` + `masks.parquet`); a directory in the
other layout (`pass.json`, 255 = person) is refused.

**Gear position per frame.** The frames stage keeps frames at `t_ms` from the source start; gear_mask has one row
per source frame (`frame`, `t_ms = frame · 1001/30`). A kept frame takes the position of the nearest source frame
within one frame period (33.4 ms). No row in reach, a missing positions table for the clip, or a position with no
template is an error (`UnknownGearPosition`), never a default: clip 027 was added after the gear stage ran.

Output: `stages/training_masks/<fp>/<clip>/` — `<camera>/<frame:06d>.png`, `training_masks.parquet` (camera, frame,
t_ms, source_frame, position, people/gear/body/ignored fractions, file) and `training_masks.json` (inputs,
rules, acceptance). The fingerprint covers the people-mask fingerprint, the template IDs, the per-frame gear-position
assignment and this module's code.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import polars as pl

_MODULE_BYTES = Path(__file__).read_bytes()

IGNORE, USE = 0, 255
SOURCE_FRAME_MS = 1001 / 30   # one source frame at 29.97 fps
Polarity = Literal["use", "subject"]   # "use": 0 = ignore, 255 = use; "subject": 255 = subject (to be ignored)

# The frames stage names lens streams by index (lens0, lens1); the remux and the rigid-mask stages call the same
# streams cam0, cam1 (stream order in the .insv).
REMUX_LENS = {"lens0": "cam0", "lens1": "cam1"}


class UnknownGearPosition(LookupError):
    """A frame of an A1 clip whose landing-gear position is not known."""


@dataclass(frozen=True)
class Templates:
    """Rigid-mask fingerprints per remux lens (CURRENT, 2026-11-12, all 8 clips of 2026-11-10)."""
    gear: dict[str, str] = field(default_factory=lambda: {"cam0": "c506a8ae5ffdd157", "cam1": "fc17000db00e21c6"})
    body: dict[str, str] = field(default_factory=lambda: {"cam0": "472823d347e66988", "cam1": "937c47e779a1d0dc"})
    rim_only: tuple[str, ...] = ("cam1",)   # cam1 looks up and never sees the gear: its gear mask is the rim band
    position_lens: str = "cam0"             # the lens whose positions table holds the gear position of the rig

    def dirs(self) -> list[str]:
        """Bucket-relative directories holding the rigid masks (gear_mask, then static_mask)."""
        return ([f"stages/gear_mask/{fp}/{lens}" for lens, fp in sorted(self.gear.items())]
                + [f"stages/static_mask/{fp}/{lens}" for lens, fp in sorted(self.body.items())])


# --- polarity -------------------------------------------------------------------------------------------------------

def ignore_region(mask: np.ndarray, polarity: Polarity) -> np.ndarray:
    """The one polarity boundary: an 8-bit mask in either convention → bool, True where the pixel is ignored."""
    mask = np.asarray(mask)
    if mask.dtype != np.uint8 or mask.ndim != 2:
        raise ValueError(f"expected an 8-bit single-channel mask, got {mask.dtype} {mask.shape}")
    if polarity == "use":
        return mask < 128
    if polarity == "subject":
        return mask >= 128
    raise ValueError(f"unknown polarity {polarity!r}")


def training_mask(ignore: np.ndarray) -> np.ndarray:
    """bool ignore region → the trainers' 8-bit mask, 0 = ignore, 255 = use."""
    return np.where(ignore, IGNORE, USE).astype(np.uint8)


def union(people: np.ndarray, *rigid: np.ndarray | None) -> np.ndarray:
    """Ignore region of one frame: the people mask (0 = ignore) ∪ each rigid ignore region given (bool). Every
    input must be the frame's full size; a mask of another size is a different camera, not something to resize."""
    out = ignore_region(people, "use").copy()
    for region in rigid:
        if region is None:
            continue
        if region.shape != out.shape:
            raise ValueError(f"rigid mask {region.shape} does not match the frame {out.shape}")
        out |= region
    return out


# --- rigid masks ----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class LensRigid:
    """One lens's rigid ignore regions (bool, full source resolution)."""
    lens: str
    gear: dict[str, np.ndarray]       # position → gear template with its rim band; a rim-only lens has "rim" only
    body: np.ndarray
    rim_only: bool

    def gear_for(self, position: str) -> np.ndarray:
        if self.rim_only:
            return self.gear["rim"]
        if position not in self.gear:
            raise UnknownGearPosition(f"{self.lens}: no gear template for position {position!r} "
                                      f"(templates: {sorted(self.gear)})")
        return self.gear[position]


def _record(path: Path, fingerprint: str, lens: str) -> dict:
    record = json.loads(path.read_text())
    if record.get("fingerprint") != fingerprint or record.get("lens") != lens:
        raise ValueError(f"{path}: record is {record.get('fingerprint')}/{record.get('lens')}, "
                         f"expected {fingerprint}/{lens}")
    if not record.get("acceptance", {}).get("ok"):
        raise ValueError(f"{path}: acceptance.ok is not true; this mask may not be used downstream")
    return record


def _png(path: Path) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise FileNotFoundError(path)
    return mask


def load_rigid(root: Path, templates: Templates) -> dict[str, LensRigid]:
    """Rigid masks from a directory mirroring the bucket layout (`<root>/stages/gear_mask/…`), checked and converted
    to ignore regions. Keyed by remux lens."""
    out = {}
    for lens, gear_fp in templates.gear.items():
        gear_dir = root / "stages" / "gear_mask" / gear_fp / lens
        record = _record(gear_dir / "templates.json", gear_fp, lens)
        rim_only = lens in templates.rim_only
        names = ["rim"] if rim_only else sorted(record["positions"])
        if not names:
            raise ValueError(f"{gear_dir}: no gear positions, and {lens} is not a rim-only lens")
        gear = {n: ignore_region(_png(gear_dir / f"{n}.png"), "subject") for n in names}
        body_fp = templates.body[lens]
        body_dir = root / "stages" / "static_mask" / body_fp / lens
        _record(body_dir / "static_mask.json", body_fp, lens)
        out[lens] = LensRigid(lens, gear, ignore_region(_png(body_dir / "mask.png"), "subject"), rim_only)
    return out


# --- gear position per kept frame -----------------------------------------------------------------------------------

def positions_path(root: Path, templates: Templates, clip: str) -> Path:
    lens = templates.position_lens
    return root / "stages" / "gear_mask" / templates.gear[lens] / lens / "positions" / f"{clip}.parquet"


def assign_positions(frames: pl.DataFrame, positions: pl.DataFrame | None, clip: str = "") -> pl.DataFrame:
    """frames (camera, frame, t_ms) → the same rows with `source_frame` and `position`: the nearest source frame of the
    gear positions table within one frame period. Raises UnknownGearPosition for any frame without one."""
    if positions is None:
        raise UnknownGearPosition(f"{clip}: no gear positions for this clip; run gear_mask with the clip assigned "
                                  f"to a position before its frames can be masked for training")
    pos = (positions.select(source_frame=pl.col("frame"), source_t_ms=pl.col("t_ms").cast(pl.Float64),
                            position=pl.col("position"))
           .sort("source_t_ms"))
    rows = (frames.select("camera", "frame", "t_ms").with_columns(t_key=pl.col("t_ms").cast(pl.Float64))
            .sort("t_key")
            .join_asof(pos, left_on="t_key", right_on="source_t_ms", strategy="nearest", tolerance=SOURCE_FRAME_MS)
            .drop("t_key", "source_t_ms")
            .sort("camera", "frame"))
    unknown = rows.filter(pl.col("position").is_null() | (pl.col("position") == ""))
    if unknown.height:
        sample = unknown.head(5).select("camera", "frame", "t_ms").to_dicts()
        raise UnknownGearPosition(f"{clip}: {unknown.height} of {rows.height} frames have no gear position within "
                                  f"{SOURCE_FRAME_MS:.1f} ms (e.g. {sample})")
    return rows


# --- fingerprint and build ------------------------------------------------------------------------------------------

def fingerprint(people_fingerprint: str, templates: Templates, assignment: pl.DataFrame | None) -> str:
    """People-mask fingerprint + rigid-mask IDs + the per-frame gear-position assignment (None: no aircraft in view)
    + this module's code."""
    rows = [] if assignment is None else sorted(
        assignment.select("camera", "frame", "position").iter_rows())
    digest = hashlib.sha256(hashlib.sha256(_MODULE_BYTES).digest())
    for part in (people_fingerprint, json.dumps(asdict(templates), sort_keys=True),
                 json.dumps({"aircraft": assignment is not None, "positions": rows})):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Plan:
    clip: str
    people_fingerprint: str
    fingerprint: str
    frames: pl.DataFrame            # camera, frame, t_ms (+ source_frame, position for an A1 clip)
    aircraft: bool


def plan(clip: str, frames: pl.DataFrame, people_fingerprint: str, templates: Templates,
         positions: pl.DataFrame | None, aircraft: bool) -> Plan:
    """What one clip's training masks are made from. `aircraft`: an A1 source (the rig's lenses see the aircraft)."""
    assigned = assign_positions(frames, positions, clip) if aircraft else None
    table = assigned if aircraft else frames.select("camera", "frame", "t_ms").sort("camera", "frame")
    return Plan(clip, people_fingerprint, fingerprint(people_fingerprint, templates, assigned), table, aircraft)


def _check_people_dir(people_dir: Path) -> pl.DataFrame:
    if (people_dir / "pass.json").exists():
        raise ValueError(f"{people_dir}: a pass.json layout (255 = person) is not the masks stage's output")
    return pl.read_parquet(people_dir / "masks.parquet")


def build(p: Plan, people_dir: Path, rigid: dict[str, LensRigid], templates: Templates,
          out_dir: Path) -> pl.DataFrame:
    """Write every frame's training mask of one clip; returns `training_masks.parquet`'s table."""
    people = _check_people_dir(people_dir)
    have = set(people.select("camera", "frame").iter_rows())
    missing = [k for k in p.frames.select("camera", "frame").iter_rows() if k not in have]
    if missing:
        raise FileNotFoundError(f"{p.clip}: {len(missing)} frames have no people mask in {people_dir} "
                                f"(e.g. {missing[:5]})")
    records = []
    for r in p.frames.iter_rows(named=True):
        person = _png(people_dir / r["camera"] / f"{r['frame']:06d}.png")
        gear = body = None
        if p.aircraft:
            lens = rigid[REMUX_LENS[r["camera"]]]
            gear, body = lens.gear_for(r["position"]), lens.body
        ignore = union(person, gear, body)
        name = f"{r['camera']}/{r['frame']:06d}.png"
        (out_dir / r["camera"]).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_dir / name), training_mask(ignore))
        records.append({"camera": r["camera"], "frame": r["frame"], "t_ms": r["t_ms"],
                        "source_frame": r.get("source_frame"), "position": r.get("position"),
                        "people_fraction": float(ignore_region(person, "use").mean()),
                        "gear_fraction": None if gear is None else float(gear.mean()),
                        "body_fraction": None if body is None else float(body.mean()),
                        "ignored_fraction": float(ignore.mean()), "file": name})
    table = pl.DataFrame(records, schema={
        "camera": pl.String, "frame": pl.Int64, "t_ms": pl.Int64, "source_frame": pl.Int64, "position": pl.String,
        "people_fraction": pl.Float64, "gear_fraction": pl.Float64, "body_fraction": pl.Float64,
        "ignored_fraction": pl.Float64, "file": pl.String})
    table.write_parquet(out_dir / "training_masks.parquet")
    acceptance = {"frames": table.height, "frames_expected": p.frames.height,
                  "positions": {} if not p.aircraft else dict(table["position"].value_counts().iter_rows())}
    acceptance["ok"] = table.height == p.frames.height
    meta = {"stage": "training_masks", "clip": p.clip, "fingerprint": p.fingerprint,
            "code_version": hashlib.sha256(_MODULE_BYTES).hexdigest()[:12], "polarity": "0 = ignore, 255 = use",
            "people_fingerprint": p.people_fingerprint,
            "rule": ("people ∪ gear template of the frame's position (with rim band) ∪ aircraft body" if p.aircraft
                     else "people only: not an A1 source, no aircraft in view"),
            "templates": asdict(templates) if p.aircraft else None, "acceptance": acceptance}
    (out_dir / "training_masks.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    return table
