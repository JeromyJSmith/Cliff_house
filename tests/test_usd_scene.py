"""The draw-on-top scene: COLMAP poses become USD cameras that see the world where COLMAP says they do."""
import numpy as np
from scipy.spatial.transform import Rotation

from cliff_house.resolve import usd_scene as us


def _synthetic(n_frames=5):
    rng = np.random.default_rng(0)
    points = rng.uniform([-3, -1, 4], [3, 1, 9], (200, 3))
    views = []
    for k in range(n_frames):
        R = Rotation.from_euler("xyz", [2 * k, 5 * k - 10, 1], degrees=True).as_matrix()
        centre = np.array([0.4 * k - 1, 0.1 * k, 0.0])
        views.append(us.View(frame=10 * k, cam_from_world=np.c_[R, -R @ centre]))
    return views, points


def test_usd_camera_sees_points_where_colmap_does():
    views, points = _synthetic()
    width = height = 1920
    fov = 90.0
    K = us.pinhole(width, height, fov)
    focal = us.FILM_MM / 2 / np.tan(np.radians(fov) / 2)
    for v in views:
        expected = us.colmap_project(v.cam_from_world, K, points)
        got = us.usd_project(us.usd_camera_matrix(v.cam_from_world), focal, us.FILM_MM, width, height, points)
        assert np.abs(expected - got).max() < 1e-6


def test_scene_file_has_cameras_points_path_and_a_drawing_layer(tmp_path):
    views, points = _synthetic()
    path = us.write_scene(tmp_path, {"lens0": views}, points, np.full_like(points, 0.5), 1920, 1920, 90.0,
                          30000 / 1001, "synthetic")
    text = path.read_text()
    assert text.startswith("#usda 1.0") and 'def Camera "lens0"' in text and 'def Points "Sparse"' in text
    assert text.count("matrix4d xformOp:transform.timeSamples") == 1 and "40: (" in text   # frames are time codes
    assert 'subLayers = [@./site_lines.usda@]' in text and (tmp_path / "site_lines.usda").exists()


def test_drawing_layer_is_never_overwritten(tmp_path):
    views, points = _synthetic(2)
    (tmp_path / "site_lines.usda").write_text("#usda 1.0\n# owner's lines\n")
    us.write_scene(tmp_path, {"lens0": views}, points, np.zeros_like(points), 640, 640, 90.0, 30.0, "synthetic")
    assert "owner's lines" in (tmp_path / "site_lines.usda").read_text()
