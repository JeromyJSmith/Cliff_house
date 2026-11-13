import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from cliff_house.poses import FrameSet, insta360_rig, stage_workspace


def _lens_json(q0, q1, t1):
    cam = lambda q, t: {"rotation": dict(zip("xyzw", q)), "translation": t}
    return {"rig": {"projection": {"kind": {"Rig": {"cameras": [cam(q0, [0, 0, 0]), cam(q1, t1)]}}}}}


def test_insta360_rig_makes_lens1_relative_to_lens0():
    r0 = Rotation.from_euler("xyz", [10, -20, 30], degrees=True)
    rel = Rotation.from_euler("y", 180, degrees=True)
    lens = _lens_json(r0.as_quat(), (rel * r0).as_quat(), [0.0, 0.0, -0.0713])
    ref, other = insta360_rig(lens)
    assert (ref.folder, other.folder) == ("lens0", "lens1")
    assert Rotation.from_quat(ref.quat_xyzw).magnitude() == pytest.approx(0, abs=1e-9)
    assert (Rotation.from_quat(other.quat_xyzw) * rel.inv()).magnitude() == pytest.approx(0, abs=1e-9)
    assert other.translation == (0.0, 0.0, -0.0713)


def test_workspace_uses_rig_layout_and_colmap_mask_names(tmp_path):
    frames, masks = tmp_path / "frames", tmp_path / "masks"
    for cam in ("lens0", "lens1"):
        (frames / cam).mkdir(parents=True)
        (masks / cam).mkdir(parents=True)
        (frames / cam / "000005.jpg").write_bytes(b"jpg")
        (masks / cam / "000005.png").write_bytes(b"png")
    fs = FrameSet("CLIP", frames, masks, {"lens0": "lens0", "lens1": "lens1"}, (("lens0", 5), ("lens1", 5)))
    by_folder = stage_workspace([fs], tmp_path / "ws")
    assert by_folder == {"lens0": ["lens0/CLIP__000005.jpg"], "lens1": ["lens1/CLIP__000005.jpg"]}
    assert (tmp_path / "ws/images/lens1/CLIP__000005.jpg").read_bytes() == b"jpg"
    assert (tmp_path / "ws/masks/lens1/CLIP__000005.jpg.png").read_bytes() == b"png"
