"""Review sheet for people masks: chosen source frames with each mask's outline drawn on them, side by side.

    pixi run -e sam3 python scripts/review_masks.py <lens.mp4> <out_dir> <frame,frame,…> <label>=<mask_dir> …

For every frame it writes <out_dir>/<frame:06d>.jpg (full-resolution 3840² is too big to look at, so the frame is
shown at 1280² with a 2× crop of the region the masks cover), and an all-frames contact sheet `sheet.jpg`. Mask
colours: the first mask is red, the second cyan, more are yellow/green. A pixel inside the red mask and outside the
cyan one is a gap of the cyan mask, and vice versa. The sheets show footage, so they go to the stage mirror's
`_proof/` folder, never the public repo.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

COLOURS = [(255, 40, 40), (0, 220, 255), (255, 220, 0), (60, 255, 60)]
VIEW = 1280


def source_frame(mp4: Path, frame: int) -> Image.Image:
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(mp4), "-map", "0:v:0", "-vf",
           f"select='eq(n\\,{frame})'", "-fps_mode", "passthrough", "-frames:v", "1", "-f", "image2pipe",
           "-vcodec", "png", "-"]
    from io import BytesIO
    return Image.open(BytesIO(subprocess.run(cmd, capture_output=True, check=True).stdout)).convert("RGB")


def outline(mask: Image.Image, width: int) -> Image.Image:
    m = mask.point(lambda v: 255 if v > 127 else 0)
    return Image.fromarray(np.asarray(m.filter(ImageFilter.MaxFilter(width))) - np.asarray(m))


def draw(img: Image.Image, masks: list[tuple[str, Image.Image]], frame: int) -> Image.Image:
    out = img.copy()
    for (label, m), colour in zip(masks, COLOURS):
        tint = Image.new("RGB", out.size, colour)
        out = Image.composite(Image.blend(out, tint, 0.25), out, m.point(lambda v: 255 if v > 127 else 0))
        out.paste(tint, mask=outline(m, 9))
    view = out.resize((VIEW, VIEW), Image.Resampling.LANCZOS)
    union = np.zeros(img.size[::-1], bool)
    for _, m in masks:
        union |= np.asarray(m) > 127
    panels = [view]
    if union.any():  # 2× detail of the masked region, so belts, straps, hands and boots can be judged
        ys, xs = np.nonzero(union)
        cx, cy = int(xs.mean()), int(ys.mean())
        half = max(int(max(xs.max() - xs.min(), ys.max() - ys.min()) * 0.6), VIEW // 2)
        box = (max(0, cx - half), max(0, cy - half), min(img.width, cx + half), min(img.height, cy + half))
        panels.append(out.crop(box).resize((VIEW, VIEW), Image.Resampling.LANCZOS))
    sheet = Image.new("RGB", (VIEW * len(panels), VIEW + 40), "black")
    for i, p in enumerate(panels):
        sheet.paste(p, (i * VIEW, 40))
    d = ImageDraw.Draw(sheet)
    legend = "   ".join(f"{label} {100 * (np.asarray(m) > 127).mean():.2f}%" for label, m in masks)
    d.text((10, 10), f"frame {frame}   {legend}   (red, cyan, yellow, green in that order)", fill="white")
    return sheet


def main(argv: list[str]) -> None:
    mp4, out_dir, frames, *specs = argv
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mask_dirs = [(s.split("=", 1)[0], Path(s.split("=", 1)[1])) for s in specs]
    sheets = []
    for frame in (int(f) for f in frames.split(",")):
        img = source_frame(Path(mp4), frame)
        masks = [(label, Image.open(d / f"{frame:06d}.png").convert("L")) for label, d in mask_dirs
                 if (d / f"{frame:06d}.png").exists()]
        sheet = draw(img, masks, frame)
        sheet.save(out_dir / f"{frame:06d}.jpg", quality=88)
        sheets.append(sheet.resize((sheet.width // 2, sheet.height // 2)))
    contact = Image.new("RGB", (max(s.width for s in sheets), sum(s.height for s in sheets)), "black")
    y = 0
    for s in sheets:
        contact.paste(s, (0, y))
        y += s.height
    contact.save(out_dir / "sheet.jpg", quality=85)
    print(out_dir)


if __name__ == "__main__":
    main(sys.argv[1:])
