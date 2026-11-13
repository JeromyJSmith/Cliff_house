"""Landing-gear masks: the geometric acceptance and the per-frame position choice.

The real-data tests load the masks that went wrong on 2026-11-12 (a per-clip mask on a wall painting, a single
lowered leg, sky on the upward lens) from the project drive, which is never committed (footage-derived), and are
skipped when the drive is not mounted.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from cliff_house import gear_mask as gm

SIZE = 480
P = gm.Params(min_area_px=10, mirror_tol_px=3)
STAGE = Path("/Volumes/2TB/CliffHouse/stages/static_mask")


def _circle_mask():
    m = np.zeros((SIZE, SIZE), np.uint8)
    return m


def _strut(m, u, v, w=0.03, h=0.12):
    """A part hugging the rim at (u, v): a rectangle from the edge inward."""
    x0, x1 = (0, int((u + w) * SIZE)) if u < 0.5 else (int((u - w) * SIZE), SIZE)
    cv2.rectangle(m, (x0, int((v - h / 2) * SIZE)), (x1, int((v + h / 2) * SIZE)), 1, -1)


def test_mirrored_pair_at_the_rim_is_a_gear():
    m = _circle_mask()
    _strut(m, 0.03, 0.47)
    _strut(m, 0.97, 0.46)
    geo = gm.gear_geometry(m, P)
    assert geo["ok"], geo["reason"]


def test_two_pairs_lowered_gear_is_a_gear():
    m = _circle_mask()
    _strut(m, 0.03, 0.47)
    _strut(m, 0.97, 0.46)
    _strut(m, 0.10, 0.18, w=0.12, h=0.08)
    _strut(m, 0.90, 0.19, w=0.12, h=0.08)
    assert gm.gear_geometry(m, P)["ok"]


def test_single_leg_is_not_a_gear():
    m = _circle_mask()
    _strut(m, 0.90, 0.2, w=0.12, h=0.08)
    geo = gm.gear_geometry(m, P)
    assert not geo["ok"] and ("symmetric" in geo["reason"] or "one side" in geo["reason"])


def test_central_patch_or_unmatched_side_parts_are_not_a_gear():
    m = _circle_mask()
    cv2.circle(m, (SIZE // 2, SIZE // 2), SIZE // 4, 1, -1)  # sky patch
    assert not gm.gear_geometry(m, P)["ok"]
    m = _circle_mask()
    _strut(m, 0.03, 0.47)
    _strut(m, 0.97, 0.80)  # right part far lower than the left: not a mirror image
    assert not gm.gear_geometry(m, P)["ok"]


def test_lens_guard_edge_at_the_top_rim_is_allowed():
    m = _circle_mask()
    _strut(m, 0.03, 0.47)
    _strut(m, 0.97, 0.46)
    cv2.rectangle(m, (int(0.42 * SIZE), 0), (int(0.58 * SIZE), 6), 1, -1)
    assert gm.gear_geometry(m, P)["ok"]


def test_position_per_frame_follows_a_mid_clip_change_and_smooths_unsure_frames():
    n = 120
    lowered = np.full(n, -0.05)  # edge correlation of the lowered legs' outline: absent
    lowered[60:] = 0.3           # legs lowered half way through
    lowered[90] = 0.09           # one unsure frame (between absent_max and present_min)
    scores = {"folded": np.full(n, np.nan), "lowered": lowered}
    position, confident = gm.assign(scores, fps=29.97, p=gm.Params())
    assert list(position[:60]) == ["folded"] * 60 and list(position[60:]) == ["lowered"] * 60
    assert not confident[90] and confident[:90].all()


def _load(path: Path) -> np.ndarray:
    m = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) > 0
    return cv2.resize(m.astype(np.uint8), (960, 960), interpolation=cv2.INTER_NEAREST)


BAD = {  # what went wrong, and the per-clip or per-lens mask that showed it
    "wall painting and top edge, no legs (clip 041)": "d0072e4ccbeb046f/VID_20261110_132328_041/cam0/mask.png",
    "one lowered leg only (clip 042)": "7f141ac57111099f/VID_20261110_134257_042/cam0/mask.png",
    "one strut only (clip 038)": "da829a3f19e8739b/VID_20261110_131804_038/cam0/mask.png",
    "sky on the upward lens (clip 040)": "e82bbb7b06586c97/VID_20261110_132300_040/cam1/mask.png",
}


@pytest.mark.skipif(not STAGE.is_dir(), reason="project drive not mounted")
@pytest.mark.parametrize("what", sorted(BAD))
def test_masks_that_went_wrong_fail_the_geometry(what):
    path = STAGE / BAD[what]
    if not path.exists():
        pytest.skip(f"{path} not present")
    assert not gm.gear_geometry(_load(path), gm.Params())["ok"], what


@pytest.mark.skipif(not STAGE.is_dir(), reason="project drive not mounted")
def test_the_folded_mask_pooled_over_clips_passes_the_geometry():
    path = STAGE / "a2c308df0a6904ce/cam0/mask.png"
    if not path.exists():
        pytest.skip(f"{path} not present")
    geo = gm.gear_geometry(_load(path), gm.Params())
    assert geo["ok"], geo["reason"]


def test_mirror_follows_an_off_centre_image_circle():
    m = np.zeros((10, 10), np.uint8)
    m[4, 2] = 1
    assert gm.mirror(m, cx=4.0)[4, 6] == 1   # 2 → 2·4 − 2 = 6
    assert gm.mirror(m, cx=4.5)[4, 7] == 1   # centred frame (cx = 4.5): 2 → 7


def test_one_frame_blips_are_not_a_change_of_position():
    n = 300
    lowered = np.full(n, -0.05)
    lowered[[40, 41, 200]] = 0.13          # isolated frames just over present_min
    lowered[150:260] = 0.3                 # a real lowering for 110 frames (3.7 s)
    position, _ = gm.assign({"folded": np.full(n, np.nan), "lowered": lowered}, fps=29.97, p=gm.Params())
    assert set(position[:150]) == {"folded"} and set(position[150:260]) == {"lowered"}
    assert set(position[260:]) == {"folded"}
