"""The static per-lens mask keeps a rigid white part present in every clip and drops look-alikes that are not."""
import cv2
import numpy as np

from cliff_house import static_mask as sm

SIZE = 240


def _clip_median(rng, with_part=True, with_transient=False):
    """A brownish averaged scene inside the image circle, plus a white rim part at 9 o'clock."""
    img = np.zeros((SIZE, SIZE, 3), np.uint8)
    cv2.circle(img, (SIZE // 2, SIZE // 2), SIZE // 2 - 2, (70, 90, 120), -1)
    img = np.clip(img.astype(int) + rng.integers(-10, 10, img.shape), 0, 255).astype(np.uint8)
    if with_part:
        cv2.rectangle(img, (3, 100), (18, 140), (235, 235, 235), -1)
    if with_transient:  # something white on the opposite rim in one clip only (e.g. a white wall)
        cv2.rectangle(img, (222, 100), (236, 140), (240, 240, 240), -1)
    return img


def test_rigid_part_is_kept_and_a_one_clip_lookalike_is_dropped():
    rng = np.random.default_rng(1)
    medians = [_clip_median(rng, with_transient=(i == 0)) for i in range(6)]
    pooled = np.median(np.stack(medians), axis=0).astype(np.uint8)
    pooled[100:141, 222:237] = 240  # make the look-alike survive the pooled median, as a bright scene region can
    p = sm.Params(work_size=SIZE, min_area_px=20, close_px=3)
    cand = sm.derive(pooled, p)
    assert cand[120, 10] and cand[120, 229]
    keep, report = sm.keep_static_components(cand, medians, p)
    assert keep[120, 10] and not keep[120, 229]
    assert sorted(c["kept"] for c in report) == [False, True]


def test_lens_without_the_part_gives_an_empty_mask():
    rng = np.random.default_rng(2)
    medians = [_clip_median(rng, with_part=False) for _ in range(6)]
    pooled = np.median(np.stack(medians), axis=0).astype(np.uint8)
    p = sm.Params(work_size=SIZE, min_area_px=20, close_px=3)
    keep, _ = sm.keep_static_components(sm.derive(pooled, p), medians, p)
    assert not keep.any()


def test_fingerprint_covers_inputs_and_params():
    base = sm.fingerprint(["a" * 64, "b" * 64], sm.Params())
    assert base == sm.fingerprint(["b" * 64, "a" * 64], sm.Params())  # order of clips does not matter
    assert base != sm.fingerprint(["a" * 64], sm.Params())
    assert base != sm.fingerprint(["a" * 64, "b" * 64], sm.Params(whiteness_min=90))
