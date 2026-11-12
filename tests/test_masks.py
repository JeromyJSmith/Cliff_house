import cv2
import numpy as np
import polars as pl

from cliff_house.masks import Params, fingerprint, segmentation_size, training_mask, unwanted, write


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


def test_fingerprint_tracks_frames_and_parameters():
    base = fingerprint("f" * 16, Params())
    assert fingerprint("f" * 16, Params()) == base
    assert fingerprint("e" * 16, Params()) != base
    assert fingerprint("f" * 16, Params(prompts=("person", "drone"))) != base
