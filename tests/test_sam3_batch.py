"""The batched path must give the same masks as calling SAM 3 once per (frame, prompt), which is what Pixeltable's
`sam3_for_segmentation` does. Runs the real model (gated; needs an HF login) on two small clip-041 frames, on CPU."""
from pathlib import Path

import numpy as np
import PIL.Image
import pytest
import torch

from cliff_house.masks import Params
from cliff_house.sam3_batch import Sam3

FRAMES = sorted((Path(__file__).parents[2] / "data/frasier/cliff-house/runs/spirula/clip_041_20261110/images/cam0")
                .glob("*.jpg"))
PROMPTS = ("person", "hand", "picture")


@pytest.mark.skipif(len(FRAMES) < 30, reason="clip 041 Spirula frames are not on this machine")
def test_batched_masks_match_one_call_per_frame_and_prompt():
    params = Params()
    sam = Sam3.load(params.model_id, params.revision, PROMPTS, "cpu")
    images = [PIL.Image.open(FRAMES[i]).convert("RGB").resize((512, 512)) for i in (5, 20)]
    batched = sam.segment(images, threshold=0.4, mask_threshold=params.mask_threshold)
    found = 0
    for image, got in zip(images, batched):
        for prompt in PROMPTS:
            with torch.no_grad():
                inputs = sam.processor(images=image, text=prompt, return_tensors="pt")
                ref = sam.processor.post_process_instance_segmentation(
                    sam.model(**inputs), threshold=0.4, mask_threshold=params.mask_threshold,
                    target_sizes=inputs["original_sizes"].tolist())[0]
            want = ref["masks"].numpy().astype(bool).reshape(-1, 512, 512)
            assert got[prompt]["masks"].shape == want.shape, prompt
            np.testing.assert_allclose(got[prompt]["scores"], ref["scores"].numpy(), atol=1e-4)
            assert (got[prompt]["masks"] != want).mean() < 1e-4, prompt
            found += len(want)
    assert found > 0  # the frames show the operator, so the comparison is not vacuous
