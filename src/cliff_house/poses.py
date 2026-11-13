"""Stage: poses — COLMAP structure from motion over the frames, with the A1's two lenses solved as one rig.

Workspace layout is what COLMAP's rig support keys on: one folder per physical camera, and identical file names for
images taken at the same instant (`lens0/<clip>__000005.jpg` and `lens1/<clip>__000005.jpg`). A folder is one camera
across every clip that used it, so each lens is calibrated once from all its frames. Masks come from the
training_masks stage (people ∪ landing gear ∪ aircraft body), never the people-only masks stage, and follow COLMAP's
convention (`<mask root>/<image name>.png`, 0 = ignore, 255 = use), the one polarity of every training input.

The lens-to-lens transform comes from the camera's factory rig calibration (Insta360 `lens.json`, decoded by the
telemetry stage): lens 1 is rotated ~180° from lens 0 and offset 71.3 mm. On clip 041 every reading of that record
converged under bundle adjustment to the same transform, with the translation sign as stored, so the stored record
is used as-is. Because the baseline is a factory length in metres and bundle adjustment holds its norm, the solve is
expressed in metres — a scale hint from a 7 cm baseline, to be checked against LiDAR, not a survey measurement.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Literal

import numpy as np
import pycolmap
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class CameraPrior:
    model: str
    params: tuple[float, ...]


# Calibration transferred from the earlier clip-041 solve (OPENCV_FISHEYE, principal point at the image centre).
# A transferred prior, not an independent calibration: the solve refines it.
A1_LENS_PRIORS = {
    "lens0": CameraPrior("OPENCV_FISHEYE", (1102.302, 1100.1837, 1920.0, 1920.0, 0.0262, 0.0009, -0.0035, 0.0002)),
    "lens1": CameraPrior("OPENCV_FISHEYE", (1112.2607, 1110.2465, 1920.0, 1920.0, -0.0187, 0.0387, -0.0155, 0.0014)),
}


@dataclass(frozen=True)
class RigSensor:
    folder: str
    quat_xyzw: tuple[float, float, float, float]   # cam_from_rig rotation
    translation: tuple[float, float, float]        # cam_from_rig translation, metres


def insta360_rig(lens_json: dict, folders: tuple[str, ...] = ("lens0", "lens1")) -> tuple[RigSensor, ...]:
    """Rig sensors from an Insta360 lens.json: the first camera is the reference; the others get R_i · R_0⁻¹ and their
    stored translation (the reading bundle adjustment confirmed on clip 041)."""
    cams = lens_json["rig"]["projection"]["kind"]["Rig"]["cameras"]
    rot = [Rotation.from_quat([c["rotation"][k] for k in "xyzw"]) for c in cams]
    return tuple(RigSensor(folder, tuple((rot[i] * rot[0].inv()).as_quat()), tuple(cams[i]["translation"]))
                 for i, folder in enumerate(folders))


@dataclass(frozen=True)
class Params:
    rig: tuple[RigSensor, ...] = ()                  # first entry is the reference sensor; empty = no rig
    priors: dict[str, CameraPrior] = field(default_factory=lambda: dict(A1_LENS_PRIORS))
    unknown_camera_model: str = "OPENCV"             # cameras without a prior (phones) are estimated
    overlap: int = 15
    mapper: Literal["global", "incremental"] = "incremental"   # global (GLOMAP) fragmented short walkthroughs
    max_image_size: int = 1600                       # SIFT on 3840² fisheye at 1600 px: 4x faster, same solve


@dataclass(frozen=True)
class FrameSet:
    clip: str
    frames_dir: Path      # contains <camera>/<frame:06d>.jpg
    masks_dir: Path       # training_masks stage output: <camera>/<frame:06d>.png, 0 = ignore, 255 = use
    folders: dict[str, str]   # camera id in the frame set -> workspace folder (= COLMAP camera)
    frames: tuple[tuple[str, int], ...]   # (camera, frame) pairs to include


def fingerprint(frame_set_fingerprints: Iterable[str], params: Params) -> str:
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for part in (*sorted(frame_set_fingerprints), json.dumps(asdict(params), sort_keys=True, default=str)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


def stage_workspace(sets: Iterable[FrameSet], out: Path) -> dict[str, list[str]]:
    """Link frames and masks into COLMAP's layout; returns image names grouped by folder (camera)."""
    by_folder: dict[str, list[str]] = {}
    for s in sets:
        for camera, frame in s.frames:
            name = f"{s.folders[camera]}/{s.clip}__{frame:06d}.jpg"
            for src, dst in ((s.frames_dir / camera / f"{frame:06d}.jpg", out / "images" / name),
                             (s.masks_dir / camera / f"{frame:06d}.png", out / "masks" / f"{name}.png")):
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.unlink(missing_ok=True)
                os.symlink(src.resolve(), dst)
            by_folder.setdefault(s.folders[camera], []).append(name)
    return {k: sorted(v) for k, v in by_folder.items()}


def _extract(db: Path, out: Path, folder: str, names: list[str], params: Params, camera_id: int) -> int:
    """Extract one batch of a folder's images into that folder's camera (-1: create it); returns the camera's id."""
    prior = params.priors.get(folder)
    reader = pycolmap.ImageReaderOptions()
    reader.mask_path = str(out / "masks")
    reader.camera_model = prior.model if prior else params.unknown_camera_model
    reader.camera_params = ",".join(map(str, prior.params)) if prior else ""
    reader.existing_camera_id = camera_id
    extraction = pycolmap.FeatureExtractionOptions()
    extraction.max_image_size = params.max_image_size
    pycolmap.extract_features(db, out / "images", image_names=names, camera_mode=pycolmap.CameraMode.SINGLE,
                              reader_options=reader, extraction_options=extraction)
    with pycolmap.Database.open(db) as database:
        return database.read_image_with_name(names[0]).camera_id


def _rig_config(params: Params) -> pycolmap.RigConfig:
    config = pycolmap.RigConfig()
    cameras = []
    for i, sensor in enumerate(params.rig):
        cam = pycolmap.RigConfigCamera(ref_sensor=(i == 0), image_prefix=f"{sensor.folder}/")
        if i:
            cam.cam_from_rig = pycolmap.Rigid3d(pycolmap.Rotation3d(np.array(sensor.quat_xyzw)),
                                                np.array(sensor.translation))
        cameras.append(cam)
    config.cameras = cameras
    return config


def _map(db: Path, out: Path, sparse: Path, params: Params,
         next_image: Callable[[], None]) -> dict[int, pycolmap.Reconstruction]:
    sparse.mkdir(parents=True, exist_ok=True)
    if params.mapper == "global":
        return pycolmap.global_mapping(db, out / "images", sparse)
    return pycolmap.incremental_mapping(db, out / "images", sparse, next_image_callback=next_image)


def largest(models: dict[int, pycolmap.Reconstruction]) -> pycolmap.Reconstruction:
    if not models:
        raise RuntimeError("SfM produced no model")
    return max(models.values(), key=lambda r: r.num_reg_images())


Progress = Callable[[str, int, int], None]
"""(step, done, total), called from the caller's thread: after every batch, and every 2 s while mapping runs."""

STEPS = ("features", "rig", "matching", "mapping")
# Steps run in batches so progress is reported between COLMAP calls. Nothing reads the database while COLMAP writes
# it: a second connection broke the solve twice (Python's sqlite3: "database disk image is malformed"; pycolmap's own:
# "No registered database factory succeeded").
BATCH_IMAGES = 64
BATCH_PAIRS = 4096


def _batches(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _map_reporting(db: Path, out: Path, params: Params, progress: Progress, total: int):
    """Mapping is one COLMAP call: run it on a worker thread, reporting its registered-image count from this one."""
    registered, result = [0], {}

    def next_image():
        registered[0] += 1

    def target():
        try:
            result["value"] = _map(db, out, out / "sparse_all", params, next_image)
        except BaseException as e:  # re-raised below, in the caller's thread
            result["error"] = e
    worker = threading.Thread(target=target, name="colmap-mapping")
    worker.start()
    while worker.is_alive():
        progress("mapping", registered[0], total)
        worker.join(timeout=2.0)
    progress("mapping", registered[0], total)
    if "error" in result:
        raise result["error"]
    return result["value"]


def solve(sets: Iterable[FrameSet], out: Path, params: Params, progress: Progress) -> pycolmap.Reconstruction:
    """Rig-constrained SfM; writes <out>/sparse/0 and returns the largest reconstruction."""
    by_folder = stage_workspace(sets, out)
    images = sum(len(v) for v in by_folder.values())
    db = out / "database.db"
    db.unlink(missing_ok=True)
    # COLMAP's per-image INFO log goes through the notebook's console capture. In the molab kernel, rig setup crawled
    # under it (419 of 2,176 frames in 2.5 h); the same step on the same database in a plain process took 0.4 s.
    pycolmap.logging.minloglevel = pycolmap.logging.WARNING

    done = 0
    for folder, names in sorted(by_folder.items()):
        camera_id = -1
        for batch in _batches(names, BATCH_IMAGES):
            camera_id = _extract(db, out, folder, batch, params, camera_id)
            done += len(batch)
            progress("features", done, images)

    with pycolmap.Database.open(db) as database:
        pycolmap.apply_rig_config([_rig_config(params)] if params.rig else [], database)
        progress("rig", database.num_frames(), database.num_frames())

    pairing = pycolmap.SequentialPairingOptions()
    pairing.overlap = params.overlap
    pairing.quadratic_overlap = True
    with pycolmap.Database.open(db) as database:
        pairs = pycolmap.SequentialPairGenerator(pairing, database).all_pairs()
        name = {image.image_id: image.name for image in database.read_all_images()}
    pair_list, done = out / "pairs.txt", 0
    for batch in _batches(pairs, BATCH_PAIRS):
        pair_list.write_text("".join(f"{name[a]} {name[b]}\n" for a, b in batch))
        imported = pycolmap.ImportedPairingOptions()
        imported.match_list_path = pair_list
        pycolmap.match_image_pairs(db, pairing_options=imported)
        done += len(batch)
        progress("matching", done, len(pairs))

    final = largest(_map_reporting(db, out, params, progress, images))
    (out / "sparse" / "0").mkdir(parents=True, exist_ok=True)
    final.write(out / "sparse" / "0")
    return final


def summary(rec: pycolmap.Reconstruction, total_images: int) -> dict:
    """Health of a solve: judged by points and track length, not just the registered count (SPEC §5)."""
    cameras = {}
    for cid, cam in rec.cameras.items():
        names = [i.name for i in rec.images.values() if i.camera_id == cid]
        folder = names[0].split("/")[0] if names else str(cid)
        cameras[folder] = {"model": cam.model.name, "params": [round(float(x), 4) for x in cam.params],
                           "registered": len(names)}
    return {"registered_images": rec.num_reg_images(), "total_images": total_images,
            "points3D": rec.num_points3D(), "mean_track_length": round(float(rec.compute_mean_track_length()), 3),
            "mean_reprojection_error_px": round(float(rec.compute_mean_reprojection_error()), 3),
            "rigs": len(rec.rigs), "frames": len(rec.frames), "cameras": cameras,
            "rig_baselines_m": [round(float(np.linalg.norm(t.translation)), 4) for rig in rec.rigs.values()
                                for t in rig.non_ref_sensors.values()]}
