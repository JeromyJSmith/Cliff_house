import numpy as np
import pycolmap

from cliff_house.views import cameras, overlay, points


def test_overlay_tints_only_ignored_pixels():
    rgb = np.full((2, 2, 3), 100, np.uint8)
    mask = np.array([[0, 255], [255, 255]], np.uint8)
    out = overlay(rgb, mask)
    assert out.dtype == np.uint8 and out.shape == rgb.shape
    assert (out[0, 0] != 100).any() and out[0, 0, 0] > out[0, 0, 1]   # reddened
    assert (out[0, 1] == 100).all() and (out[1] == 100).all()


def _reconstruction(n_points: int) -> pycolmap.Reconstruction:
    rec = pycolmap.Reconstruction()
    rec.add_camera_with_trivial_rig(pycolmap.Camera.create_from_model_name(1, "SIMPLE_PINHOLE", 100.0, 64, 64))
    for i, name in enumerate(["lens0/CLIP__000003.jpg", "lens0/CLIP__000000.jpg"], start=1):
        image = pycolmap.Image(name=name, camera_id=1, image_id=i)
        rec.add_image_with_trivial_frame(image, pycolmap.Rigid3d(pycolmap.Rotation3d(), np.array([0.0, 0.0, -i])))
    for k in range(n_points):
        rec.add_point3D(np.array([k, 0.0, 0.0]), pycolmap.Track())
    return rec


def test_cameras_lists_registered_images_with_their_centres_in_frame_order():
    table = cameras(_reconstruction(0))
    assert table.select("camera", "clip", "frame").rows() == [("lens0", "CLIP", 0), ("lens0", "CLIP", 3)]
    assert table["z"].to_list() == [2.0, 1.0]   # centre = -R^T t


def test_points_thins_to_the_limit_and_keeps_the_extent():
    cloud = points(_reconstruction(10), limit=4)
    assert cloud.height <= 4
    assert cloud["x"].min() == 0.0
