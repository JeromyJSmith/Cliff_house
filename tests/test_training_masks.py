"""Training masks: people ∪ gear template of the frame's position ∪ aircraft body, in one polarity.

The synthetic tests build a small bucket layout (gear_mask, static_mask, masks stage) with distinct shapes per source
and check the written masks pixel by pixel. The real-data tests use the CURRENT rigid masks and gear positions on the
project drive, which is never committed (footage-derived), and are skipped when the drive is not mounted.
"""
import json
from pathlib import Path

import cv2
import numpy as np
import polars as pl
import pytest

from cliff_house import training_masks as tm

N = 64
T = tm.Templates(gear={"cam0": "g0", "cam1": "g1"}, body={"cam0": "b0", "cam1": "b1"})
CLIP = "VID_X_041"


def _rect(y0, y1, x0, x1):
    m = np.zeros((N, N), bool)
    m[y0:y1, x0:x1] = True
    return m


# Distinct, partly overlapping regions so a union that drops or inverts any one source shows up.
FOLDED, LOWERED = _rect(20, 40, 0, 6), _rect(4, 14, 4, 20)
RIM1 = _rect(0, N, 60, N)
BODY0, BODY1 = _rect(0, 3, 10, 50), _rect(0, 5, 20, 44)
PERSON = _rect(30, 50, 2, 30)       # overlaps FOLDED, to check the union is not a sum or an XOR


def _subject(region):                # rigid stages write 255 = mask
    return np.where(region, 255, 0).astype(np.uint8)


def _write_record(d: Path, name: str, record: dict):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(record))


def _bucket(root: Path, ok: bool = True, positions: dict[str, list[str]] | None = None) -> Path:
    g0 = root / "stages/gear_mask/g0/cam0"
    _write_record(g0, "templates.json", {"fingerprint": "g0", "lens": "cam0", "positions": {"folded": ["041"],
                                         "lowered": ["042"]}, "acceptance": {"ok": ok}})
    cv2.imwrite(str(g0 / "folded.png"), _subject(FOLDED))
    cv2.imwrite(str(g0 / "lowered.png"), _subject(LOWERED))
    g1 = root / "stages/gear_mask/g1/cam1"
    _write_record(g1, "templates.json", {"fingerprint": "g1", "lens": "cam1", "positions": {}, "acceptance": {"ok": True}})
    cv2.imwrite(str(g1 / "rim.png"), _subject(RIM1))
    for fp, lens, region in (("b0", "cam0", BODY0), ("b1", "cam1", BODY1)):
        d = root / f"stages/static_mask/{fp}/{lens}"
        _write_record(d, "static_mask.json", {"fingerprint": fp, "lens": lens, "acceptance": {"ok": True}})
        cv2.imwrite(str(d / "mask.png"), _subject(region))
    (g0 / "positions").mkdir()
    for clip, seq in (positions or {CLIP: ["folded"] * 30 + ["lowered"] * 30}).items():
        idx = np.arange(len(seq))
        pl.DataFrame({"frame": idx, "t_ms": np.round(idx * 1001 / 30, 3), "position": seq}).write_parquet(
            g0 / "positions" / f"{clip}.parquet")
    return root


def _frames(t_ms=(0, 334, 667, 1001)) -> pl.DataFrame:
    """Kept frames at the frames stage's t_ms (12 candidate fps), both lenses."""
    return pl.DataFrame([{"camera": c, "frame": k, "t_ms": t} for c in ("lens0", "lens1") for k, t in enumerate(t_ms)])


def _people(d: Path, frames: pl.DataFrame, region=PERSON) -> Path:
    """The masks stage's layout and polarity: 0 = ignore, 255 = use."""
    for r in frames.iter_rows(named=True):
        (d / r["camera"]).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / r["camera"] / f"{r['frame']:06d}.png"), np.where(region, 0, 255).astype(np.uint8))
    frames.select("camera", "frame").write_parquet(d / "masks.parquet")
    return d


def _run(tmp_path, frames=None, positions=None):
    frames = _frames() if frames is None else frames
    root = _bucket(tmp_path / "bucket", positions=positions)
    rigid = tm.load_rigid(root, T)
    pos = pl.read_parquet(tm.positions_path(root, T, CLIP))
    p = tm.plan(CLIP, frames, "peoplefp", T, pos, aircraft=True)
    out = tmp_path / "out"
    table = tm.build(p, _people(tmp_path / "people", frames), rigid, T, out)
    return p, table, out


def _read(out: Path, camera: str, frame: int) -> np.ndarray:
    return cv2.imread(str(out / camera / f"{frame:06d}.png"), cv2.IMREAD_UNCHANGED)


# --- the union --------------------------------------------------------------------------------------------------------

def test_union_covers_people_gear_of_the_frames_position_and_body_pixel_by_pixel(tmp_path):
    # t_ms 0 and 334 fall in source frames 0 and 10 (folded); 1001 and 1334 in frames 30 and 40 (lowered).
    p, table, out = _run(tmp_path, frames=_frames((0, 334, 1001, 1334)))
    assert p.frames["position"].to_list() == ["folded", "folded", "lowered", "lowered"] * 2
    for frame, gear in ((0, FOLDED), (1, FOLDED), (2, LOWERED), (3, LOWERED)):
        want = PERSON | gear | BODY0
        assert (_read(out, "lens0", frame) == np.where(want, 0, 255)).all(), frame
    for frame in range(4):   # cam1: rim band whatever the position, and its own body arc
        assert (_read(out, "lens1", frame) == np.where(PERSON | RIM1 | BODY1, 0, 255)).all(), frame
    row = table.filter((pl.col("camera") == "lens0") & (pl.col("frame") == 2)).row(0, named=True)
    assert row["ignored_fraction"] == pytest.approx((PERSON | LOWERED | BODY0).mean())
    assert row["people_fraction"] == pytest.approx(PERSON.mean())
    assert row["gear_fraction"] == pytest.approx(LOWERED.mean())
    assert row["body_fraction"] == pytest.approx(BODY0.mean())
    meta = json.loads((out / "training_masks.json").read_text())
    assert meta["acceptance"]["ok"] and meta["acceptance"]["positions"] == {"folded": 4, "lowered": 4}
    assert pl.read_parquet(out / "training_masks.parquet").equals(table)


def test_a_source_without_the_aircraft_is_masked_by_people_only(tmp_path):
    frames = pl.DataFrame({"camera": ["lens0"], "frame": [0], "t_ms": [0]})
    p = tm.plan("IMG_1", frames, "peoplefp", T, positions=None, aircraft=False)
    tm.build(p, _people(tmp_path / "people", frames), {}, T, tmp_path / "out")
    assert (_read(tmp_path / "out", "lens0", 0) == np.where(PERSON, 0, 255)).all()
    assert "people only" in json.loads((tmp_path / "out/training_masks.json").read_text())["rule"]


def test_a_frame_without_a_people_mask_is_an_error(tmp_path):
    frames = _frames()
    root = _bucket(tmp_path / "bucket")
    p = tm.plan(CLIP, frames, "fp", T, pl.read_parquet(tm.positions_path(root, T, CLIP)), aircraft=True)
    people = _people(tmp_path / "people", frames.head(3))
    with pytest.raises(FileNotFoundError, match="no people mask"):
        tm.build(p, people, tm.load_rigid(root, T), T, tmp_path / "out")


def test_a_rigid_mask_of_another_size_is_refused():
    with pytest.raises(ValueError, match="does not match"):
        tm.union(np.full((N, N), 255, np.uint8), np.zeros((N + 1, N), bool))


# --- polarity ---------------------------------------------------------------------------------------------------------

def test_polarity_is_converted_only_at_the_boundary():
    use = np.array([[0, 255], [127, 128]], np.uint8)     # masks stage: 0 = ignore
    assert tm.ignore_region(use, "use").tolist() == [[True, False], [True, False]]
    assert tm.ignore_region(use, "subject").tolist() == [[False, True], [False, True]]
    with pytest.raises(ValueError):
        tm.ignore_region(use, "person")
    with pytest.raises(ValueError):
        tm.ignore_region(use.astype(np.uint16), "use")
    assert tm.training_mask(np.array([[True, False]])).tolist() == [[0, 255]]
    assert (tm.IGNORE, tm.USE) == (0, 255)


def test_output_keeps_the_trainers_polarity_and_inverts_only_the_rigid_masks(tmp_path):
    _, _, out = _run(tmp_path)
    m = _read(out, "lens0", 0)
    assert m.dtype == np.uint8 and set(np.unique(m)) == {0, 255}
    assert m[40, 20] == 0                       # a person (people masks are 0 = ignore and stay so)
    assert m[25, 2] == 0 and m[1, 30] == 0      # gear and body (255 = mask in their stages, inverted once)
    assert m[60, 40] == 255                     # nothing there: used


def test_people_masks_in_the_255_is_person_layout_are_refused(tmp_path):
    frames = _frames()
    root = _bucket(tmp_path / "bucket")
    p = tm.plan(CLIP, frames, "fp", T, pl.read_parquet(tm.positions_path(root, T, CLIP)), aircraft=True)
    people = _people(tmp_path / "people", frames)
    (people / "pass.json").write_text("{}")
    with pytest.raises(ValueError, match="255 = person"):
        tm.build(p, people, tm.load_rigid(root, T), T, tmp_path / "out")


# --- unknown gear positions -------------------------------------------------------------------------------------------

def test_a_clip_with_no_gear_positions_is_an_error_not_a_default():
    with pytest.raises(tm.UnknownGearPosition, match="VID_NEW_027"):
        tm.plan("VID_NEW_027", _frames(), "fp", T, positions=None, aircraft=True)


def test_a_frame_past_the_positions_table_is_an_error(tmp_path):
    root = _bucket(tmp_path / "bucket", positions={CLIP: ["folded"] * 10})   # source frames 0–9 (≈ 300 ms)
    pos = pl.read_parquet(tm.positions_path(root, T, CLIP))
    tm.assign_positions(_frames((0, 300, 330)), pos)    # 330 ms is within one frame period of frame 9 (300.3 ms)
    with pytest.raises(tm.UnknownGearPosition, match="2 of 6 frames"):
        tm.assign_positions(_frames((0, 300, 400)), pos, CLIP)


def test_a_missing_position_value_is_an_error(tmp_path):
    root = _bucket(tmp_path / "bucket", positions={CLIP: ["folded", "", "folded"]})
    with pytest.raises(tm.UnknownGearPosition):
        tm.assign_positions(_frames((33,)), pl.read_parquet(tm.positions_path(root, T, CLIP)), CLIP)


def test_a_position_with_no_template_is_an_error(tmp_path):
    with pytest.raises(tm.UnknownGearPosition, match="half"):
        _run(tmp_path, frames=_frames((0,)), positions={CLIP: ["half"] * 5})


def test_rigid_masks_are_checked_against_their_records(tmp_path):
    root = _bucket(tmp_path / "bad", ok=False)
    with pytest.raises(ValueError, match="acceptance.ok"):
        tm.load_rigid(root, T)
    root = _bucket(tmp_path / "moved")
    (root / "stages/gear_mask/g0").rename(root / "stages/gear_mask/g9")   # a record filed under another ID
    with pytest.raises(ValueError, match="expected g9/cam0"):
        tm.load_rigid(root, tm.Templates(gear={"cam0": "g9", "cam1": "g1"}, body=T.body))


# --- fingerprint ------------------------------------------------------------------------------------------------------

def test_fingerprint_changes_when_any_input_changes(tmp_path, monkeypatch):
    root = _bucket(tmp_path / "bucket")
    pos = pl.read_parquet(tm.positions_path(root, T, CLIP))
    a = tm.assign_positions(_frames(), pos)
    base = tm.fingerprint("people", T, a)
    assert tm.fingerprint("people", T, a) == base
    assert tm.fingerprint("people2", T, a) != base
    for templates in (tm.Templates(gear={"cam0": "gX", "cam1": "g1"}, body=T.body),
                      tm.Templates(gear={"cam0": "g0", "cam1": "gX"}, body=T.body),
                      tm.Templates(gear=T.gear, body={"cam0": "bX", "cam1": "b1"}),
                      tm.Templates(gear=T.gear, body={"cam0": "b0", "cam1": "bX"})):
        assert tm.fingerprint("people", templates, a) != base
    flipped = a.with_columns(position=pl.when((pl.col("camera") == "lens0") & (pl.col("frame") == 0))
                             .then(pl.lit("lowered")).otherwise(pl.col("position")))
    assert tm.fingerprint("people", T, flipped) != base
    assert tm.fingerprint("people", T, None) != tm.fingerprint("people", T, a.clear())
    assert tm.fingerprint("people", T, a.reverse()) == base     # row order is not an input
    monkeypatch.setattr(tm, "_MODULE_BYTES", b"other code")
    assert tm.fingerprint("people", T, a) != base


def test_plan_fingerprint_follows_the_gear_positions(tmp_path):
    frames = _frames((0, 1001))
    folded = _bucket(tmp_path / "a", positions={CLIP: ["folded"] * 60})
    mixed = _bucket(tmp_path / "b", positions={CLIP: ["folded"] * 30 + ["lowered"] * 30})
    fp = [tm.plan(CLIP, frames, "fp", T, pl.read_parquet(tm.positions_path(r, T, CLIP)), True).fingerprint
          for r in (folded, mixed)]
    assert fp[0] != fp[1]


# --- the CURRENT rigid masks on the project drive ---------------------------------------------------------------------

DRIVE = Path("/Volumes/2TB/CliffHouse")
needs_drive = pytest.mark.skipif(not (DRIVE / "stages/gear_mask/c506a8ae5ffdd157").is_dir(),
                                 reason="project drive with the rigid masks not mounted")


@needs_drive
def test_current_rigid_masks_load_and_042_gets_the_lowered_gear_where_041_gets_the_folded(tmp_path):
    t = tm.Templates()
    rigid = tm.load_rigid(DRIVE, t)
    assert set(rigid) == {"cam0", "cam1"} and set(rigid["cam0"].gear) == {"folded", "lowered"}
    assert rigid["cam1"].rim_only and set(rigid["cam1"].gear) == {"rim"}
    # Kept frames as the frames stage times them (12 candidate fps, one per 4): 3 s of each clip.
    frames = pl.DataFrame([{"camera": c, "frame": k, "t_ms": round(4 * k * 1000 / 12)}
                           for c in ("lens0", "lens1") for k in range(9)])
    plans = {}
    for clip, position in (("VID_20261110_132328_041", "folded"), ("VID_20261110_134257_042", "lowered")):
        pos = pl.read_parquet(tm.positions_path(DRIVE, t, clip))
        plans[clip] = tm.plan(clip, frames, "people", t, pos, aircraft=True)
        assert set(plans[clip].frames["position"]) == {position}
    assert plans["VID_20261110_132328_041"].fingerprint != plans["VID_20261110_134257_042"].fingerprint
    # A synthetic person in the middle of the real 3840² frame; the written mask is the exact union.
    size = rigid["cam0"].body.shape
    person = np.zeros(size, bool)
    person[1700:2300, 1700:2100] = True
    one = frames.filter(pl.col("frame") == 0)
    people = tmp_path / "people"
    for c in ("lens0", "lens1"):
        (people / c).mkdir(parents=True)
        cv2.imwrite(str(people / c / "000000.png"), tm.training_mask(person))
    one.select("camera", "frame").write_parquet(people / "masks.parquet")
    p = tm.plan("VID_20261110_134257_042", one, "people", t,
                pl.read_parquet(tm.positions_path(DRIVE, t, "VID_20261110_134257_042")), aircraft=True)
    tm.build(p, people, rigid, t, tmp_path / "out")
    m0 = _read(tmp_path / "out", "lens0", 0)
    want0 = person | rigid["cam0"].gear["lowered"] | rigid["cam0"].body
    assert (m0 == np.where(want0, 0, 255)).all()
    assert (_read(tmp_path / "out", "lens1", 0) ==
            np.where(person | rigid["cam1"].gear["rim"] | rigid["cam1"].body, 0, 255)).all()
    # The lowered legs are ignored on 042 and would be used under the folded template.
    legs = rigid["cam0"].gear["lowered"] & ~rigid["cam0"].gear["folded"]
    assert legs.sum() > 0.02 * legs.size and (m0[legs] == 0).all()


@needs_drive
def test_a_clip_the_gear_stage_never_saw_has_no_positions():
    t = tm.Templates()
    assert not tm.positions_path(DRIVE, t, "VID_20261110_000000_027").exists()
    with pytest.raises(tm.UnknownGearPosition):
        tm.plan("VID_20261110_000000_027", _frames(), "people", t, None, aircraft=True)
