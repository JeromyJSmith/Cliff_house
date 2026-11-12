# LichtFeld Studio + 360 Plugin reference (researched 2026-11-12)

This is a feature and capability reference for LichtFeld Studio (LFS) and
`alexmgee/lichtfeld-360-plugin`, written for our capture. The capture is an
Antigravity A1 drone with an Insta360 X5 dual-fisheye camera, producing `.insv`
files with two H.264 3840x3840 streams. We also have SiteScape phone-LiDAR PLYs.
Everything runs in a Marimo notebook on molab, where CUDA works but the NVIDIA
Vulkan driver does not (only llvmpipe).

**How the sources were checked.**

- **LFS releases.** Every release body came from
  `gh api repos/MrNeRF/LichtFeld-Studio/releases --paginate`: 17 releases,
  covering v0.4.0 (2026-01-16) through `model-llmdet-tiny-v1` (2026-11-12).
- **LFS source.** Read at two points:
  - `master` at commit `9b6dce25b` (2026-11-12). This is called **master** below.
  - Tag `v0.5.4.2` at commit `fac5e497a` (2026-10-22, released 2026-11-01).
    This is called **0.5.4.2** below.
- **LFS commits.** Unreleased work was listed with
  `gh api repos/MrNeRF/LichtFeld-Studio/commits?since=2026-08-01`: 1,689
  commits, 205 of them after the 0.5.4.2 tag. Git trees of the `dev` and
  `pre_training_tools` branches were also listed.
- **LFS wiki.** Cloned (last edit 2026-08-15). It is stale, so it is only a
  cross-check.
- **360 plugin.** Read at `master` commit `3165e6e` (2026-08-19, = v0.5.0),
  together with its `CHANGELOG.md` and both GitHub releases (v0.4.0, v0.5.0).
  There are no commits after 2026-08-19.
- **radiancefields.com.** The 0.5.4 and 0.5.4.1 articles were read as
  cross-checks only.

**How paths are written.** File paths are relative to each repository root.
Open them with:

- LFS master: `https://github.com/MrNeRF/LichtFeld-Studio/blob/9b6dce25b/<path>`
- LFS 0.5.4.2: `https://github.com/MrNeRF/LichtFeld-Studio/blob/v0.5.4.2/<path>`
- 360 plugin: `https://github.com/alexmgee/lichtfeld-360-plugin/blob/3165e6e/<path>`
- Releases: `https://github.com/MrNeRF/LichtFeld-Studio/releases/tag/<tag>`

**Status tags.** **[master-only]** means the feature is on master after the
0.5.4.2 tag and is not in any release. Anything not confirmed is marked
**unconfirmed**.

---

## 1. What it is, versions, license

- **LichtFeld Studio.** A C++23/CUDA Gaussian-splatting trainer, editor and
  viewer, licensed GPL-3.0-or-later (`LICENSE`; SPDX headers, e.g.
  `src/core/argument_parser.cpp`).
  - The GUI uses a Vulkan viewer. OpenGL was removed in v0.5.3 ("Bye bye
    opengl - hello vulkan", "Remove cuda renderer" in the v0.5.3 release body).
    The window layer is SDL3 (GLFW was replaced in v0.5.0, "migrate from glfw
    to sdl3").
  - Training is CUDA, with no LibTorch in the application
    (`docs/building_and_distribution.md` § Tests).
- **Binary name.** `LichtFeld-Studio`. The help examples spell it
  `lichtfeld-studio` (`src/core/argument_parser.cpp` L736-757). A portable
  build launches through `dist/bin/run_lichtfeld.sh`
  (`docs/building_and_distribution.md`).
- **Latest release.** `v0.5.4.2` (2026-11-01, a security release). Master
  already calls itself 0.5.5: commit `36c74174f` is "Set the version back to
  0.5.5 after the 0.5.4.2 release".
- **No Linux binaries.** GitHub releases since v0.5.0 have no app assets. Only
  v0.4.x had Windows zips (release asset listing).
  - Windows binaries come through the LichtFeld portal, which needs
    registration and a donation (radiancefields 0.5.4.1 article).
  - **Linux means a source build.**
- **Model releases.** The `model-*` tags are permanent `.lfw` weight assets
  (native LFS weight format). Their bodies, and what uses them, are listed in
  §2.7.
- **The 360 plugin.**
  - Version: `lichtfeld-360-plugin` v0.5.0, GPL-3.0-or-later (`pyproject.toml`).
  - Python: `requires-python = ">=3.12,<3.13"`.
  - LFS hosts: it declares `lichtfeld_version = ">=0.5.0"`. v0.5.0 was tested
    against LFS `v0.5.3-266-gbf4ff97b0` (`CHANGELOG.md`).
  - Its README says "*This is a work in progress.*"

---

## 2. Features by release (LFS)

Unless noted, each item is quoted or paraphrased from that release's body.

### 2.1 v0.4.0 (2026-01-16) to v0.4.2 (2026-02-03): still relevant items
- The default strategy was renamed to `adc` ("Rename default strategy to adc").
  **`adc` no longer exists.** Master accepts only
  `{"mcmc","mrnf","mnrf","lfs","igs+"}` (`src/core/argument_parser.cpp` L203).
- "Portable builds", "mip 2d filter", "respect --max_width".
- "fix: transforms.json loader and equirectangular camera support".
- "feat: add pipelined image loader with GPU batch decoding".
- "export config" / "import trainer config".
- v0.4.1: "Ppisp" (per-camera physically plausible ISP).
- v0.4.2: "alpha as mask".

### 2.2 v0.5.0 (2026-03-18)
- "Mesh support", "Mesh to splat", "Mesh picking".
- "Plugin Marketplace".
- "Feature/improved gs plus" (IGS+).
- "Feat: Added mask modes to the evaluations".
- "PPISP: Fix CRF…".
- "Make equirectangular rendering without seams".
- "migrate from glfw to sdl3".
- "Enhance mcp".
- "#656 Enable/Disable cam views for training and extend python api".

### 2.3 v0.5.1 (2026-03-31) and v0.5.2 (2026-04-21)
- "Usd format import export".
- "Depth mode selection".
- "LFS densifcation" (later named MRNF).
- "Fix mcmc defaults".
- "Add --output-name parameter".
- "MCP: Add full UI window capture".
- v0.5.2: "Improve CLI progress", "Add action-only plugin toolbar support".

### 2.4 v0.5.3 (2026-06-24)
- **Rendering moved to Vulkan:** "Bye bye opengl - hello vulkan", "Fastgs
  vksplat", "Remove cuda renderer", "fix(visualizer): match Vulkan physical
  device to CUDA device on multi-GPU systems".
- **RAD LOD:** "RAD File Format Export", "RAD LOD Viewer".
- **360 cameras in COLMAP:**
  - "Add SPHERICAL (equirectangular) camera model to the COLMAP loader".
  - "COLMAP loader: use EQUIRECTANGULAR as the canonical 360 model name".
- **Masks:** "New mask mode combining Ignore and Segment"; "Support in-memory
  masks and float-dtype colors for direct-scene plugins".
- **Other:**
  - "Add CLI arguments for background mode initialization".
  - "Adding a TCP server to broadcast and share events".
  - "added las laz diaglogs".
  - "Import Asset From URL".

### 2.5 v0.5.4 (2026-10-09): the large release
This release has about 1,000 change lines and no "Highlights" section; the
overview video is https://www.youtube.com/watch?v=DIcGFMeBSXU. The capability
lines below were selected by keyword from the "What's Changed" list.

- **Training core**
  - "GUT training: all SH degrees, 25% faster".
  - "3DGUT: honor prepared undistortion instead of applying distortion twice".
  - "Match thin-prism fisheye undistortion to the COLMAP camera model".
  - "Support six-term rational camera distortion".
  - "Fix evaluation and training image quality with --undistort".
  - "Support camera-aware depth and normal supervision in GUT". An earlier
    line in the same release said "Make depth and normal loss unavailable with
    GUT"; the later line supersedes it.
- **Exposure and appearance**
  - "Exposure correction, a working bilateral grid, and cleaner skies".
  - "Seed PPISP exposure from EXIF and apply PPISP in evaluation".
  - "Scope exposure correction defaults to MRNF".
  - "Lower exposure correction VRAM…".
- **Normals and depth**
  - "Normal loss: schedule parameters and automatic normal maps".
  - "Normal loss: apply user masks to the normal terms…".
  - "Native inference engine: drop ONNX Runtime, 34 ms normals in 1 GB VRAM".
  - "Priors: accept depth and normal maps of any resolution".
  - "Fit depth anchors on the SfM points each camera observed".
- **MRNF**
  - "Add the far-field reconstruction option to mrnf".
  - "Use exact neighbors for MRNF initialization".
  - "Remove the MRNF background improvements option".
  - "Turn off the MRNF opacity regularizer".
- **Robustness**
  - "Training survives OOM, GUT gets edge scores, .licht keeps checkpoint
    history".
  - "Make resumed training runs save their results".
- **Headless**
  - "Add headless camera-path render mode (--render-camera-path)".
  - "Stabilize headless execution and plugin validation".
  - "Let headless training start from an untrained .licht with embedded
    dataset via --data-path".
  - "Headless runs redirected with -o keep the source project's embedded
    dataset".
  - "Reject --mcp-port in headless mode".
  - "Fix camera coordinates in headless video export".
- **.licht project format**
  - "Add an optional license to the .licht format".
  - "Add a seperate .licht inspect and restore CLI Tool".
  - "Add licht --embed to embed a dataset into a project".
  - "Allow cleaning and compacting projects without opening them".
- **Export**
  - "SSOG export and import"; "Publish large scenes to the gallery as
    streamable SSOG".
  - "SPZ export is 2.6x faster".
  - "SOG export is 2.9x faster…".
  - "Replace OpenUSD with vendored flat USD I/O".
  - "Export provenance stamps: every export records what produced it".
  - "Add measurement tool… to HTML viewer export"; "Add label tool to HTML
    viewer export".
  - "Leave frozen added splats out of the final export with --exclude-export".
- **Evaluation**
  - "Add native LPIPS evaluation metric".
  - "Add an eval command that scores a finished model".
  - "Write per-image evaluation results and add --eval-all".
  - "Evaluation: reference bit depth, FLIP and one image per view with masks".
  - "Select evaluated pixels with boxes, the crop box, mask folders, depth and
    points".
- **Gallery**
  - "Connect LichtFeld Studio to the portal and sync gallery files".
  - "Projects panel, Inspector Contents and Gallery publishing".
  - "Suggest SSOG as the default gallery upload format".
- **MCP**
  - "Add persistent MCP server management…".
  - "Start LichtFeld Studio on demand from the MCP bridge".
  - "Validate MCP HTTP requests and require a token for network access".
  - "Per-launch MCP port override".
- **Config:** "Export and import all dataset and training settings in config
  files".
- **Cross-check (radiancefields 0.5.4 article).** Confirms the following:
  - the .licht format, normal-guided training and Gallery publishing;
  - "camera support extended to fisheye and more complex distortion";
  - "Training requires an NVIDIA GPU with compute capability 7.5 or newer";
  - a project claim of "up to 3x faster training than 0.5.3".

### 2.6 v0.5.4.1 (2026-10-18)
Items from the release Highlights:
- **Drag export and Blender**
  - "Drag splats out of LichtFeld Studio… into a folder or straight into
    Blender as PLY or SPZ".
  - "drops into Blender use its +Z up automatically on Windows and Linux X11".
  - radiancefields adds that this uses the native splat importer in the Blender
    5.3 beta, with no add-on.
- **Crop box:** numeric crop box and ellipsoid fields; "Training can follow the
  crop box live without floaters, and you choose how much growth goes inside
  it".
- **Resume:** "Stored training sessions can be resumed, including ones saved
  during sparsification".
- **Video frame extraction:** batch extraction, exact FPS, naming presets, frame
  numbering base, full-range colours, software decode fallback.
- **Evaluation:** "A compare command scores image sets"; "masks select the same
  pixels in training, evaluation and SSIM".

From the change list:
- **Training:** "Initialize training from a mesh"; "Undistort every lens model
  with one GPU inverse"; "Keep the whole calibrated rim of a GUT fisheye";
  "Fix RAD LOD decoding and rendering in 3DGUT".
- **Linux:**
  - "Restore SOG, SSOG and USDZ export on Linux".
  - "Honor TMPDIR for the image loader's spill folder on Linux". This matters
    on molab: point TMPDIR at scratch.
- **Masks:** "Warn when ignore masks exclude every pixel"; "Validate mask
  dimensions before training"; "Resize in-memory camera masks with their
  training images".
- **Plugins:** "Verify plugin archive digests and warn on unverified URL
  installs".

### 2.7 v0.5.4.2 (2026-11-01, security)
- Rejects the 8 compromised eMudhra CAs; bundled uv moves to 0.13.5; dependency
  security bumps (OpenSSL 3.6.5, curl 8.23.0, FFmpeg 8.1.2, …).
- "**POPSpa sparsification.** Optional post-training sparsification removes
  splats the result does not need."
- "**Training region of interest from the command line.**
  `--cropbox x0,y0,z0,x1,y1,z1` …; `--cropbox-loss-weight 0` ignores every
  pixel whose ray misses it."
- "**MRNF at the splat cap.** Error-guided growth keeps exchanging splats once
  the cap is reached."
- "Add prompt to enable undistortion or GUT when distorted cameras are
  detected".
- "Write an untrained project that trains from the file alone".
- "Enforce hot_reload manifest flag policy and default to false for GPU
  plugins".

### 2.8 Unreleased on master (after the 0.5.4.2 tag)
Each item is **[master-only]**; the source is the commit list (short SHA, PR
number).

| Feature | Commit (PR) | Relevance to us |
|---|---|---|
| Native SAM2 video masking in video extraction + `mask-video` CLI | `103636f9e` (#3875) | Masks people and the operator in fisheye frames; see §3.3 |
| Assisted SAM2.1 image masks (points, box), track and review masks over extracted frames | `9b62271d0` (#4001), `7f85993a7` (#4017) | Manual mask cleanup in the GUI |
| **Automatic photogrammetric scene rescaling using AprilTags** | `8d047d9d4` (#3821) | Metric scale from markers (tag36h11) |
| **Scale distance tool** | `186ac29fa` (#3570) | Metric scale from a measured distance |
| **Pose refinement** (`--pose-opt`) | `99e61d363` (#4048), `9da5f0fbe` (#4063) | Refines camera poses; pinhole or `--undistort` only, not with `--gut` |
| Batch training CLI supervisor (`batch-train`) | `6a7c00d1f` (#3641), `bf8f64f66` (#3858) | Runs several datasets in one notebook cell |
| Sharpen training images in the dataloader (`--sharpen-*`) | `24226da92` (#3745) | Optional sharpening |
| SteadySplats colour-variance loss (`--color-variance-*`) | `25922e180` (#3726) | Less noise in stochastic renderers |
| Crop to ROI when training ends (`--crop`); `--cropbox-rotation`; polygon crop as ROI | `91e20f2a3`, `d248441f6`, `698e7d3f5`, `0081c817d` | Train the lodge only |
| Checkpoint listing and pruning in `licht`; checkpoint history opt-in | `798c96334` (#3906), `3152c3f47` (#3894) | Smaller .licht files on HF |
| Save standalone projects at several `--save-project-at-iter` iterations | `211757faa` (#3994) | Intermediate snapshots |
| Grow training VRAM on demand | `f5e58a26c` (#3956) | — |
| Collision voxelization (`voxelize`) and Walk APIs | `e1531fb8b`, `7d3c6783e`, `83247a585` | Walkable twin |
| Noise infill mesh (`--noise-infill-mesh`) | `d429b7488` (fixtures); `docs/docs/features/noise-infill.md` | Fills glass and transparent surfaces |
| Native OpenXR VR viewing | `01367cfc9` (#3569) | GUI only |
| User shaders, sequencer reveal effects, gamepad | `2df54a70a`…`5f301e66b`, `2cb838a09`, `90c63ac3c` | GUI only |
| Shared training-session publisher, external-training previews (Blender extension) | `7bf40b2e4` (#3993), `895932304` (#4008), `877f11cca` (#4034) | `docs/docs/features/external-training.md` |
| Loss heatmaps in GT Compare; RGB/depth/normal viewport modes | `ca2495395`, `393aa4274` | GUI QA |

**The `dev` branch** (tree listed, not built) adds the following:
- tensor backends for HIP, Metal and Vulkan (`src/core/tensor/backend/{hip,metal,vulkan}`);
- training Vulkan shaders (`src/training/vulkan/shaders`);
- a RoMa v1 dense matcher (`src/core/nn/models/romav1.cpp`,
  `src/python/lfs_plugins/dense_matching.py`);
- AprilTag detection.

Two branches are also present: `feat/fastgs-fisheye` and
`feature/camera-pose-refinement`. Treat all of this as future work. A Vulkan
*training* backend would **not** help on molab, because Vulkan has no GPU
there.

### 2.9 `model-*` weight releases and what uses them

| Tag (date) | Asset | Used by (per release body) | Consumer in master source? |
|---|---|---|---|
| `model-moge2-v1` (2026-07-05) | `moge-2-vitb-normal.lfw` / `.onnx` | "`preprocess` CLI for depth and normal map generation" | Yes, `preprocess` (§3.3) and auto normal maps |
| `model-sam2-v1` (2026-08-28) | `sam2.1-hiera-base-plus.lfw` | SAM 2.1 image predictor | Yes, assisted image masks [master-only] |
| `model-lpips-v1` (2026-09-03) | `lpips-vgg16-v0.1.lfw` | "the evaluator for the LPIPS metric" | Yes, `--eval`, `eval`, `compare` |
| `model-romav1-v1` (2026-09-16) | `romav1.lfw` | "the densification pipeline to match image pairs" | **No.** Only on `dev` (`src/core/nn/models/romav1.cpp`) |
| `model-moge3-v1` (2026-09-23) | `moge-3-vitl-base-v1.lfw` | "the default depth model of the SLAM pipeline and the `preprocess` CLI" | **No consumer found** in master or dev (no `slam`/`moge3` paths). Master `preprocess` still says "MoGe dynamic-token input" and defaults to the MoGe-2 asset (`docs/building_and_distribution.md` § Preprocess Model Downloads) |
| `model-sam2-video-v1` (2026-10-28) | `sam2.1-hiera-base-plus-video.lfw` (sha256 `b4a98106…`) | "native video masking" | Yes, `mask-video` [master-only] (`docs/docs/features/video-masking.md`) |
| `model-llmdet-tiny-v1` (2026-11-12) | `llmdet-tiny-v1.lfw` | "text and category mask selection" | **No consumer found** in master or dev. The video-masking doc says "Text-based object selection is not available in this preview" |

Weights are cached in `~/.lichtfeld/onnx/` ("The historical folder name does
not indicate a runtime dependency", `docs/docs/features/video-masking.md`).
**On molab this cache is wiped at shutdown. Mirror the `.lfw` files to HF and
pass `--model`.**

### 2.10 Cross-cutting capabilities (current master)
- **Strategies.** The values are `mcmc`, `mrnf` (aliases `mnrf`, `lfs`) and
  `igs+` (`src/core/argument_parser.cpp` L46, L203).
  - The default is **mrnf**. `OptimizationParameters.strategy =
    kStrategyMRNF`, with `iterations = 30'000` and `sh_degree = 3`
    (`src/core/include/core/parameters.hpp` L248-312).
  - MRNF defaults: `use_exposure_correction = true`, `max_cap = 5'000'000`,
    `stop_refine = 28'500`, error map and edge map on
    (`src/core/parameters.cpp` `mrnf_defaults()`).
  - IGS+ defaults: `max_cap = 4'000'000`, `stop_refine = 15'000`.
  - The struct default for `max_cap` is 1,000,000, which MCMC inherits.
- **Camera models in the COLMAP loader** (`src/io/formats/colmap.cpp`
  L734-749):
  - SIMPLE_PINHOLE, PINHOLE, SIMPLE_RADIAL, RADIAL, OPENCV, OPENCV_FISHEYE,
    FULL_OPENCV, FOV, SIMPLE_RADIAL_FISHEYE, RADIAL_FISHEYE,
    THIN_PRISM_FISHEYE.
  - EQUIRECTANGULAR (model id 17); `SPHERICAL` is accepted as an alias.
  - `transforms.json` also loads (`src/io/formats/transforms.cpp`).
- **Distorted and fisheye cameras.** Non-pinhole or distorted cameras require
  `--gut` or `--undistort`. Otherwise training fails with "Use --gut or
  --undistort to train on cameras with non-pinhole model"
  (`src/training/trainer.cpp` L6319-6353).
  - `--undistort` resamples each image, mask, depth and normal map into a
    pinhole camera once (`src/core/optimization_properties.cpp` L1086-1090).
  - The 3DGUT docs list the GUT-supported models: pinhole family, OPENCV,
    FULL_OPENCV, OPENCV_FISHEYE, RADIAL_FISHEYE, SIMPLE_RADIAL_FISHEYE
    (`docs/docs/features/gut.md`).
- **Mutual exclusions** (`src/core/parameters.cpp` L1083-1095):
  - "GUT and igs+ strategy cannot be used together".
  - "pose_opt … cannot be combined with GUT".
  - "use_exposure_correction cannot be combined with use_bilateral_grid,
    use_ppisp, ppisp_use_controller, or ppisp_freeze_from_sidecar". Because
    MRNF turns exposure correction on by default, `--ppisp` or
    `--bilateral-grid` under MRNF also needs `--no-exposure-correction`.
- **Masks.**
  - `--mask-mode none|segment|ignore|segment_and_ignore|alpha_consistent`
    (`src/core/argument_parser.cpp` L901). The GUI string for ignore is
    "Ignore masked pixels in the loss"
    (`src/visualizer/gui/resources/locales/en.json` L814).
  - The mask-video output convention is "0 to exclude a pixel and 255 to keep
    it. Training's existing mask loader recognizes these sidecars"
    (`docs/docs/features/video-masking.md`).
  - Sidecar layout is `masks/<image filename>.png`.
- **Normal and depth guidance.** `--use-normal-loss` auto-generates normal maps
  unless `--no-normal-auto-generate` is given. Depth works the same way. The
  rest of the flags are in §3.1.
- **Export formats.**
  - Training `--export`: "ply, sog, ssog, spz, usd, usda, usdc, html, rad"
    (`src/core/argument_parser.cpp` L785).
  - `convert` adds `glb`. This is SPZ inside glTF:
    `save_spz(... .glb = true)`, `src/app/converter.cpp` L147.
  - MCP adds `scene.export_usdz_nurec` and `scene.export_colmap`
    (`src/app/mcp_gui_tools.cpp`).
  - Loaders: PLY, SOG, SSOG, SPZ, RAD, USD*, NuRec USDZ
    (`src/io/loaders/`, `src/io/formats/nurec_usdz.hpp`).
  - **There is no splat-to-mesh extraction.** No TSDF, marching-cubes or
    Poisson code was found in `src/`. Meshes are import-only: init, noise
    infill, mesh2splat, display.
- **.licht.** "One file is your whole session". It holds the model and
  checkpoint, scene graph, layout and sequencer, written as append-only
  generations with zstd-framed payloads (`docs/licht_format.md`).
- **MCP server.** The namespaces are `scene_*`, `training_*`, `runtime_*`,
  `ui_*`, `operator_*`, `selection_*`, `transform_*`, `gaussians_*`,
  `history_*`, `editor_*`, `shader_*`, `camera_*`, `render_*`, `sequencer_*`
  (`docs/docs/development/mcp/index.md`).
  - Tools include `scene.load_dataset`, `scene.export_{ply,sog,ssog,spz,usd,rad,html,colmap,usdz_nurec}`,
    `training.start`, `training.get_state`, `training.get_loss_history`,
    `apriltag.scan`, and others (`src/app/mcp_*.cpp`).
  - **It is GUI-only:** `--mcp-port` is "not available in headless mode"
    (`src/core/argument_parser.cpp` L1003).
- **Python plugin API.** The `lichtfeld` module runs *inside* LFS: "SDK stubs
  are for IDE completion, not a standalone Python runtime"
  (`docs/plugins/README.md`).
  - Headless runs load plugins when `--python-script` is given
    (`src/app/application.cpp` L1120-1176).
  - AprilTag APIs [master-only]: `detect_scene_apriltags(family='tag36h11', …)`
    and `scale_scene_by_apriltags(constraints, …)`
    (`src/python/stubs/lichtfeld/__init__.pyi` L3080-3085).
- **Timelapse.** Use `--timelapse-images <name>` (repeatable) and
  `--timelapse-every N` (default 50) (`src/core/argument_parser.cpp`
  L973-974). The docs page says `--timelapse-interval`
  (`docs/docs/features/timelapse.md`), but **that flag does not exist in the
  parser.** Use `--timelapse-every`.
- **Blender.** Drag export (§2.6). A "LichtFeld Blender extension" publishes
  training sessions (`docs/docs/features/external-training.md`).
- **Gallery.** Publishes to lichtfeld.io, with SSOG as the suggested format
  (§2.5). This needs a portal login and is GUI only.

---

## 3. CLI reference (quoted from `src/core/argument_parser.cpp`, master `9b6dce25b`)

The flag names below were extracted mechanically from every `::args::` object
in the parser (267 objects, 198 distinct names). Compared with 0.5.4.2 (158
names), master **adds** these flags: `crop, cropbox-rotation,
color-variance-weight, color-variance-warmup-iters, noise-infill-mesh, pose-opt,
keep-all-checkpoints, no-keep-all-checkpoints, eval-green-infill,
sharpen-{amount,kernel,radius,threshold}`. Master also adds the subcommands
`mask-video`, `batch-train` and `voxelize`, and their flags. Nothing was
removed. Everything else listed below exists in 0.5.4.2 as well.

Help text is quoted where it is inline. Where the help text comes from
`optimization_cli_help`, the description is taken from the property
registry.

### 3.1 Main mode (training, view, resume, render)

**Mode selection**
- `-h, --help`; `-V, --version`.
- `-v, --view <path>`: "View file(s). Supports projects (.licht), splat (.ply,
  .sog, .ssog, .spz, .rad, .usd, .usda, .usdc, .usdz) and mesh (.obj, .fbx,
  .gltf, .glb, .stl)". This is a GUI mode.
- `--resume <checkpoint>`: "Resume training from a .resume checkpoint or
  .licht project".
- `--render-camera-path <path>`: "Render a JSON camera-keyframe path to video,
  headless (no GUI/window). Requires --render-load and --render-output". It
  takes `--render-load <.ply/.sog/.ssog/.spz/.resume>`,
  `--render-output <.mp4>`, `--render-width` (1920), `--render-height` (1080),
  `--render-fps` (30) and `--render-crf` (18).

**Training paths**
- `-d, --data-path`: "a dataset folder or an untrained .licht project".
- `-o, --output-path`: "Directory for the project file and --export files".
- `--output-name`: "default project.licht and splat_ITER".
- `--config <json>`.
- `--init <path>`: "Initialize from a splat, point cloud or mesh file; a mesh
  must be in the dataset's coordinates".
- `--add-splat <path>` (repeatable), `--freeze`, `--freeze-lr-scale`,
  `--exclude-export`.
- `--no-provenance`.
- `--export <formats>`: "comma-separated ply, sog, ssog, spz, usd, usda, usdc,
  html, rad".
- `--import-cameras <sparse>`: "Import COLMAP cameras from sparse folder (no
  images required)".

**Training parameters**
- `-i, --iter`: "cannot be combined with --steps-scaler".
- `--strategy`: mcmc | mrnf | igs+ (legacy `mnrf`, `lfs`).
- `--sh-degree`, `--sh-degree-interval`, `--morton-reorder-interval`,
  `--max-cap`, `--min-opacity`.
- Crop box:
  - `--cropbox x0,y0,z0,x1,y1,z1`: "set up when a headless run starts a fresh
    model".
  - `--cropbox-rotation rx,ry,rz` [master-only], `--crop` [master-only].
  - `--cropbox-lr-scale`, `--cropbox-loss-weight`, `--cropbox-growth-inside`.
- MRNF and growth tuning: `--thin-structure-weight`, `--late-lr-anneal`,
  `--gradient-loss-weight`, `--densify-structure-weight`,
  `--opacity-decay-rendered-only` / `--no-opacity-decay-rendered-only`,
  `--max-screen-share`, `--screen-share-penalty`.
- Colour variance [master-only]: `--color-variance-weight`,
  `--color-variance-warmup-iters`.
- `--steps-scaler`.
- `--pose-opt` [master-only].
- Error and edge maps: `--no-error-map`, `--densify-error-map ssim|ssim_cs`,
  `--no-edge-map`.
- Background: `--bg-mode solidcolor|modulation|image|random`, `--bg-color`,
  `--bg-image-path`.

**Initialization**
- `--random`, `--init-num-pts`, `--init-extent`.
- `--init-mesh-resolution`: 16 to 2048, default 1024
  (`docs/docs/features/mesh-init.md`).
- `--noise-infill-mesh` [master-only].

**Dataset**
- `--images <folder name>`, `--test-every N`.
- `-r, --resize_factor auto|1|2|4|8`.
- `--max-width`: "0 disables the cap (default: 3840)".
- `--min-track-length`.
- `--no-cpu-cache`.
- `--use-16bit`: "caches losslessly as JPEG 2000".
- `--sharpen-amount|kernel|radius|threshold` [master-only].
- `--undistort`.
- `--centralize off|by_pointcloud|by_cameras`.

**Mask, depth and normal**
- `--mask-mode`, `--invert-masks`, `--no-alpha-as-mask`.
- Depth: `--use-depth-loss`, `--depth-loss-weight`, `--depth-loss-mode`
  (values "ssi (auto-detect), ssi-disparity, or ssi-depth"),
  `--no-depth-auto-generate`.
- Normals: `--use-normal-loss`, `--no-normal-auto-generate`,
  `--normal-loss-weight`, `--normal-consistency-weight`,
  `--normal-flatten-weight`, `--normal-start-fraction`,
  `--normal-end-fraction`.
- `--normal-loss-space`: values `auto, camera-opencv, camera-opengl, world`
  (`src/core/parameters.cpp` L1098-1102).

**Sparsity:** `--enable-sparsity` ("Run POPSpa sparsification after
training"), `--popspa-target-count`.

**Rendering**
- `--enable-mip`.
- `--bilateral-grid`, `--exposure-correction` / `--no-exposure-correction`.
- PPISP: `--ppisp`, `--no-ppisp-exif-exposure`, `--ppisp-controller`,
  `--ppisp-freeze`, `--ppisp-sidecar <.ppisp>`, `--ppisp-holdout-appearance`.
- `--gut`.

**Output**
- Evaluation: `--eval`, `--eval-all`, `--eval-flip`, `--eval-green-infill`
  [master-only], `--eval-space distorted|undistorted`,
  `--eval-bit-depth auto|8|16|float`, `--eval-mask <source>`,
  `--eval-mask-opacity`, `--eval-mask-report`, `--eval-steps 7000,30000`,
  `--no-save-eval-images`.
- `--no-download`: "Do not download optional model weights".
- Checkpoints: `--keep-all-checkpoints` / `--no-keep-all-checkpoints`
  [master-only].
- Timelapse: `--timelapse-images`, `--timelapse-every`.
- `--save-project-at-iter <list>`, `--save-project-path`.

**UI**
- `--headless`: "Run without visualization".
- `--train`: "Start training immediately on startup".
- Recovery and reset: `--safe-mode`, `--reset-preferences`, `--reset-layout`,
  `--reset-all-settings`, `--no-splash`.
- Debugging: `--debug-python`, `--debug-python-port`.
- `--mcp-port`: GUI only.

**Profiling and logging**
- Profiling: `--perf-bench`, `--perf-bench-warmup`, `--profile-window`.
- Logging: `--log-level trace|debug|info|perf|warn|error|critical|off`,
  `--verbose`, `-q, --quiet`, `--log-file`, `--log-filter`.
- Environment variable: `LFS_LOG_LEVEL`.

**TCP and extensions**
- TCP: `--tcp-connection` (requires `--headless`), `--tcp-server-port`,
  `--tcp-broadcast-port`.
- `--python-script <path>` (repeatable): "custom training callbacks".

Help examples, quoted verbatim (L736-757):

```text
lichtfeld-studio --headless -d ./data -o ./output --export ply
lichtfeld-studio --headless --resume session.licht
lichtfeld-studio -d ./data -o ./output --save-project-at-iter 7000
lichtfeld-studio --render-camera-path path.json --render-load model.ply --render-output out.mp4
lichtfeld-studio batch-train ./datasets/ -o ./outputs/ --strategy mrnf --iter 30000
```

Constraints enforced in the parser:
- "Headless mode requires --data-path or --resume" (L1404).
- "--iter and --steps-scaler are mutually exclusive" (L1096).
- "--strategy conflicts with config file" (L2207).
- `--data-path project.licht` requires `--headless`
  (`src/app/application.cpp` L1832-1834).

### 3.2 Subcommands
The list is from the main help (L723-733). Run `<subcommand> --help`.

| Subcommand | In 0.5.4.2? | Flags (quoted names) |
|---|---|---|
| `convert <in> [out]` | yes | `-o`, `--sh-degree` (-1 keep), `-f/--format ply,sog,ssog,spz,glb,html,usd,usda,usdc,rad`, `--spz-version 3/4`, `--no-provenance`, `--tiles AxB`, `--lod-builder bhatt/octree`, `--stream`, `--none-stream`, `-y/--overwrite` |
| `eval <model or .licht>` | yes | (own parser; "Score a finished model or splat file against its images") |
| `compare <reference> <test>` | yes | `-o`, `--colmap`, `--eval-mask`, `--eval-mask-opacity`, `--eval-mask-report`, `--undistort`, `--eval-space`, `--eval-bit-depth`, `--eval-flip`, `--save-images`, `--no-download` |
| `mesh2splat <mesh> [out]` | yes | `-o`, `-f`, `--spz-version`, `--no-provenance`, `--resolution` (1024), `--sigma` (0.65), `-y` |
| `preprocess <dataset>` | yes | `--mode depth,normals,both` (both), `--images`, `--model <onnx>`, `--inference-backend native`, `--max-side` (518), `--num-tokens` (1800), `--threads`, `--png-compression` (6), `--bit-depth 8/16` (16), `-y`, `--no-download`, `--download-only` |
| `plugin` | yes | create / check / list |
| `licht <project.licht>` | `--embed` yes; checkpoint actions **master-only** | `--embed [dataset]`, `--checkpoints`, `--prune-checkpoints [--keep N]`, `--remove-checkpoints <iters>` (L3025-3042; `docs/docs/cli.md`) |
| `mask-video <video or dataset>` | **master-only** | `-o`, `--model <.lfw>`, `--fps` (1), `--start`, `--end`, `--seed x,y[,label]`, `--seed-frame`, `--seed-box`, `--circle cx,cy,rx,ry`, `--fisheye`, `--recenter`, `--fisheye-fov` (200), `--view-fov` (160), `--dilation` (12), `--require-operator`, `-y`, `--no-download`, `--download-only` |
| `batch-train <inputs…>` | **master-only** | `-o/--output/--output-dir/--output-path`, `--manifest`, `--recursive`, `--stop-on-failure/--fail-fast`, `--dry-run`, `--timeout <min>`, `--summary`, `--report` |
| `voxelize <splat> [out]` | **master-only** | `-o`, `--voxel-size` (0.05), `--voxel-opacity`, `--max-gaussian-area`, `--filter cleanup/none`, `--auto`, `-y` |

### 3.3 Points that matter for us
- **Masks for fisheye frames.** `mask-video` takes `--circle` and `--fisheye`.
  Its doc says it "is an equidistant approximation for a single circular lens
  image; split multi-lens recordings into individual lens frames first".
  `--seed` tracks one subject from a seed point, and automatic mode looks for a
  camera operator. Neither is a general "mask every person" detector
  (`docs/docs/features/video-masking.md`).
- **`preprocess` makes depth and normal priors** with MoGe and the native
  runtime. It is not documented which camera models it handles; fisheye input
  is **unconfirmed**.

---

## 4. Linux / headless build and the molab GPU verdict

### 4.1 Prerequisites (`docs/building_and_distribution.md`)
- **Toolchain:** "CUDA Toolkit 12.8+", "CMake 3.30+", "vcpkg (`VCPKG_ROOT`
  environment variable set)", "GCC 14+".
  - Sources: `find_package(CUDAToolkit 12.8 REQUIRED)` (`CMakeLists.txt` L477);
    `cmake_minimum_required(VERSION 3.30)`.
  - sm_120 (Blackwell) needs CUDA ≥ 12.8, so the floor is already high enough.
    Our driver 595.71 can run CUDA 13.x.
- **Driver gate:** if `nvidia-smi` reports a driver below 570, configure fails
  (`CMakeLists.txt` L423).
- **apt packages used by CI:**

  ```text
  git curl unzip cmake gcc-14 g++-14 ccache ninja-build zip tar pkg-config
  python3 python3-dev libxinerama-dev libxcursor-dev xorg-dev
  libglu1-mesa-dev libwayland-dev libxkbcommon-dev libegl-dev libdecor-0-dev
  libibus-1.0-dev libdbus-1-dev libsystemd-dev libgtk-3-dev nasm autoconf
  autoconf-archive automake libtool
  ```

- **GTK3 is required even for headless builds.** `SetupNativeFileDialog.cmake`
  stops with a FATAL_ERROR when `pkg-config` cannot find `gtk+-3.0`.
- **Vulkan and SDL3 are required at configure time:** `find_package(Vulkan
  REQUIRED)`, `find_package(VulkanMemoryAllocator CONFIG REQUIRED)`,
  `find_package(SDL3 REQUIRED)` (`CMakeLists.txt` L514-517).
- **vcpkg dependencies** (`vcpkg.json`) are all built from source in the build
  tree:

  ```text
  apriltag, cppzmq, curl, args, assimp[draco],
  ffmpeg[avcodec,avfilter,avformat,nvcodec,swscale,x264], freetype, fmt, glm,
  libarchive, libdeflate, libjpeg-turbo, libpng, libplacebo, libwebp,
  nanobind, nativefiledialog-extended, nlohmann-json, python3[extensions],
  rmlui[svg], sdl3[vulkan], spdlog, tbb, tiff, openexr, openxr-loader, vulkan,
  vulkan-loader[wayland,xcb,xlib], vulkan-memory-allocator, volk,
  glslang[tools], shader-slang, xxhash, zstd
  ```

  **Expect a long first build.** The time is **unconfirmed**; the docs only say
  vcpkg runs during configure, with concurrency capped at 6.
- **Headless build switch:** "If you intentionally want a headless or
  experimental build, pass `-DLFS_ENFORCE_LINUX_GUI_BACKENDS=OFF`". This only
  skips the X11/Wayland preflight (`cmake/LinuxGuiSanity.cmake` L77, L158).
  SDL3 and Vulkan are still linked.

### 4.2 Presets and options
- **Presets** (`CMakePresets.json`):
  - `build` (Release in `build/`), `debug`;
  - `linux-release` and `linux-relwithdebinfo`, which are Release-only vcpkg
    triplets (`docs/docs/development/build.md`).
  - All presets "build the complete application feature set" and "compile for
    one native CUDA architecture".
- **CMake options** (`docs/building_and_distribution.md` § CMake Options;
  `CMakeLists.txt` L188-240, L372):
  - `BUILD_PORTABLE` (OFF): "Create self-contained distribution". It forces
    `BUILD_CUDA_PTX_ONLY=ON`.
  - `BUILD_CUDA_PTX_ONLY` (OFF): "JIT at runtime, ~5-15s first startup".
  - `BUILD_CUDA_MIN_SM` (75).
  - `BUILD_TESTS` (OFF).
  - `LFS_ENFORCE_LINUX_GUI_BACKENDS` (ON).
  - `LFS_CUDA_COMPILER_CACHE`, `ENABLE_COMPILER_CACHE` (ON),
    `LFS_VCPKG_CLEAN_AFTER_BUILD` (OFF, master).
  - Developer toggles: `LFS_ENABLE_VULKAN_VALIDATION` and others
    (`cmake/DeveloperOptions.cmake`).
- **CUDA architecture selection:**
  - With CUDA ≥ 13.1, the build detects the architecture through `nvidia-smi`.
  - When there is no GPU, it falls back to "using CUDA architecture 8.6"
    (`CMakeLists.txt` L429-438). **Build on the GPU session, or pass
    `-DCMAKE_CUDA_ARCHITECTURES=120`.**
- **Portable build.** `cmake -B build -DBUILD_PORTABLE=ON && cmake --build
  build && cmake --install build --prefix ./dist` produces
  `dist/bin/run_lichtfeld.sh`.
  - It "works on any machine with an NVIDIA driver".
  - It excludes `libcuda.so` (v0.5.3 release body).
  - It is a good artifact to build once and store on HF (about 518 MB per the
    docs table).
- **LibTorch is needed for tests only.** "a LibTorch SDK is required to
  configure the test build. It is not needed for the application itself, which
  is LibTorch-free" (`docs/building_and_distribution.md` § Tests).

### 4.3 Does `--headless` touch Vulkan, SDL or a display at run time?
**Verdict:** headless training, `--render-camera-path`, `eval`, `convert`
(splat formats), `preprocess` and `mask-video` initialise **only CUDA**. They
should use the RTX PRO 6000 on molab. Three exceptions below need Vulkan.

Evidence (master `9b6dce25b`):
1. **SDL init.** `SDL_Init(SDL_INIT_VIDEO)` appears only in
   `src/visualizer/window/window_manager.cpp` L769/L790, and
   `SDL_InitSubSystem(SDL_INIT_GAMEPAD)` only in
   `src/visualizer/input/gamepad_service.cpp`. Neither file is reached on the
   headless path.
2. **Vulkan instance creation.** `vkCreateInstance` is called in
   `src/visualizer/window/vulkan_context.cpp` (viewer), the Vulkan splat
   rasterizer `src/rendering/rasterizer/vulkan/src/gs_renderer.cpp` (used only
   from `src/visualizer/rendering/vksplat_viewport_renderer.hpp`),
   `src/visualizer/vr/openxr_service.cpp`, and **`src/rendering/mesh2splat.cpp`
   L1167-1179**. libplacebo creates a Vulkan instance for HDR video tone
   mapping (`src/io/hdr_libplacebo.cpp` L206).
3. **Dispatch.** `Application::run` sends `render_path` →
   `runHeadlessRender`, `evaluate_only` → `runHeadlessEvaluation`, and
   `headless` → `runHeadless`/`runHeadlessWithTCP`, all **before**
   `runGui(...)` (`src/app/application.cpp` L1816-1856). Only `runGui` selects
   `GraphicsBackend::Vulkan` (L1616).
4. **`runHeadless` (L983-1218)** calls only scene loading,
   `training::initializeTrainingModel`, `Trainer::initialize/train` and
   `export_final_splats`. The trainer's Vulkan interop barrier "Headless
   leaves both empty (no-op)" (`src/training/trainer.hpp` L347-366).
5. **Headless render and timelapse use the CUDA rasterizers.**
   `runHeadlessRender` calls `training::fast_rasterize(...)` (L1392).
   Timelapse uses `gsplat_rasterize`/`fast_rasterize` (`src/training/trainer.cpp`
   L8765-8770).
6. **GPU preflight.** `preflightGpu` in `src/app/application.cpp` L1456 is
   CUDA-only. `main.cpp` notes CLI-only modes "must not create a CUDA primary
   context just for HUD metrics".

**Exceptions that need Vulkan (they would land on llvmpipe on molab):**
- `--init <mesh>`, `--noise-infill-mesh`, the `mesh2splat` subcommand, and
  `convert` from a mesh. All of them call `rendering::mesh_to_splat`
  (`src/training/training_setup.cpp` L265-278, `src/training/noise_infill.cpp`
  L264-267, `src/app/converter.cpp` L546).
  - That code needs a Vulkan device with graphics, `geometryShader` and
    `fragmentStoresAndAtomics`. It scores a discrete GPU 100 and any other
    device 10 (`src/rendering/mesh2splat.cpp` L1199-1233).
  - On molab it would pick llvmpipe (CPU) if lavapipe reports those features,
    or fail. **Unconfirmed which.** For a SiteScape *mesh* init, convert
    elsewhere or use a point-cloud PLY `--init`, which does not need Vulkan.
- HDR → SDR video tone mapping in the video extractor (libplacebo).
- The GUI, MCP (GUI-only) and OpenXR. None of these are needed headless.

**Runtime linkage caveat.** `lfs_core`'s CUDA module links `Vulkan::Vulkan`
(`src/core/cuda/CMakeLists.txt` L79), and SDL3 is linked as well. The loader
library (`libvulkan.so.1`) and SDL3 must therefore be *resolvable* at load
time, even though headless never creates an instance. molab has a Vulkan
loader (llvmpipe works), and a portable build bundles its libs. Confirm with
`ldd` on the first build.

**How to verify on molab** (machine-checkable):
- Run `LichtFeld-Studio --headless -d <small dataset> -o out --iter 500
  --export ply` with `VK_LOADER_DEBUG=all`.
- Expect exit 0 and `out/project.licht` plus the PLY present.
- Expect no `vkCreateInstance` in the loader log.
- Expect the process listed by `nvidia-smi` during training.

---

## 5. The 360 plugin: reference and headless use

### 5.1 Stages (`core/pipeline.py` docstring; `README.md` § How It Works)
1. **Ingest.**
   - `.osv` and single-file `.insv` (X4/X5) are demuxed by `core/osv_handler.py`.
   - Older `_00_`/`_10_` `.insv` pairs go through
     `paired_extractor.detect_insv_pair`.
   - Other inputs: pre-split front and back `.mp4` (`source_mode="split"`),
     ERP `.mp4`, single-lens 1:1 fisheye video, or image folders (ERP;
     dual-fisheye as one folder or front+back; single-lens).
2. **Extract.**
   - `extraction_sharpness` `none|basic|better|best` (default `best`).
     - `none` extracts "at fixed intervals, no analysis".
     - `basic` scores "~10 candidates per interval".
     - `better` and `best` score every frame (`core/sharpest_extractor.py`
       L131-137).
   - `blur_metric` `tenengrad|laplacian`; `all_frames`; `interval` (s).
   - GPU (NVDEC + CUDA OpenCV) extraction is optional, enabled from the panel.
3. **Mask.**
   - The UI exposes **only SAM 3**: `masking_method = "sam3_cubemap"`,
     `mask_backend = "sam3"` (`panels/prep360_panel.py` L3561-3564), with text
     prompts (default `["person"]`).
   - The library also has `masking_method="fullcircle"`. That path is YOLO
     (yolov8s) + SAM v1 detection with SAM 2.1 video tracking
     (`SAM2_MODEL_ID = "facebook/sam2.1-hiera-large"`, `core/backends.py`
     L198-1500).
   - ERP and pinhole: detection runs on pinhole reframes and is back-projected
     and OR-merged into an ERP mask.
   - Fisheye: detection runs on the raw lens frames, plus a circle mask
     (`fisheye_circle_margin`, default 6 %).
   - `enable_overlap_masks` (Voronoi anti-overlap masks for COLMAP) defaults to
     True.
4. **Reframe** (pinhole modes). Presets `cubemap` (6), `low` (12), `medium`
   (16, the default), `high` (20), `ultra` (24), all with 90° views
   (`core/presets.py` L193-302; README table). `output_size` options are 960
   to 3840 (default 1920).
5. **Align: COLMAP 4.1 through pycolmap.**
   - `colmap_feature_type` `sift|aliked_n16rot|aliked_n32`.
   - `colmap_matcher_type` `bruteforce|lightglue`.
   - `colmap_matcher` `sequential|exhaustive`, with
     `colmap_sequential_overlap` 2-20 (default 10).
   - `loop_detection`, `colmap_guided_matching`, `colmap_sift_affine_dsp`.
   - `colmap_mapper` `incremental|global` (GLOMAP, which has no rig support).
   - `colmap_ba_solver` `auto` (Hybrid), `caspar`, `ceres_gpu`, `ceres`.
     Caspar supports PINHOLE/SIMPLE_RADIAL only.
   - Match budget `fast` 8,192 / `balanced` 16,384 / `default` 32,768 / `high`
     65,536 / `custom`.
   - `sift_preset` `normal|high|custom`.
   - Source: `core/pipeline.py` L78-176; README § COLMAP Integration.
6. **Output.**
   - `output_mode` `pinhole` | `erp_native` (EQUIRECTANGULAR) | `fisheye`
     (OPENCV_FISHEYE, native).
   - `training_output` / `fisheye_training_output` `native|pinhole|both`.
     Pinhole crops are *derived* from the native poses, with "no second COLMAP
     run".
   - Each dataset writes `sparse/0`, `transforms.json`, `pointcloud.ply` and
     `masks/` (README § Output Structure).

**Rig constraints.**
- The pinhole modes lock the virtual cameras of one panorama.
- For dual fisheye, `use_rig` is "experimental — default off" and the panel
  never sets it.
  - With `use_rig` on, `write_dual_fisheye_rig_config` uses an assumed
    "25mm/180°" transform with `refine_sensor_from_rig=True`
    (`core/pipeline.py` L169, L2698-2733).
  - Without it, each lens is a separate OPENCV_FISHEYE camera, calibrated by
    BA.
- `camera_family` is `dji_osmo360` or `insta360`. Only the Osmo has a
  calibrated prior. `"insta360": None  # TBD — calibrate a representative
  unit` (`core/fisheye_priors.py` L16-30), so Insta360 starts from a generic
  fisheye guess.

### 5.2 Changelog summary (`CHANGELOG.md`, GitHub releases v0.4.0 and v0.5.0)
- **0.5.0 (2026-08-19).**
  - Use an existing `sam3.pt` without an HF token.
  - Fix for ALIKED and LightGlue crashes: it downloads two Windows ONNX Runtime
    provider DLLs, about 262 MB (`core/ort_provider_repair.py`).
- **0.4.0 (2026-08-07).** Single-lens fisheye image folders; "Keep source
  images" (default on); pre-existing masks for fisheye folders; honest COLMAP
  progress.
- **0.3.0 (2026-08-06).** **BREAKING:** ERP output moved under
  `<output>/colmap/`. Training-output selector for image folders and ERP video.
  GLOMAP BA forced to Ceres-GPU.
- **0.2.0 (2026-07-10).** CPU OpenCV baseline, SAM 3 runtime in the base
  dependencies, opt-in GPU extraction.
- Earlier commits:
  - COLMAP 4.1 upgrade and `erp_native` (`05d6d28`, 2026-07-03);
  - single-lens fisheye path (`f54e436`);
  - "Fisheye (Pinhole)" mode retired (`ff59e4b`).

### 5.3 Python dependencies (`pyproject.toml`)
- **Packages:**
  - `huggingface-hub==1.9.0`
  - `opencv-contrib-python==4.13.0.92` (CPU; the CUDA overlay is Windows-only)
  - `numpy`, `pycolmap`, `static-ffmpeg`
  - `sam2==1.1.0`, `ultralytics>=8.4.33`, `segment-anything>=1.0`
  - `torch>=2.11.0`, `torchvision>=0.26.0`
  - `sam3>=0.1.3`
  - `triton-windows` (win32 only)
- **Windows-only sources:**
  - The GPU pycolmap wheel comes from `lyehe/build_gpu_colmap` for
    `sys_platform == 'win32'` only.
  - The torch cu128 index is also Windows-only.
  - README: "On Linux, CPU build from PyPI".
- SAM 3 weights are gated (`facebook/sam3` on HF), or you supply a local
  `sam3.pt`.

### 5.4 Windows-only parts that break Linux
- **COLMAP never runs on Linux without a patch.** Every COLMAP stage (feature
  extraction, matching, mapping) runs in a subprocess launched with
  `_VENV_PYTHON = str(_PLUGIN_DIR / ".venv" / "Scripts" / "python.exe")`
  (`core/colmap_runner.py` L541, L770).
  - That path does not exist in a Linux venv.
  - The module-level constant is read at call time, so a caller can patch it:
    `core.colmap_runner._VENV_PYTHON = sys.executable`. This is untested.
- **The X5 container path rejects our H.264 `.insv`.** The X4/X5 handler
  parses only HEVC streams: `if codec_type == "video" and codec_name ==
  "hevc"`. It raises "Expected 2 HEVC video streams in dual fisheye container"
  when fewer are found (`core/osv_handler.py` L19-23, L280-296).
  - Our A1/X5 `.insv` holds **H.264** streams, so the container path will
    reject it.
  - Workaround: demux with ffmpeg to `front.mp4`/`back.mp4`
    (`-map 0:v:0`/`-map 0:v:1 -c copy`), then use split mode, or extract
    frames to a two-folder image source.
  - The split and extraction paths accept H.264: `paired_extractor.py` L227
    says "Use HEVC/H.265 or H.264 for GPU extraction".
- **Other Windows-only code that is a no-op on Linux:** Job Objects, the
  `CREATE_NO_WINDOW` flags, the GPU-extraction installer (`nvcuda.dll`, CUDA
  `*.dll`s), and the ORT DLL repair. `lib/_C.pyd` and `lib/python3.dll` are
  Windows binaries.
- **Linux pycolmap is CPU-only**, so there is no GPU SIFT, cuDSS Ceres or
  Caspar. COLMAP 4.1 GPU on Linux would need a CUDA COLMAP/pycolmap build
  (**unconfirmed** source; see §7).

### 5.5 Can `core/pipeline.py` run headless outside LFS?
**Yes, with the patches above (unconfirmed by execution).**
- `PipelineJob(config, on_progress, on_complete).start()` runs `_run` on a
  daemon thread, with `cancel()`, `stage`, `progress` and `status`
  (`core/pipeline.py` L304-372).
- The only `lichtfeld` import in `core/` is the lazy, `try/except`-wrapped
  `import lichtfeld as lf` inside `_find_uv()` (`core/setup_checks.py`
  L683-690). It falls back to `shutil.which("uv")`.
- `pipeline.py` imports `is_sam3_masking_ready` from `setup_checks`. That
  checks for sam3 and weights, not LFS.
- The panel performs the final import (`lf.load_file`), "not here"
  (`core/pipeline.py` docstring).
- Running it on molab requires:
  - a Python 3.12 env with the dependencies above;
  - patching `_VENV_PYTHON`;
  - H.264-safe ingest (split mode or image folder);
  - a decision about CPU vs CUDA COLMAP.
- `.join()` the thread in the notebook cell, or poll `is_running`.

---

## 6. Recommended settings for OUR capture
These are inferences from the sources above, not tested settings.

1. **Ingest.**
   - Demux each `.insv` into two H.264 lens videos with ffmpeg.
   - Run plugin `PipelineConfig` with:
     - `input_type="dual_fisheye"`, `source_mode="split"`,
       `camera_family="insta360"`;
     - `output_mode="fisheye"`, `fisheye_training_output="both"`;
     - `extraction_sharpness="best"`, `interval` 0.5-1.0 s for drone passes.
   - `use_rig` stays off. Our top/bottom lens layout is not the assumed
     "25mm/180°" front/back prior.
2. **Masks (people walking through).**
   - Use SAM 3 with prompts `["person"]` (`masking_method="sam3_cubemap"`,
     `mask_backend="sam3"`) on raw lens frames. Fisheye mode applies the circle
     margin too.
   - An alternative is LFS `mask-video <dataset> --circle … --recenter
     --fisheye-fov <X5 FOV>` [master-only]. It tracks one seeded subject, so it
     needs one run per person: a poor fit for crowds.
   - Train with `--mask-mode ignore` (0 = ignored, 255 = kept).
3. **Alignment.** Use SIFT with sequential matching, overlap 10-15 and
   `loop_detection=True` (the lodge circuits revisit viewpoints), and the
   incremental mapper. On Linux pycolmap this is CPU. Budget time or obtain a
   CUDA COLMAP.
4. **Photoreal splat (native fisheye dataset).**

   ```text
   LichtFeld-Studio --headless -d <native> -o <out> --gut --strategy mrnf
     --mask-mode ignore --eval --test-every 8 --export ply,spz,ssog
   ```

   - MRNF turns exposure correction on by default, which suits varying
     exposure. Do **not** add `--ppisp` or `--bilateral-grid` unless you also
     pass `--no-exposure-correction` (they are mutually exclusive).
   - Keep `--max-width 3840` (the default).
   - Raise `--max-cap` above 5 M only after a VRAM check on 96 GB.
5. **Pinhole variant** (from `both`). Train without `--gut`. Add `--pose-opt`
   [master-only] if the poses look soft. `--pose-opt` and `--gut` cannot be
   combined.
6. **Geometry.**
   - Add `--use-normal-loss` (normal priors are auto-generated) and optionally
     `--use-depth-loss`. Whether the MoGe priors are valid on fisheye images is
     **unconfirmed**; test on the pinhole variant first.
   - LFS does **not** extract meshes. Use an external splat→mesh tool or COLMAP
     MVS on the pinhole dataset for measured meshes.
7. **Metric scale.**
   - SiteScape PLY as a point-cloud `--init` (no Vulkan needed) only after
     aligning it to the COLMAP frame externally. "a mesh must be in the
     dataset's coordinates"; the same holds for clouds.
   - Or place AprilTag tag36h11 markers and use `scale_scene_by_apriltags`
     [master-only, Python and GUI, not headless CLI].
8. **Region of interest.** Use `--cropbox x0,y0,z0,x1,y1,z1
   --cropbox-loss-weight 0` (0.5.4.2+) around the lodge, and `--crop`
   [master-only] to drop exterior splats at the end.
9. **molab hygiene.**
   - Set `TMPDIR` to scratch.
   - Mirror `~/.lichtfeld/onnx/*.lfw` and the portable `dist/` to HF.
   - Run with `--no-download` and `--model`.
   - Save `.licht` with `--save-project-at-iter` so a 12 h session can resume
     (`--headless --resume project.licht`).

---

## 7. Open questions (unconfirmed)
1. **Build time and success on molab.** Does a full vcpkg build of LFS succeed
   with pixi/conda-forge GCC 14, CUDA 12.8-13.x and GTK3 within one session?
   The size of the vcpkg binary cache to store on HF is also unknown.
2. **Linkage.** Does the portable build's `run_lichtfeld.sh` resolve
   `libvulkan.so.1`/SDL3 on molab? Does headless training log any Vulkan
   loader activity? This is verifiable with `VK_LOADER_DEBUG=all` and `ldd`.
3. **Mesh2Splat on llvmpipe.** Does lavapipe expose `geometryShader` and
   `fragmentStoresAndAtomics` on molab, so that it works (slowly) on CPU?
4. **The X5's real codec, stream order and lens FOV.** Is stream 0 the bottom
   or the top lens? The plugin assumes "stream 0 = back" for HEVC X4/X5. Does
   the A1 `.insv` match the X5 handheld layout?
5. **CUDA COLMAP on Linux.** Is there a CUDA-enabled pycolmap or COLMAP 4.1 for
   Linux (conda-forge `colmap` CUDA variant or a PyPI CUDA wheel), so that GPU
   SIFT, LightGlue and Ceres-GPU/cuDSS work? The plugin documents only a CPU
   PyPI build.
6. **LLMDet and MoGe-3 consumers.** Assets were published (2026-11-12 and
   2026-09-23), but no consuming code was found in master or dev. Is the "SLAM
   pipeline" and text mask selection in an unpublished branch?
7. **GUT with >180° lenses.** Does `--gut` with OPENCV_FISHEYE handle >180°
   lenses without rim artefacts? 0.5.4.1 notes "Keep the whole calibrated rim
   of a GUT fisheye". Does `preprocess` produce usable normals on fisheye
   frames?
8. **Equirectangular datasets.** Do they train only with `--gut`? The
   non-pinhole check implies `--gut` or `--undistort`; undistorting ERP is
   unclear.
9. **Unreleased features.** When will the [master-only] features (pose
   refinement, AprilTag scaling, mask-video, batch-train, `--crop`) ship in a
   tagged release? Building master instead of `v0.5.4.2` trades stability for
   these features.
