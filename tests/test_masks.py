import cv2
import numpy as np
import polars as pl
import pytest

from cliff_house.masks import (Params, by_group, combine, fill_holes, fingerprint, grow, segmentation_size,
                               training_mask, unwanted, write)

# Rules only, so each test sees one rule at a time.
BARE = Params(grow_px=0, rim_px=0, max_hole_frac=0.0)


def test_unwanted_unions_every_instance_of_every_prompt_at_full_size():
    person = np.zeros((2, 10, 10), bool)
    person[0, 0:2, 0:2] = True
    person[1, 8:10, 8:10] = True
    nobody = np.zeros((0, 10, 10), bool)
    out = unwanted([person, nobody], (20, 20))
    assert out.shape == (20, 20)
    assert out[0:4, 0:4].all() and out[16:20, 16:20].all()
    assert out.sum() == 2 * 16


def test_training_mask_ignores_a_grown_region_and_keeps_the_rest():
    region = np.zeros((50, 50), bool)
    region[25, 25] = True
    mask = training_mask(region, grow_px=3)
    assert mask.dtype == np.uint8 and set(np.unique(mask)) == {0, 255}
    assert mask[25, 25] == 0 and mask[25, 28] == 0  # grown by 3 px
    assert mask[25, 30] == 255 and mask[0, 0] == 255
    assert (training_mask(region) == np.where(region, 0, 255)).all()  # combine's region is already grown


def test_empty_frame_is_fully_usable():
    mask = training_mask(unwanted([], (8, 8)), grow_px=5)
    assert (mask == 255).all()


def test_write_produces_png_per_frame_and_a_table(tmp_path):
    m = np.full((6, 6), 255, np.uint8)
    m[:3] = 0
    table = write([("lens0", 0, m), ("lens1", 0, np.full((6, 6), 255, np.uint8))], tmp_path)
    assert table.sort("camera")["ignored_fraction"].to_list() == [0.5, 0.0]
    assert (cv2.imread(str(tmp_path / "lens0/000000.png"), cv2.IMREAD_UNCHANGED) == m).all()
    assert pl.read_parquet(tmp_path / "masks.parquet").equals(table)


def test_segmentation_size_caps_the_long_side():
    assert segmentation_size(3840, 3840, Params()) == (1920, 1920)
    assert segmentation_size(1920, 1080, Params()) == (1920, 1080)


def test_fingerprint_tracks_frames_parameters_and_rules():
    base = fingerprint("f" * 16, Params())
    assert fingerprint("f" * 16, Params()) == base
    assert fingerprint("e" * 16, Params()) != base
    assert fingerprint("f" * 16, Params(carried=("keys",))) != base
    assert fingerprint("f" * 16, Params(grow_px=4)) != base


def test_prompts_and_thresholds_per_group():
    p = Params(people=("person",), carried=("keys",), depictions=("poster",))
    assert p.prompts == ("person", "keys", "poster")
    assert p.detection_threshold == 0.4
    assert (p.threshold("person"), p.threshold("keys"), p.threshold("poster")) == (0.5, 0.4, 0.5)


def test_by_group_resizes_and_applies_each_groups_threshold():
    p = Params(people=("person",), carried=("keys",), depictions=("poster",))
    m = np.zeros((2, 5, 5), bool)
    m[:, 0, 0] = True
    results = {"person": {"scores": [0.45, 0.9], "masks": m},     # 0.45 is below the person threshold
               "keys": {"scores": [0.45], "masks": m[:1]},       # carried items pass at 0.4
               "poster": {"scores": [], "masks": np.zeros((0, 5, 5), bool)}}
    out = by_group(results, (10, 10), p)
    assert [len(out[g]) for g in ("people", "carried", "depictions")] == [1, 1, 0]
    assert out["people"][0].shape == (10, 10) and out["people"][0][:2, :2].all()


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


def _scene(shape=(200, 200)):
    person = np.zeros(shape, bool)
    person[20:120, 80:120] = True
    keys = np.zeros(shape, bool)
    keys[60:80, 112:130] = True         # hanging at the belt: overlaps the body by 8 x 20 px
    net = np.zeros(shape, bool)
    net[60:90, 122:150] = True          # in a bucket beside the leg: 2 px away, no overlap
    return person, keys, net


def test_carried_items_must_overlap_a_person_not_just_touch_one():
    person, keys, net = _scene()
    region, stats = combine([person], [keys, net], [], person.shape, Params(**{**BARE.__dict__, "attach_overlap_px": 64}),
                            fisheye=False)
    assert region[keys].all() and not region[net & ~keys].any()
    assert (stats["carried"], stats["carried_rejected"]) == (1, 1)


def test_without_a_person_nothing_is_carried():
    person, keys, net = _scene()
    region, stats = combine([], [keys, net], [], person.shape, BARE, fisheye=False)
    assert not region.any() and stats["carried_rejected"] == 2


def test_a_large_neighbour_is_not_carried():
    person, _, _ = _scene()
    cushion = np.zeros_like(person)
    cushion[20:120, 110:200] = True      # a sofa against the operator, read as a "bag"
    region, stats = combine([person], [cushion], [], person.shape,
                            Params(**{**BARE.__dict__, "carried_max_frac": 0.1}), fisheye=False)
    assert not region[cushion & ~person].any() and stats["carried_rejected"] == 1


def test_people_in_pictures_are_dropped_people_in_front_of_them_kept():
    person, _, _ = _scene()
    poster = np.zeros_like(person)
    poster[130:190, 130:190] = True
    face = np.zeros_like(person)
    face[140:170, 140:170] = True       # SAM 3 calls the poster's face a "person"
    region, stats = combine([person, face], [], [poster], person.shape, BARE, fisheye=False)
    assert region[person].all() and not region[face].any()
    assert (stats["people"], stats["depicted"]) == (1, 1)
    behind = np.zeros_like(person)
    behind[0:150, 50:150] = True
    behind &= ~person                   # a painting the operator walks in front of
    region, stats = combine([person], [], [behind], person.shape, BARE, fisheye=False)
    assert region[person].all() and stats["depicted"] == 0


def test_a_picture_covering_the_frame_is_not_a_veto():
    person, _, _ = _scene()
    region, stats = combine([person], [], [np.ones_like(person)], person.shape, BARE, fisheye=False)
    assert region[person].all() and stats["depicted"] == 0


def test_holes_are_filled_then_the_region_grows():
    person, _, _ = _scene()
    person[40:50, 95:105] = False       # a chest device the silhouette went around
    region, stats = combine([person], [], [], person.shape, Params(**{**BARE.__dict__, "max_hole_frac": 0.01,
                                                                        "grow_px": 3}), fisheye=False)
    assert region[40:50, 95:105].all() and stats["filled_px"] == 100
    assert region[20, 77] and not region[20, 76]


def test_a_person_touching_the_fisheye_rim_reaches_the_image_circle():
    person = np.zeros((200, 200), bool)
    person[6:80, 80:120] = True         # enters the outer band (r >= 90) and stops 6 px short of the edge
    p = Params(**{**BARE.__dict__, "rim_frac": 0.9, "rim_px": 12})
    region, stats = combine([person], [], [], person.shape, p, fisheye=True)
    assert region[0:6, 95:105].all() and not region[100, 100] and stats["rim_px"] > 0
    region, stats = combine([person], [], [], person.shape, p, fisheye=False)  # a phone frame has no rim
    assert not region[0:6, 95:105].any() and stats["rim_px"] == 0


def test_rules_return_a_bool_region_the_trainer_mask_inverts():
    person, keys, _ = _scene()
    region, _ = combine([person], [keys], [], person.shape, Params(), fisheye=True)
    mask = training_mask(region)
    assert region.dtype == bool and mask.dtype == np.uint8
    assert (mask[region] == 0).all() and (mask[~region] == 255).all()
