"""End-to-end check of the draw-on-top scene in Resolve's Fusion, on synthetic data with a known answer.

    pixi run python -m cliff_house.resolve.usd_check <work dir>

1. Synthetic world points and a camera moving over 5 frames (COLMAP convention), as `usd_scene` would get them
   from the poses stage.
2. A plate: 5 rectified frames with a green dot where each point projects (the "footage").
3. `scene.usda` from `usd_scene.write_scene`, the points red and large.
4. In Resolve: a timeline holding the plate; a Fusion comp `MediaIn → Merge(bg)`, `uLoader(scene) → uRenderer
   (camera = the scene camera) → Merge(fg)`; render 5 frames.
5. In each rendered frame, the red blobs' centroids are matched to the expected pixels. Pass: median error ≤ 2 px on
   every frame — Fusion then reads the cameras, time codes and units as the maths says, and real poses will draw
   site lines where they are in the footage.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from . import usd_scene as us
from .connect import resolve_app

SIZE, FOV, FRAMES = 960, 90.0, 5


def synthetic():
    rng = np.random.default_rng(7)
    points = rng.uniform([-3, -2, 5], [3, 2, 10], (60, 3))
    views = []
    for k in range(FRAMES):
        R = Rotation.from_euler("xyz", [1.5 * k, 4 * k - 8, 0.5 * k], degrees=True).as_matrix()
        centre = np.array([0.3 * k - 0.6, -0.1 * k, 0.2 * k])
        views.append(us.View(frame=k, cam_from_world=np.c_[R, -R @ centre]))
    return views, points


def write_inputs(work: Path):
    views, points = synthetic()
    K = us.pinhole(SIZE, SIZE, FOV)
    plate = work / "plate"
    plate.mkdir(parents=True, exist_ok=True)
    expected = []
    for v in views:
        uv = us.colmap_project(v.cam_from_world, K, points)
        inside = (uv[:, 0] > 5) & (uv[:, 0] < SIZE - 5) & (uv[:, 1] > 5) & (uv[:, 1] < SIZE - 5)
        img = np.full((SIZE, SIZE, 3), 40, np.uint8)
        for x, y in uv[inside]:
            cv2.circle(img, (int(round(x)), int(round(y))), 4, (0, 200, 0), -1)
        cv2.imwrite(str(plate / f"{v.frame:06d}.png"), img)
        expected.append(uv[inside])
    us.write_scene(work / "usd", {"cam": views}, points, np.tile([1.0, 0.0, 0.0], (len(points), 1)), SIZE, SIZE, FOV,
                   30000 / 1001, "synthetic check")
    text = (work / "usd" / "scene.usda").read_text().replace("float[] widths = [0.01]", "float[] widths = [0.08]")
    (work / "usd" / "scene.usda").write_text(text)
    return plate, expected


def build_and_render(work: Path, plate: Path) -> tuple[list[Path], dict]:
    from .passes import _folder, render

    resolve = resolve_app()
    project = resolve.GetProjectManager().GetCurrentProject()
    mp = project.GetMediaPool()
    folder = _folder(mp, _folder(mp, mp.GetRootFolder(), "inputs"), "usd_check")
    mp.SetCurrentFolder(folder)
    items = mp.ImportMedia([str(plate)])
    name = f"usd_check-{int(time.time())}"
    tl = mp.CreateTimelineFromClips(name, [items[0]])
    for key, value in (("useCustomSettings", "1"), ("timelineResolutionWidth", str(SIZE)),
                       ("timelineResolutionHeight", str(SIZE))):
        tl.SetSetting(key, value)
    item = tl.GetItemListInTrack("video", 1)[0]
    comp = item.AddFusionComp() if not item.GetFusionCompCount() else item.GetFusionCompByIndex(1)
    media_in, media_out = comp.FindTool("MediaIn1"), comp.FindTool("MediaOut1")
    loader = comp.AddTool("uLoader", -32768, -32768)
    loader.SetInput("Filename", str(work / "usd" / "scene.usda"))
    renderer = comp.AddTool("uRenderer", -32768, -32768)
    renderer.ConnectInput("SceneInput", loader)
    renderer.SetInput("UseFrameFormatSettings", 0)
    renderer.SetInput("Width", SIZE)
    renderer.SetInput("Height", SIZE)
    renderer.SetInput("Lighting", "None")
    merge = comp.AddTool("Merge", -32768, -32768)
    merge.ConnectInput("Background", media_in)
    merge.ConnectInput("Foreground", renderer)
    media_out.ConnectInput("Input", merge)
    cams = renderer.GetInput("CameraSelector")
    files = render(project, tl, work / "render", "RGB8")
    return files, {"timeline": name, "camera_selector": cams}


def measure(files: list[Path], expected: list[np.ndarray]) -> dict:
    per_frame = []
    for f, exp in zip(files, expected):
        img = cv2.imread(str(f))
        red = ((img[:, :, 2] > 150) & (img[:, :, 1] < 90) & (img[:, :, 0] < 90)).astype(np.uint8)
        n, _, _, cen = cv2.connectedComponentsWithStats(red)
        found = cen[1:]
        if not len(found) or not len(exp):
            per_frame.append({"found": int(len(found)), "expected": int(len(exp)), "median_px": None})
            continue
        d, _ = cKDTree(found).query(exp)
        per_frame.append({"found": int(len(found)), "expected": int(len(exp)), "median_px": float(np.median(d)),
                          "p90_px": float(np.percentile(d, 90))})
    ok = all(r["median_px"] is not None and r["median_px"] <= 2.0 for r in per_frame)
    return {"frames": per_frame, "ok": ok}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("work", type=Path)
    args = parser.parse_args(argv)
    plate, expected = write_inputs(args.work)
    files, info = build_and_render(args.work, plate)
    result = measure(files, expected) | info
    (args.work / "usd_check.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
