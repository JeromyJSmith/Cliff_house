"""Stage: poses — COLMAP structure from motion over the frames, with the A1's two lenses solved as one rig.

Workspace layout is what COLMAP's rig support keys on: one folder per physical camera, and identical file names for
images taken at the same instant (`lens0/<clip>__000005.jpg` and `lens1/<clip>__000005.jpg`). A folder is one camera
across every clip that used it, so each lens is calibrated once from all its frames. Masks follow COLMAP's convention
(`<mask root>/<image name>.png`, 0 = ignore), which is the masks stage's convention too.

Following COLMAP 4's rig workflow: solve once without the rig, derive the lens-to-lens transform from that solve
(`apply_rig_config`), then solve again with the rig constraint. Scale stays arbitrary: nothing here is metric.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Literal

import pycolmap


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
class Params:
    rig_folders: tuple[str, ...] = ("lens0", "lens1")   # first is the rig's reference sensor
    priors: dict[str, CameraPrior] = field(default_factory=lambda: dict(A1_LENS_PRIORS))
    unknown_camera_model: str = "OPENCV"                 # cameras without a prior (phones) are estimated
    overlap: int = 15
    mapper: Literal["global", "incremental"] = "global"
    max_image_size: int = 3200


@dataclass(frozen=True)
class FrameSet:
    clip: str
    frames_dir: Path      # contains <camera>/<frame:06d>.jpg
    masks_dir: Path       # contains <camera>/<frame:06d>.png
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


def _extract(db: Path, out: Path, by_folder: dict[str, list[str]], params: Params) -> None:
    for folder, names in sorted(by_folder.items()):
        prior = params.priors.get(folder)
        reader = pycolmap.ImageReaderOptions()
        reader.mask_path = str(out / "masks")
        reader.camera_model = prior.model if prior else params.unknown_camera_model
        reader.camera_params = ",".join(map(str, prior.params)) if prior else ""
        extraction = pycolmap.FeatureExtractionOptions()
        extraction.max_image_size = params.max_image_size
        pycolmap.extract_features(db, out / "images", image_names=names, camera_mode=pycolmap.CameraMode.PER_FOLDER,
                                  reader_options=reader, extraction_options=extraction)


def _rig_config(params: Params) -> pycolmap.RigConfig:
    config = pycolmap.RigConfig()
    config.cameras = [pycolmap.RigConfigCamera(ref_sensor=(i == 0), image_prefix=f"{f}/")
                      for i, f in enumerate(params.rig_folders)]
    return config


def _map(db: Path, out: Path, sparse: Path, params: Params) -> dict[int, pycolmap.Reconstruction]:
    sparse.mkdir(parents=True, exist_ok=True)
    if params.mapper == "global":
        return pycolmap.global_mapping(db, out / "images", sparse)
    return pycolmap.incremental_mapping(db, out / "images", sparse)


def largest(models: dict[int, pycolmap.Reconstruction]) -> pycolmap.Reconstruction:
    if not models:
        raise RuntimeError("SfM produced no model")
    return max(models.values(), key=lambda r: r.num_reg_images())


def solve(sets: Iterable[FrameSet], out: Path, params: Params) -> pycolmap.Reconstruction:
    """Two-pass rig-aware SfM; writes <out>/sparse/0 (final) and returns the final reconstruction."""
    sets = list(sets)
    by_folder = stage_workspace(sets, out)
    db = out / "database.db"
    db.unlink(missing_ok=True)
    _extract(db, out, by_folder, params)
    pairing = pycolmap.SequentialPairingOptions()
    pairing.overlap = params.overlap
    pairing.quadratic_overlap = True
    pycolmap.match_sequential(db, pairing_options=pairing)

    unconstrained = largest(_map(db, out, out / "sparse_norig", params))
    with pycolmap.Database.open(db) as database:
        pycolmap.apply_rig_config([_rig_config(params)], database, unconstrained)
    final = largest(_map(db, out, out / "sparse_rig", params))
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
            "rigs": len(rec.rigs), "frames": len(rec.frames), "cameras": cameras}
