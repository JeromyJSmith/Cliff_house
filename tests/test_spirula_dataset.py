"""spirula_dataset: the COLMAP dataset Spirula trains from, built from a poses model + frames + training masks.

A small synthetic COLMAP model is written with pycolmap (known camera poses, two lenses, two clips, one image left
unregistered). Frames carry a distinct constant brightness per image and masks a distinct unmasked fraction per image, so a
dataset that links the wrong frame or mask, or leaves an unregistered frame in, fails on values. Spirula's own parser
is an independent oracle for the file layout in two places: an in-test reader of the classic COLMAP `images.bin` layout
(what Spirula's `ColmapParser` reads) and, when the app is installed, `spirula train --help-all` for every flag in the
argv. No real footage and no network are used.
"""
import json
import shutil
import struct
import subprocess
from pathlib import Path

import cv2
import numpy as np
import polars as pl
import pycolmap
import pytest
from scipy.spatial.transform import Rotation

from cliff_house import spirula_dataset as sd

N = 48
CLIPS = ("VID_20261110_131538_036", "VID_20261110_131644_037")
FRAMES = {CLIPS[0]: (0, 5), CLIPS[1]: (0, 5)}          # frames kept per clip
UNREGISTERED = (CLIPS[1], "lens1", 5)                  # extracted and masked, but the solve did not place it
SPIRULA = Path("/Applications/Spirula Studio.app/Contents/MacOS/spirula")


def _pose(k: int):
    """Camera k: a known rotation about y and a known centre on the x axis; returns (cam_from_world Rigid3d, centre)."""
    centre = np.array([0.1 * k, 0.0, 0.02 * k])
    rot = Rotation.from_euler("y", 3.0 * k, degrees=True)
    t = -rot.as_matrix() @ centre
    return pycolmap.Rigid3d(pycolmap.Rotation3d(rot.as_quat()), t), centre


def _use_fraction(clip: str, lens: str, frame: int) -> float:
    return 0.60 + 0.05 * CLIPS.index(clip) + 0.05 * int(lens[-1]) + 0.01 * frame   # distinct per image, 0.60–0.75


def _brightness(clip: str, lens: str, frame: int) -> int:
    return 10 + 40 * CLIPS.index(clip) + 100 * int(lens[-1]) + 5 * frame


def _write_dataset_inputs(root: Path):
    """frames/<clip>/<lens>/<frame:06d>.jpg, masks/<clip>/<lens>/<frame:06d>.png (training_masks layout, 255 = use)."""
    for clip, (lo, hi) in FRAMES.items():
        for lens in ("lens0", "lens1"):
            for frame in range(lo, hi + 1):
                f = root / "frames" / clip / lens / f"{frame:06d}.jpg"
                m = root / "masks" / clip / lens / f"{frame:06d}.png"
                f.parent.mkdir(parents=True, exist_ok=True)
                m.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(f), np.full((N, N, 3), _brightness(clip, lens, frame), np.uint8))
                mask = np.zeros(N * N, np.uint8)
                mask[: round(_use_fraction(clip, lens, frame) * N * N)] = 255
                cv2.imwrite(str(m), mask.reshape(N, N))


def _write_model(sparse: Path) -> dict[str, np.ndarray]:
    """A COLMAP model with one fisheye camera per lens and a registered image per (clip, lens, frame) except
    UNREGISTERED; returns the camera centre of each image by name."""
    rec = pycolmap.Reconstruction()
    cams = {}
    for lens, f in (("lens0", 1100.0), ("lens1", 1112.0)):
        cam = pycolmap.Camera(model="OPENCV_FISHEYE", width=N, height=N,
                              params=[f, f, N / 2, N / 2, 0.02, 0.0, 0.0, 0.0], camera_id=1 + int(lens[-1]))
        rec.add_camera_with_trivial_rig(cam)
        cams[lens] = cam.camera_id
    centres, k = {}, 0
    for clip, (lo, hi) in FRAMES.items():
        for frame in range(lo, hi + 1):
            for lens in ("lens0", "lens1"):
                if (clip, lens, frame) == UNREGISTERED:
                    continue
                k += 1
                cam_from_world, centre = _pose(k)
                name = f"{lens}/{clip}__{frame:06d}.jpg"
                image = pycolmap.Image(name=name, camera_id=cams[lens], image_id=k)
                rec.add_image_with_trivial_frame(image, cam_from_world)
                centres[name] = centre
    rec.add_point3D(np.array([0.0, 0.0, 5.0]), pycolmap.Track(), np.array([128, 128, 128], np.uint8))
    sparse.mkdir(parents=True, exist_ok=True)
    rec.write(sparse)
    return centres


@pytest.fixture
def world(tmp_path):
    _write_dataset_inputs(tmp_path)
    sparse = tmp_path / "poses" / "sparse" / "0"
    centres = _write_model(sparse)
    clips = [sd.ClipInputs(c, tmp_path / "frames" / c, f"fr-{c[-3:]}", tmp_path / "masks" / c, f"tm-{c[-3:]}")
             for c in CLIPS]
    return tmp_path, sparse, clips, centres


def _plan(world, params=sd.Params()):
    _, sparse, clips, _ = world
    return sd.plan(sparse, "poses123", clips, params)


# --- names, plan ----------------------------------------------------------------------------------------------------

def test_parse_image_name():
    assert sd.parse_image_name(f"lens1/{CLIPS[0]}__000123.jpg") == ("lens1", CLIPS[0], 123)
    for bad in ("lens0/frame.jpg", f"{CLIPS[0]}/{CLIPS[0]}__000001.jpg.png", "lens0/a__12.jpg"):
        with pytest.raises(sd.DatasetError):
            sd.parse_image_name(bad)


def test_plan_lists_exactly_the_registered_images_with_their_own_files(world):
    root, _, _, _ = world
    p = _plan(world)
    assert len(p.images) == 2 * 2 * 6 - 1                       # 2 clips x 2 lenses x 6 frames, one unplaced
    assert (UNREGISTERED[1] + "/" + f"{UNREGISTERED[0]}__{UNREGISTERED[2]:06d}.jpg") not in {i.name for i in p.images}
    for i in p.images:
        assert i.frame_file == root / "frames" / i.clip / i.lens / f"{i.frame:06d}.jpg"
        assert i.mask_file == root / "masks" / i.clip / i.lens / f"{i.frame:06d}.png"
        assert (i.width, i.height) == (N, N)


def test_plan_refuses_phone_style_names_and_unknown_clips(world):
    root, sparse, clips, _ = world
    with pytest.raises(sd.DatasetError, match="360 footage only"):
        sd.plan(sparse, "p", clips, sd.Params(lenses=("lens0",)))            # lens1 images are then foreign cameras
    with pytest.raises(sd.DatasetError, match="no frames/masks were given for clip"):
        sd.plan(sparse, "p", clips[:1])


def test_plan_names_a_missing_frame_or_mask(world):
    root, *_ = world
    (root / "masks" / CLIPS[0] / "lens0" / "000002.png").unlink()
    (root / "frames" / CLIPS[1] / "lens1" / "000003.jpg").unlink()
    with pytest.raises(sd.DatasetError, match="2 registered images lack a file"):
        _plan(world)


def test_plan_needs_the_three_core_model_files(world):
    _, sparse, clips, _ = world
    (sparse / "points3D.bin").unlink()
    with pytest.raises(sd.DatasetError, match="points3D.bin"):
        sd.plan(sparse, "p", clips)


# --- fingerprint ----------------------------------------------------------------------------------------------------

def test_fingerprint_follows_every_input(world):
    _, sparse, clips, _ = world
    base = sd.plan(sparse, "poses123", clips).fingerprint
    assert len(base) == 16 and base == sd.plan(sparse, "poses123", list(reversed(clips))).fingerprint
    assert sd.plan(sparse, "poses124", clips).fingerprint != base                       # poses
    changed = [clips[0], sd.ClipInputs(clips[1].clip, clips[1].frames_dir, clips[1].frames_fingerprint,
                                       clips[1].masks_dir, "tm-other")]
    assert sd.plan(sparse, "poses123", changed).fingerprint != base                    # training masks
    assert sd.plan(sparse, "poses123", clips, sd.Params(iterations=1000)).fingerprint != base   # parameters


# --- check ----------------------------------------------------------------------------------------------------------

def test_check_measures_each_masks_use_fraction(world):
    table = sd.check(_plan(world))
    assert table.height == 23
    for r in table.iter_rows(named=True):
        want = round(_use_fraction(r["clip"], r["lens"], r["frame"]) * N * N) / (N * N)
        assert r["use_fraction"] == pytest.approx(want, abs=1e-9)
        assert (r["width"], r["height"]) == (N, N)


def test_check_rejects_wrong_size_mask_and_frame(world):
    root, *_ = world
    cv2.imwrite(str(root / "masks" / CLIPS[0] / "lens0" / "000001.png"), np.full((N, N + 2), 255, np.uint8))
    cv2.imwrite(str(root / "frames" / CLIPS[0] / "lens1" / "000001.jpg"), np.zeros((N + 2, N, 3), np.uint8))
    with pytest.raises(sd.DatasetError) as e:
        sd.check(_plan(world))
    assert "mask size" in str(e.value) and "frame size" in str(e.value)


def test_check_rejects_grey_masks(world):
    root, *_ = world
    cv2.imwrite(str(root / "masks" / CLIPS[0] / "lens0" / "000001.png"), np.full((N, N), 128, np.uint8))
    with pytest.raises(sd.DatasetError, match="mask not 0/255"):
        sd.check(_plan(world))


def test_check_rejects_a_nearly_empty_mask(world):
    root, *_ = world
    cv2.imwrite(str(root / "masks" / CLIPS[1] / "lens0" / "000004.png"), np.zeros((N, N), np.uint8))
    with pytest.raises(sd.DatasetError, match="nearly empty.*000004"):
        sd.check(_plan(world))


def test_check_catches_inverted_masks_by_the_dataset_median(world):
    root, *_ = world
    for m in (root / "masks").rglob("*.png"):
        img = cv2.imread(str(m), cv2.IMREAD_UNCHANGED)
        cv2.imwrite(str(m), 255 - img)          # 255 = subject now: only 25–40 % of each frame left to train on
    with pytest.raises(sd.DatasetError, match="look inverted"):
        sd.check(_plan(world, sd.Params(min_use_fraction=0.01)))


# --- build ----------------------------------------------------------------------------------------------------------

def test_build_links_each_image_and_mask_to_its_own_source(world, tmp_path):
    p = _plan(world)
    out = tmp_path / "out"
    meta = sd.build(p, out)
    linked_images = sorted(x.relative_to(out / "images").as_posix() for x in (out / "images").rglob("*.jpg"))
    assert linked_images == sorted(i.name for i in p.images)               # the unregistered frame is not linked
    for i in p.images:
        img = cv2.imread(str(out / "images" / i.name))
        assert int(img[0, 0, 0]) == _brightness(i.clip, i.lens, i.frame)    # the right frame behind the name
        mask = cv2.imread(str(out / "masks" / f"{i.name}.png"), cv2.IMREAD_UNCHANGED)
        assert set(np.unique(mask)) <= {0, 255}
        assert (mask == 255).mean() == pytest.approx(round(_use_fraction(i.clip, i.lens, i.frame) * N * N) / N**2)
    assert meta["acceptance"]["ok"] and meta["acceptance"]["images"] == 23
    assert meta["acceptance"]["images_per_lens"] == {"lens0": 12, "lens1": 11}
    on_disk = json.loads((out / "dataset.json").read_text())
    assert on_disk["fingerprint"] == p.fingerprint and on_disk["poses_fingerprint"] == "poses123"
    assert on_disk["clips"][CLIPS[0]] == {"frames": "fr-036", "training_masks": "tm-036"}
    table = pl.read_parquet(out / "dataset.parquet")
    assert table.height == 23 and "frame_file" not in table.columns


def test_built_sparse_model_has_the_input_poses_and_cameras(world, tmp_path):
    _, _, _, centres = world
    out = tmp_path / "out"
    sd.build(_plan(world), out)
    rec = pycolmap.Reconstruction(out / "sparse" / "0")
    assert rec.num_reg_images() == 23 and rec.num_points3D() == 1
    for image in rec.images.values():
        np.testing.assert_allclose(image.projection_center(), centres[image.name], atol=1e-9)
    assert {c.model.name for c in rec.cameras.values()} == {"OPENCV_FISHEYE"}
    assert sorted(float(c.params[0]) for c in rec.cameras.values()) == [1100.0, 1112.0]


def test_images_bin_is_the_classic_colmap_layout_spirula_reads(world, tmp_path):
    """Read images.bin by hand: id, qvec(wxyz), tvec, camera_id, NUL-terminated name, points2D. Names are relative to
    images/, so `images/<name>` resolves to a linked frame."""
    _, _, _, centres = world
    out = tmp_path / "out"
    sd.build(_plan(world), out)
    data = (out / "sparse" / "0" / "images.bin").read_bytes()
    (count,) = struct.unpack_from("<Q", data, 0)
    off, seen = 8, {}
    for _ in range(count):
        image_id, qw, qx, qy, qz, tx, ty, tz, cam_id = struct.unpack_from("<I4d3dI", data, off)
        off += struct.calcsize("<I4d3dI")
        end = data.index(b"\0", off)
        name = data[off:end].decode()
        (n2d,) = struct.unpack_from("<Q", data, end + 1)
        off = end + 1 + 8 + n2d * struct.calcsize("<2dq")
        assert (out / "images" / name).is_file()
        centre = -Rotation.from_quat([qx, qy, qz, qw]).inv().as_matrix() @ np.array([tx, ty, tz])
        seen[name] = centre
    assert off == len(data) and set(seen) == set(centres)
    for name, centre in seen.items():
        np.testing.assert_allclose(centre, centres[name], atol=1e-9)


# --- train.json -----------------------------------------------------------------------------------------------------

def test_train_json_is_headless_and_points_at_this_dataset(world, tmp_path):
    p = _plan(world)
    out = tmp_path / "out"
    sd.build(p, out, output_prefix=tmp_path / "runs")
    train = json.loads((out / "train.json").read_text())
    argv = train["argv"]
    assert argv[:2] == ["train", "360-camera"] and train["binary"] == "spirula"
    flag = {a: argv[k + 1] for k, a in enumerate(argv) if a.startswith("--")}
    assert flag["--data"] == str(out) and flag["--data-format"] == "colmap"
    assert (flag["--image-dir"], flag["--mask-dir"], flag["--colmap-recon-dir"]) == ("images", "masks", "sparse/0")
    assert flag["--output-dir-name"] == f"spirula-{p.fingerprint}" and flag["--output-dir-prefix"] == str(tmp_path / "runs")
    assert (flag["--disable-viewer"], flag["--keep-viewer-alive"]) == ("1", "0")     # otherwise the process never exits
    assert flag["--num-iterations"] == "50000" and flag["--steps-per-save"] == "2000"


@pytest.mark.skipif(not SPIRULA.exists(), reason="Spirula Studio is not installed here")
def test_every_train_flag_exists_in_this_spirulas_help(tmp_path):
    help_all = subprocess.run([str(SPIRULA), "train", "--help-all"], capture_output=True, text=True, timeout=120).stdout
    argv = sd.train_args(tmp_path / "ds", tmp_path / "runs", "run")
    preset = argv[1]
    assert preset in help_all
    for flag in (a for a in argv if a.startswith("--")):
        assert f"\n  {flag} " in help_all, f"{flag} is not a `spirula train` flag in this build"
