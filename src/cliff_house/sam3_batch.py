"""SAM 3 concept segmentation for many prompts over many frames, encoding each frame once.

SAM 3's cost is its image encoder; the per-prompt part (text features, detector, mask head) is light. Calling the
model once per (frame, prompt) — what a per-prompt computed column does — runs the encoder once per prompt on the
same frame. Here a batch of frames is encoded once, every prompt's text features are computed once per batch size,
and only the light part runs per prompt. Results have the shape Pixeltable's `sam3_for_segmentation` returns
({"scores", "boxes", "masks"} per prompt), so the masks stage consumes them unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
import PIL.Image
import torch
from transformers import Sam3Model, Sam3Processor


@dataclass
class Sam3:
    model: Sam3Model
    processor: Sam3Processor
    device: torch.device
    prompts: tuple[str, ...]
    _text: dict[int, list[tuple[object, torch.Tensor]]] = field(default_factory=dict)

    @classmethod
    def load(cls, model_id: str, revision: str, prompts: Sequence[str], device: str) -> Sam3:
        model = Sam3Model.from_pretrained(model_id, revision=revision).to(device).eval()
        return cls(model, Sam3Processor.from_pretrained(model_id, revision=revision), torch.device(device),
                   tuple(prompts))

    def _text_features(self, batch: int) -> list[tuple[object, torch.Tensor]]:
        """Per prompt: (text features, attention mask) for a batch of `batch` frames, computed once per size."""
        if batch not in self._text:
            self._text[batch] = []
            for prompt in self.prompts:
                tokens = self.processor(text=[prompt] * batch, return_tensors="pt").to(self.device)
                feats = self.model.get_text_features(input_ids=tokens["input_ids"],
                                                     attention_mask=tokens["attention_mask"], return_dict=True)
                self._text[batch].append((feats, tokens["attention_mask"]))
        return self._text[batch]

    @torch.no_grad()
    def segment(self, images: Sequence[PIL.Image.Image], threshold: float,
                mask_threshold: float) -> list[dict[str, dict[str, np.ndarray]]]:
        """One {prompt: {"scores", "boxes", "masks"}} per image; masks are bool (n, H, W) at the image's size."""
        inputs = self.processor(images=[im.convert("RGB") for im in images], return_tensors="pt").to(self.device)
        vision = self.model.get_vision_features(pixel_values=inputs["pixel_values"])
        sizes = inputs["original_sizes"].tolist()
        out: list[dict[str, dict[str, np.ndarray]]] = [{} for _ in images]
        for prompt, (text, attention) in zip(self.prompts, self._text_features(len(images))):
            outputs = self.model(vision_embeds=vision, text_embeds=text, attention_mask=attention)
            results = self.processor.post_process_instance_segmentation(
                outputs, threshold=threshold, mask_threshold=mask_threshold, target_sizes=sizes)
            for i, (res, (h, w)) in enumerate(zip(results, sizes)):
                masks = res["masks"].cpu().numpy().astype(bool)
                out[i][prompt] = {"scores": res["scores"].float().cpu().numpy(),
                                  "boxes": res["boxes"].float().cpu().numpy(),
                                  "masks": masks.reshape(-1, int(h), int(w))}
        return out
