"""The masks stage's pure parts: contract, fingerprint, acceptance and comparison. No torch or model needed."""
import shutil
import subprocess

import numpy as np
import polars as pl
import pytest
from PIL import Image

from cliff_house import masks
from cliff_house.masks import (Params, acceptance, combine, compare, coverage, fill_holes, fingerprint, grow, t_ms,
                               write_png)


def test_t_ms_is_source_frame_time_at_2997():
    assert [t_ms(f) for f in (0, 1, 30, 364)] == [0, 33, 1001, 12145]
    # molab's join back to a source frame: round(t_ms * 30 / 1001)
    assert all(round(t_ms(f) * 30 / 1001) == f for f in range(25000))


def test_grow_is_euclidean_and_local():
    m = np.zeros((40, 40), bool)
    m[20, 20] = True
    g = grow(m, 5)
    assert g[20, 25] and g[23, 24] and not g[20, 26] and not g[24, 24]  # 5.0 in, 5.66 out
    assert (grow(m, 0) == m).all() and not grow(np.zeros((4, 4), bool), 3).any()


def test_fill_holes_fills_enclosed_pockets_only():
    m = np.zeros((30, 30), bool)
    m[5:25, 5:25] = True
    m[10:13, 10:13] = False   # a strap-sized pocket inside the body: filled
    m[0:30, 15] = False       # a gap that reaches the border: not a hole
    filled, n = fill_holes(m, max_px=50)
    assert filled[10:13, 10:13].all() and n == 9
    assert not filled[0:30, 15].any()
    big = np.zeros((30, 30), bool)
    big[2:28, 2:28] = True
    big[5:25, 5:25] = False   # a pocket larger than max_px (an arm looped around the room): kept
    assert fill_holes(big, max_px=50)[1] == 0


def _person_with_items(shape=(100, 100)):
    person = np.zeros(shape, bool)
    person[10:60, 40:60] = True
    on_person = np.zeros(shape, bool)
    on_person[30:40, 60:66] = True     # keys hanging at the belt, touching the body
    across_room = np.zeros(shape, bool)
    across_room[85:95, 5:15] = True    # a speaker that also reads as a "device"
    return person, on_person, across_room


def test_combine_keeps_carried_items_only_when_attached():
    person, keys, speaker = _person_with_items()
    p = Params(attach_px=4, grow_px=0, rim_px=0, max_hole_frac=0.01)
    mask, stats = combine([person], [keys, speaker], p)
    assert mask.dtype == np.uint8 and set(np.unique(mask)) == {0, 255}
    assert (mask[keys] == 255).all() and (mask[speaker] == 0).all()
    assert stats == {"people": 1, "depicted": 0, "carried": 1, "carried_rejected": 1, "filled_px": 0, "rim_px": 0}


def test_combine_rejects_a_large_neighbour_as_carried():
    person, _, _ = _person_with_items()
    cushion = np.zeros_like(person)
    cushion[10:60, 60:95] = True       # a sofa cushion against the operator, read as a "bag"
    mask, stats = combine([person], [cushion], Params(attach_px=4, grow_px=0, rim_px=0, carried_max_frac=0.05))
    assert (mask[cushion] == 0).all() and stats["carried_rejected"] == 1


def test_combine_without_people_keeps_no_carried_items():
    _, keys, speaker = _person_with_items()
    mask, stats = combine([np.zeros_like(keys)], [keys, speaker], Params())
    assert (mask == 0).all() and stats["carried_rejected"] == 2


def test_combine_drops_people_in_pictures_but_keeps_people_in_front_of_them():
    operator = np.zeros((100, 100), bool)
    operator[0:50, 40:60] = True
    poster = np.zeros((100, 100), bool)
    poster[60:95, 60:95] = True        # a framed poster on the wall
    poster_face = np.zeros((100, 100), bool)
    poster_face[65:85, 70:90] = True   # the face SAM 3 calls a "person"
    p = Params(grow_px=0, rim_px=0, depiction_max_frac=0.5)
    mask, stats = combine([operator, poster_face], [], p, depictions=[poster])
    assert (mask[operator] == 255).all() and (mask[poster_face] == 0).all()
    assert stats["people"] == 1 and stats["depicted"] == 1
    # the operator walks in front of the painting: SAM 3's painting instance excludes them, so they stay
    painting_behind = np.zeros((100, 100), bool)
    painting_behind[0:60, 20:80] = True
    painting_behind &= ~operator
    mask, stats = combine([operator], [], p, depictions=[painting_behind])
    assert (mask[operator] == 255).all() and stats["depicted"] == 0


def test_a_picture_covering_the_frame_is_not_a_veto():
    operator = np.zeros((100, 100), bool)
    operator[0:50, 40:60] = True
    whole = np.ones((100, 100), bool)  # "photo" at 0.44 over the entire fisheye
    mask, stats = combine([operator], [], Params(grow_px=0, rim_px=0), depictions=[whole])
    assert (mask[operator] == 255).all() and stats["depicted"] == 0


def test_a_person_touching_the_rim_is_masked_out_to_the_image_circle():
    # 200² frame, rim band from 0.9 of the half-width (r >= 90); the operator enters the band but stops 6 px short of
    # the image edge at the top
    person = np.zeros((200, 200), bool)
    person[6:80, 80:120] = True
    mask, stats = combine([person], [], Params(grow_px=0, rim_frac=0.9, rim_px=12))
    assert (mask[0:6, 95:105] == 255).all()        # the gap up to the rim is closed
    assert mask[100, 100] == 0 and mask[85, 100] == 0  # nothing grows inward, below the band
    assert stats["rim_px"] > 0
    inner = np.zeros((200, 200), bool)
    inner[80:120, 80:120] = True                    # a person in the middle: no rim growth
    assert combine([inner], [], Params(grow_px=0, rim_px=12))[1]["rim_px"] == 0


def test_combine_fills_holes_then_grows():
    person = np.zeros((100, 100), bool)
    person[10:60, 30:70] = True
    person[20:30, 45:50] = False       # chest device the silhouette went around
    mask, stats = combine([person], [], Params(grow_px=3, rim_px=0, max_hole_frac=0.01))
    assert (mask[20:30, 45:50] == 255).all() and stats["filled_px"] == 50
    assert mask[10, 27] == 255 and mask[10, 26] == 0


def test_png_is_8bit_L_255_subject(tmp_path):
    m = np.zeros((6, 8), np.uint8)
    m[:3] = 255
    write_png(tmp_path / "000000.png", m)
    img = Image.open(tmp_path / "000000.png")
    assert img.mode == "L" and img.size == (8, 6)
    assert (np.asarray(img) == m).all() and coverage(m) == 0.5


def test_fingerprint_tracks_input_code_and_params():
    base = fingerprint("a" * 64, Params(), code="c")
    assert len(base) == 16 and fingerprint("a" * 64, Params(), code="c") == base
    assert fingerprint("b" * 64, Params(), code="c") != base
    assert fingerprint("a" * 64, Params(), code="d") != base
    assert fingerprint("a" * 64, Params(carried=("keys",)), code="c") != base
    assert fingerprint("a" * 64, Params(grow_px=4), code="c") != base


def _table(cov):
    return pl.DataFrame({"frame": list(range(len(cov))), "coverage": cov})


RULE = {"every_frame": True, "coverage": [0.04, 0.15]}


def test_acceptance_passes_a_full_clip_in_band():
    result = acceptance(_table([0.08] * 365), 365, RULE)
    assert result["ok"] and result["checks"]["coverage"]["median"] == 0.08


@pytest.mark.parametrize("cov, expected, failing", [
    ([0.08] * 364, 365, "frame_count"),          # a frame missing
    ([0.08] * 364 + [0.0], 365, "every_frame"),  # the operator lost on one frame
    ([0.02] * 365, 365, "coverage"),             # median below the band (a jacket, not a person)
    ([0.30] * 365, 365, "coverage"),             # median above it (leaking into the room)
])
def test_acceptance_fails(cov, expected, failing):
    result = acceptance(_table(cov), expected, RULE)
    assert not result["ok"] and not result["checks"][failing]["ok"]


def test_empty_frames_allowed_when_people_are_not_expected():
    # cam1 (up-looking) has no operator: the rule carries no every_frame and no coverage band
    assert acceptance(_table([0.0] * 10), 10, {})["ok"]


def test_compare_reports_iou_and_each_sides_gaps(tmp_path):
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    a_dir.mkdir(), b_dir.mkdir()
    a = np.zeros((10, 10), np.uint8)
    b = np.zeros((10, 10), np.uint8)
    a[0:4] = 255   # 40 px
    b[2:6] = 255   # 40 px, 20 shared
    write_png(a_dir / "000007.png", a)
    write_png(b_dir / "000007.png", b)
    write_png(a_dir / "000008.png", a)  # no counterpart: skipped
    t = compare(a_dir, b_dir)
    assert t["frame"].to_list() == [7]
    row = t.row(0, named=True)
    assert row["iou"] == pytest.approx(20 / 60)
    assert row["a_only"] == pytest.approx(0.2) and row["b_only"] == pytest.approx(0.2)


def test_existing_partial_fingerprint_is_never_touched(tmp_path):
    fp = fingerprint("a" * 64, Params())
    partial = tmp_path / fp / "clip" / "cam0"
    partial.mkdir(parents=True)
    (partial / "000000.png").write_bytes(b"kept")
    with pytest.raises(FileExistsError):
        masks.run(tmp_path / "x.mp4", "a" * 64, 1, tmp_path, "clip", "cam0", RULE)
    assert (partial / "000000.png").read_bytes() == b"kept"


def test_done_fingerprint_is_returned_not_rerun(tmp_path):
    fp = fingerprint("a" * 64, Params())
    done = tmp_path / fp / "clip" / "cam0"
    done.mkdir(parents=True)
    (done / "pass.json").write_text('{"fingerprint": "%s", "acceptance": {"ok": true}}' % fp)
    assert masks.run(tmp_path / "x.mp4", "a" * 64, 1, tmp_path, "clip", "cam0", RULE)["fingerprint"] == fp


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_decode_yields_every_frame_at_model_size(tmp_path):
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30000/1001:duration=1",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    frames = list(masks.decode(clip, 16))
    assert len(frames) == 30 and frames[0].shape == (16, 16, 3) and frames[0].dtype == np.uint8
    assert masks.probe_size(clip) == (64, 64)
