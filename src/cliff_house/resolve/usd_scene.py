"""The "draw on top" scene: SfM cameras, sparse points, the drone's path and site lines as USD, for Fusion.

    pixi run python -m cliff_house.resolve.usd_scene <sparse model dir> <out dir> [--lens lens0] [--fov 90]

COLMAP (the poses stage) solves the fisheye lenses with the OPENCV_FISHEYE model; USD and Fusion cameras are pinhole.
So each solved view becomes a pinhole camera with a chosen rectilinear field of view (`fov_deg`), and the footage for
that view is undistorted to exactly that pinhole (`rectify_map`, from the solve's own fisheye parameters). A line
drawn in the solve's 3D frame then renders onto the rectified plate where it is in the footage, from every camera.

Written (USDA text, no USD library needed): `scene.usda` with
- `/World/Cameras/<lens>`: one camera animated over the solved frames (time code = source frame number);
- `/World/Sparse`: the sparse points with their colours;
- `/World/CameraPath/<lens>`: the camera centres as a linear curve (the drone's own path);
- a sublayer `site_lines.usda` with `/World/SiteLines`, curves in the solve frame (metres, from the factory baseline:
  a scale hint, not a survey), created empty with one example line, so lines can be drawn or imported later and
  stay locked to the footage. The coordinate frame is recorded as `customData` on `/World`.

Conventions: COLMAP cameras look down +Z with +Y down; USD cameras look down −Z with +Y up,
so world_from_usd_camera = world_from_colmap_camera · diag(1, −1, −1). USD matrices are row-major
with the translation in the last row (row vectors). Apertures are in millimetres on a 36 mm-wide film back; focal
length follows from the rectified field of view.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

FILM_MM = 36.0
FLIP = np.diag([1.0, -1.0, -1.0])


@dataclass(frozen=True)
class View:
    frame: int                 # source frame number (USD time code)
    cam_from_world: np.ndarray  # 3×4 [R | t], COLMAP convention


def pinhole(width: int, height: int, fov_deg: float) -> np.ndarray:
    """K of a centred pinhole with the given horizontal field of view."""
    f = width / 2 / np.tan(np.radians(fov_deg) / 2)
    return np.array([[f, 0, width / 2], [0, f, height / 2], [0, 0, 1.0]])


def usd_camera_matrix(cam_from_world: np.ndarray) -> np.ndarray:
    """4×4 USD (row-vector) transform of a USD camera at a COLMAP pose."""
    R, t = cam_from_world[:, :3], cam_from_world[:, 3]
    world_from_cam = np.eye(4)
    world_from_cam[:3, :3] = R.T @ FLIP
    world_from_cam[:3, 3] = -R.T @ t
    return world_from_cam.T


def usd_project(usd_matrix: np.ndarray, focal_mm: float, aperture_mm: float, width: int, height: int,
                points: np.ndarray) -> np.ndarray:
    """Pixels of world points seen by a USD camera (independent of the COLMAP maths, to test the conversion)."""
    world_from_cam = usd_matrix.T
    cam = (np.linalg.inv(world_from_cam) @ np.c_[points, np.ones(len(points))].T)[:3].T   # USD camera frame
    x, y, z = cam[:, 0], cam[:, 1], -cam[:, 2]             # depth along −Z
    fpx = focal_mm / aperture_mm * width
    return np.c_[width / 2 + fpx * x / z, height / 2 - fpx * y / z]


def colmap_project(cam_from_world: np.ndarray, K: np.ndarray, points: np.ndarray) -> np.ndarray:
    cam = (cam_from_world @ np.c_[points, np.ones(len(points))].T).T
    uv = (K @ cam.T).T
    return uv[:, :2] / uv[:, 2:3]


def _m(mat: np.ndarray) -> str:
    return "( " + ", ".join("(" + ", ".join(f"{v:.9g}" for v in row) + ")" for row in mat) + " )"


def _pts(pts: np.ndarray) -> str:
    return "[" + ", ".join(f"({x:.6g}, {y:.6g}, {z:.6g})" for x, y, z in pts) + "]"


def write_scene(out: Path, views: dict[str, list[View]], points: np.ndarray, colours: np.ndarray, width: int,
                height: int, fov_deg: float, fps: float, frame_note: str) -> Path:
    """Write scene.usda (+ site_lines.usda if absent: it is the owner's drawing layer and is never overwritten)."""
    out.mkdir(parents=True, exist_ok=True)
    focal = FILM_MM / 2 / np.tan(np.radians(fov_deg) / 2)
    frames = [v.frame for vs in views.values() for v in vs]
    cams, paths = [], []
    for lens, vs in views.items():
        samples = ",\n".join(f"            {v.frame}: {_m(usd_camera_matrix(v.cam_from_world))}"
                             for v in sorted(vs, key=lambda v: v.frame))
        cams.append(f'''        def Camera "{lens}"
        {{
            float focalLength = {focal:.6g}
            float horizontalAperture = {FILM_MM}
            float verticalAperture = {FILM_MM * height / width:.6g}
            float2 clippingRange = (0.01, 100000)
            matrix4d xformOp:transform.timeSamples = {{
{samples}
            }}
            uniform token[] xformOpOrder = ["xformOp:transform"]
        }}''')
        ordered = sorted(vs, key=lambda v: v.frame)
        centres = np.array([-v.cam_from_world[:, :3].T @ v.cam_from_world[:, 3] for v in ordered])
        paths.append(f'''        def BasisCurves "{lens}"
        {{
            uniform token type = "linear"
            int[] curveVertexCounts = [{len(centres)}]
            point3f[] points = {_pts(centres)}
            float[] widths = [0.02] (interpolation = "constant")
            color3f[] primvars:displayColor = [(1, 0.45, 0)] (interpolation = "constant")
        }}''')
    cols = "[" + ", ".join(f"({r:.4g}, {g:.4g}, {b:.4g})" for r, g, b in colours) + "]"
    scene = f'''#usda 1.0
(
    defaultPrim = "World"
    upAxis = "Y"
    metersPerUnit = 1
    startTimeCode = {min(frames) if frames else 0}
    endTimeCode = {max(frames) if frames else 0}
    timeCodesPerSecond = {fps:.6g}
    subLayers = [@./site_lines.usda@]
)

def Xform "World" (
    customData = {{ string coordinate_frame = "{frame_note}" }}
)
{{
    def Scope "Cameras"
    {{
{chr(10).join(cams)}
    }}
    def Points "Sparse"
    {{
        point3f[] points = {_pts(points)}
        float[] widths = [0.01] (interpolation = "constant")
        color3f[] primvars:displayColor = {cols} (interpolation = "vertex")
    }}
    def Scope "CameraPath"
    {{
{chr(10).join(paths)}
    }}
}}
'''
    (out / "scene.usda").write_text(scene)
    lines = out / "site_lines.usda"
    if not lines.exists():
        lines.write_text('''#usda 1.0
(
    defaultPrim = "World"
)

over "World"
{
    def Scope "SiteLines" (
        doc = """Site lines in the solve frame (metres from the factory baseline: a scale hint).
Add a BasisCurves per line: property line, footprint, grade breaks.
They render through every camera and stay locked to the footage."""
    )
    {
        def BasisCurves "example_line"
        {
            uniform token type = "linear"
            int[] curveVertexCounts = [2]
            point3f[] points = [(0, 0, 0), (1, 0, 0)]
            float[] widths = [0.03] (interpolation = "constant")
            color3f[] primvars:displayColor = [(0, 1, 1)] (interpolation = "constant")
        }
    }
}
''')
    return out / "scene.usda"


def rectify_map(fisheye_params: tuple[float, ...], size_in: tuple[int, int], width: int, height: int,
                fov_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """cv2.remap maps that undistort an OPENCV_FISHEYE frame (fx, fy, cx, cy, k1..k4) to the scene's pinhole view."""
    fx, fy, cx, cy, *k = fisheye_params
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]])
    return cv2.fisheye.initUndistortRectifyMap(K, np.array(k[:4]), np.eye(3), pinhole(width, height, fov_deg),
                                               (width, height), cv2.CV_32FC1)


def from_colmap(model_dir: Path, lens: str | None = None) -> tuple[dict[str, list[View]], np.ndarray, np.ndarray,
                                                                   dict[str, tuple]]:
    """Views per lens folder (image names `<lens>/<clip>__<frame>.jpg`), points, colours and fisheye params."""
    import pycolmap

    rec = pycolmap.Reconstruction(str(model_dir))
    views: dict[str, list[View]] = {}
    params: dict[str, tuple] = {}
    for iid in rec.reg_image_ids():
        im = rec.images[iid]
        folder, rest = im.name.split("/", 1)
        if lens and folder != lens:
            continue
        frame = int(rest.removesuffix(".jpg").rsplit("__", 1)[1])
        views.setdefault(folder, []).append(View(frame, np.asarray(im.cam_from_world().matrix())))
        params[folder] = tuple(rec.cameras[im.camera_id].params)
    xyz = np.array([p.xyz for p in rec.points3D.values()]).reshape(-1, 3)
    rgb = np.array([p.color for p in rec.points3D.values()]).reshape(-1, 3) / 255.0
    return views, xyz, rgb, params


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("model", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--lens")
    parser.add_argument("--fov", type=float, default=90.0)
    parser.add_argument("--size", type=int, default=1920)
    args = parser.parse_args(argv)
    views, xyz, rgb, params = from_colmap(args.model, args.lens)
    path = write_scene(args.out, views, xyz, rgb, args.size, args.size, args.fov, 30000 / 1001,
                       f"COLMAP solve {args.model} (metres, factory-baseline scale hint)")
    (args.out / "cameras.json").write_text(json.dumps({k: {"fisheye_params": list(v), "fov_deg": args.fov,
                                                           "size": args.size} for k, v in params.items()}, indent=2))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
