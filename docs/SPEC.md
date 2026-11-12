# Cliff House digital twin — notebook blueprint

This document is the recovery blueprint. If every session, machine and chat is lost, this file plus the
Hugging Face storage and this repository are enough to rebuild the workbench notebook and continue.
It states the decisions, the theory the notebook is built on, each stage's contract, and where every borrowed
idea comes from.

- Repository (public): <https://github.com/JeromyJSmith/Cliff_house>
- Workbench notebook: [`notebooks/cliff_house.py`](../notebooks/cliff_house.py) — open in molab at
  <https://molab.marimo.io/github/JeromyJSmith/Cliff_house/blob/main/notebooks/cliff_house.py>
- Sources (private, versioned): `hf://datasets/ojeromyo/frasier-cliff-house`
- Outputs (private, mutable): `hf://buckets/ojeromyo/frasier-cliff-house`
- Research inputs: [`docs/research/`](research/) (paper survey, harvested notebook cells)

## 1. Goal

Turn the Insta360 walkthrough video and phone LiDAR scans of the property into:

1. a photoreal **Gaussian splat** of the site, and
2. **measured geometry** (registered point clouds and meshes) whose scale is known where — and only where — it
   is constrained by evidence (LiDAR, markers, control distances),

then hand both to Blender (on the owner's Apple-silicon MacBook Pro) and later to IFC/BIM. Unknown pose, scale or
registration is recorded as unknown, never as zero or as a guess.

## 2. Decisions (owner direction, 2026-11-12)

| Decision | Consequence |
|---|---|
| **Everything runs in the Marimo notebook** on molab (cloud, Linux x86_64, NVIDIA GPU). | No local pipelines; the iMac only holds originals, uploads them, and runs tests. |
| **Hugging Face is the only durable store.** | molab keeps nothing over 1 GB and clears scratch at shutdown, so every session rebuilds from HF and writes back to HF. |
| **Pixeltable runs inside the notebook**, in session scratch. | Pixeltable is a derived, per-session catalog — never the system of record. |
| **Sources → versioned dataset repo; outputs → storage bucket.** | Sources never change (git history protects them); outputs are overwritten freely (no history to pay for). Bucket deletes are permanent — never sync with `--delete` against sources. |
| **Polars + polars-st, DuckDB spatial, GeoParquet** for tabular and spatial data. | DuckDB writes GeoParquet (`COPY … TO` with a GEOMETRY column emits `geo` metadata); polars-st reads it via `st.from_wkb`. |
| **Client-first layout**: `<client>/<property>/<kind>/…`; shared assets under `_shared/`. | Every path is identical locally (`data/…`) and on HF (`hf://datasets/<repo>/…`). No spaces in any path. |
| **Repo is public** so molab can mirror the notebook. | Never commit tokens, `.env`, footage or client data. `HF_TOKEN` lives in molab's Secrets panel (`.env`, not forked). |
| **Non-commercial project; borrow freely, respect licenses.** | Cells may come from MIT/Apache-2.0/BSD **and** non-commercial licenses (CC BY-NC, CC BY-NC-SA, Inria GS) with the license notice and attribution kept in the cell (the repo is public; BY-NC-SA adaptations stay BY-NC-SA). Repos with no license grant nothing — reimplement from the idea only. |
| **Blender runs on the MacBook Pro**, not the Intel iMac (Blender ≥ 5.0 dropped Intel macOS). | Export stages produce files Blender opens; they do not drive Blender. |

## 3. Theory of the notebook

### 3.1 A session is a pure function

```
session(code @ git SHA, sources @ dataset revision, bucket state) → new bucket objects
```

Nothing the notebook needs lives only in the session. Opening the notebook in a fresh molab session and running
all cells reproduces the catalog and continues the work. This is why a session dying (12-hour cap, 90-minute idle
shutdown, or the owner going to bed) costs time, not data.

### 3.2 One source of truth per concept

| Concept | Authority | Derived views |
|---|---|---|
| Source files | HF dataset repo + `_manifest/sources.parquet` (path, bytes, SHA-256, mtime, link target, capture time) | Pixeltable `sources` table |
| Stage outputs | HF bucket objects under `stages/<stage>/<fingerprint>/` with a per-stage manifest | Pixeltable tables per stage |
| Code and environment | This repo at a git SHA (`pyproject.toml`, `pixi.lock`, notebook PEP 723 header) | the molab kernel and the pixi env |
| Decisions and design | This spec | `CLAUDE.md`, commit messages |

### 3.3 Stages are dataflow, not control flow

Every stage runs on every session. Which work it does is decided by data: a stage computes the **fingerprint**
of each work item (input SHA-256s + stage code version + parameters), lists what already exists in the bucket,
and processes exactly the missing fingerprints. Changing a parameter changes the fingerprint, so new outputs are
produced beside old ones instead of overwriting them; the stage manifest says which fingerprint is current.
Restart after an interruption is therefore idempotent by construction, not by bookkeeping.

### 3.4 Pixeltable's role

Pixeltable gives each stage a typed table with computed columns (frame iterators over video, model outputs per
frame) and lineage inside the session. Tables are rebuilt from the manifest and stage manifests at session start;
heavy outputs (frames, depth maps, splats) are files in the bucket referenced by path, not blobs in the catalog.

### 3.5 Coordinates and units

Each reconstruction lives in its own frame with **arbitrary SfM units** until a scale constraint is applied.
Every geometry record carries a `coordinate_frame_id`. Transforms between frames (SfM ↔ LiDAR ↔ property-local
metres ↔ Blender Z-up) are explicit, versioned records with direction and provenance. Gravity alignment from the
camera's IMU/upward lens axis is an estimate, not a survey datum.

## 4. Inputs

| Input | Location | Facts |
|---|---|---|
| Insta360 `.insv` video (8 clips, 2026-11-10; 1 clip 2026-11-09 kept with an earlier Spirula run) | `frasier/cliff-house/source/video/<date>/` | Two H.264 video streams per file, one per fisheye lens, **3840×3840 at 29.97 fps**, plus a `mov_text` stream. Embedded `creation_time` is authoritative; filename clock is off by an hour on at least one clip. |
| Prior evidence (registrations, COLMAP/OpenMVS runs, contact sheets) | `frasier/cliff-house/evidence/2026-11-11/` | Produced on the MacBook; symlinks repointed relative. See repo `docs/*-20261111/`. |
| Spirula runs (excluded from the new workflow, retained) | `frasier/cliff-house/runs/spirula/` | Contains per-lens fisheye calibration from the clip 041 solve. |
| Unqualified OBJ | `frasier/cliff-house/reconstructions/meshes/unqualified-processed-model/` | No capture provenance; never building authority. |
| SAM 2.1 small checkpoint | `_shared/models/` | For person/sky masks. |

## 5. Stages

Each stage: inputs → outputs (bucket path + Pixeltable table) → acceptance check that blocks dependents.

| # | Stage | Inputs | Outputs | Acceptance |
|---|---|---|---|---|
| 0 | **Bootstrap** — token, manifest, Pixeltable `sources` | HF dataset | `sources` table; `sessions/<id>/sources_by_kind.parquet` | row count == manifest rows (implemented, tested) |
| 1 | **Toolchain** — pixi in the session installs the locked native tools (COLMAP, OpenMVS, ffmpeg, PDAL) | repo `pyproject.toml` + `pixi.lock` | `.pixi/envs/default/bin` path handed to later cells | each tool runs; pixi binary SHA-256 matches the pinned release digest |
| 2 | **Frames** — per-lens frame extraction with sharpness and overlap selection | `.insv` | `stages/frames/<fp>/<clip>/<lens>/*.jpg` + frame table (clip, lens, t, sharpness) | every selected frame traceable to (clip SHA, stream, timestamp); no frame below sharpness floor |
| 3 | **Masks** — people/sky/camera-operator masks | frames, SAM 2.1 | `stages/masks/<fp>/…png` | mask coverage stats per frame |
| 4 | **Poses** — SfM on fisheye frames (`OPENCV_FISHEYE`, one camera per lens) | frames, masks | `stages/poses/<fp>/sparse/0` (COLMAP model) | registered-image ratio, mean reprojection error, single connected component per segment |
| 5 | **Splat** — fisheye-native Gaussian splatting | poses, frames, masks (optionally depth/normals) | `stages/splat/<fp>/…ply` + metrics | held-out PSNR/SSIM/LPIPS per segment |
| 6 | **Geometry** — dense points / meshes; depth-normal supervised variants | poses, frames | `stages/geometry/<fp>/…` (PLY, GLB) | cloud↔mesh distance distribution; no invented surfaces |
| 7 | **Registration & scale** — LiDAR ↔ reconstruction ICP; marker/control scale | geometry, LiDAR PLYs | transform records (GeoParquet/Parquet) | held-out residuals; scale flagged *unknown* unless constrained |
| 8 | **Export** — Blender-ready GLB/PLY, GeoParquet footprints | all above | `stages/export/<fp>/…` | files open in Blender (checked on the MacBook) |

## 6. Toolchain

- Local and cloud environments come from one manifest, [`pyproject.toml`](../pyproject.toml), locked in
  [`pixi.lock`](../pixi.lock) for `osx-64`, `osx-arm64` and `linux-64`.
- Python packages: Pixeltable, Marimo (all extras: `recommended`, `lsp`, `mcp`, `otel`), Polars + polars-st,
  DuckDB, pyarrow, shapely, pyproj, huggingface_hub, OpenCV, Open3D, pycolmap, trimesh, plyfile, laspy, PyAV.
- Native: ffmpeg, exiftool, COLMAP 4.2, OpenMVS 2.4, PDAL, git-lfs (conda-forge).
- Packaging rules that the lock encodes: libraries wrapping native code (OpenCV, PyAV, shapely, pyproj, pyarrow)
  come from conda-forge so each native library loads once per process; all Qt consumers use Qt6.
- In molab the kernel's Python packages come from the notebook's PEP 723 header; native tools come from pixi
  (`pixi install --frozen`) inside the session.

## 7. Research

### 7.1 Papers (video → Gaussian splats and geometry)

_Filled from the 2026-11-12 survey — see [`research/`](research/)._

### 7.2 Notebooks and cells to adopt

_Filled from the 2026-11-12 cell harvest — see [`research/cell-harvest-2026-11-12.md`](research/cell-harvest-2026-11-12.md)._

### 7.3 Projects verified 2026-11-12

| Project | License | Use |
|---|---|---|
| [pixeltable/pixeltable](https://github.com/pixeltable/pixeltable) video/image cookbooks (`video-extract-frames`, `video-scene-detection`, `img-promptable-segmentation`) | Apache-2.0 | stages 2–3 |
| [nv-tlabs/3dgrut](https://github.com/nv-tlabs/3dgrut) (3DGUT: distorted/fisheye cameras in a rasterizer; COLMAP datasets; `threedgrut_playground/headless.ipynb`) | Apache-2.0 | stage 5 |
| [nerfstudio-project/gsplat](https://github.com/nerfstudio-project/gsplat), [nerfstudio](https://github.com/nerfstudio-project/nerfstudio) (`colab/demo.ipynb`) | Apache-2.0 | stage 5 |
| [abolhoseinisina/Colab_COLMAP_3DGS](https://github.com/abolhoseinisina/Colab_COLMAP_3DGS), [JittoJoseph/GaussianSplat-Colab](https://github.com/JittoJoseph/GaussianSplat-Colab) | MIT | stages 2, 4, 5 |
| [maturk/dn-splatter](https://github.com/maturk/dn-splatter) (depth/normal supervision, iPhone data, AGS-Mesh) | Apache-2.0 | stages 5–6 |
| [meyerls/aruco-estimator](https://github.com/meyerls/aruco-estimator) (scale a COLMAP model from ArUco markers) | MIT | stage 7 |
| Open3D ICP tutorials | MIT | stage 7 |
| [marimo-team/gallery-examples](https://github.com/marimo-team/gallery-examples) (`external/dlthub-huggingface.py`, `cad/trimesh-demo.py`) | MIT | stage 0, 8 |
| [HF blog: buckets as a working layer](https://huggingface.co/blog/davanstrien/buckets-as-working-layer) | — | storage pattern |
| [Cloud2BIM](https://arxiv.org/abs/2503.11498) (point cloud → IFC 4 via IfcOpenShell) | repo license unchecked | later BIM stage |
| libishm1/Colmap_Photogrammetry_Drone_video | **no license** — technique reference only | — |

## 8. Rebuild from nothing

1. Clone <https://github.com/JeromyJSmith/Cliff_house>; install [pixi](https://pixi.sh) and run `pixi install`,
   then `pixi run test` (needs an HF login with read on the dataset repo and write on the bucket).
2. `hf auth login` with a write token; confirm `hf auth whoami`.
3. Open the molab link above, add `HF_TOKEN` under **Secrets**, run all cells.
4. If the HF storage itself were lost: restore `data/` from the iMac originals (paths in §4), rebuild the
   manifest with `pixi run cliff-house-manifest ../data`, upload with
   `hf upload ojeromyo/frasier-cliff-house ../data . --repo-type dataset --exclude "**/.DS_Store"`, and verify with
   `pixi run cliff-house-verify-upload ../data ojeromyo/frasier-cliff-house` (exit 0 = byte-identical).

## 9. Open risks

- molab mirrors only **public** GitHub repos; the notebook must stay self-contained (no private imports).
- Bucket and private-repo storage appear to share the account quota (PRO: 1 TB, then $18/TB/month) — not stated
  explicitly by HF docs.
- Fisheye calibration from the earlier clip 041 solve is a transfer assumption, not an independent calibration.
- Physical scale has no control measurements yet; metric claims wait on LiDAR registration or on-site markers.
