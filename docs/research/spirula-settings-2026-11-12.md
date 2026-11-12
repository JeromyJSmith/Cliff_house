# Spirula Studio settings reference (researched 2026-11-12)

This is a settings reference for driving Spirula Studio headless from a Marimo
notebook. It is written for our capture: Insta360 dual-fisheye `.insv` walks of a
historic stone lodge, plus SiteScape phone-LiDAR PLYs of parts of the building.

**How the sources were checked.** Every flag listed here was read from
`harry7557558/spirula-studio` at commit `de6224dc` (master, 2026-11-12, same day
as release `v2026.11.12`), from its GitHub release notes, or from the strings in the
`v2026.11.12` Linux release binary. That binary was inspected with `strings` and
`objdump` and never run. Source paths are relative to the repository root. Use
`https://github.com/harry7557558/spirula-studio/blob/de6224dc/<path>` to open any
of them. Anything not confirmed is marked **unconfirmed**.

Notation: `[default]` is the compiled default before any preset or macro runs.

---

## 1. What Spirula is: license, platforms, versions

### Identity
- The official repo is **https://github.com/harry7557558/spirula-studio**. It had
  about 2.35k stars on 2026-11-12. It is the renamed `spirulae-splat`
  (`README.md`, "Trivia"). Other `spirula*` repos found by
  `gh search repos spirula` are forks or add-ons. Examples are
  `timfennell/blender-splat-render` and `savvasdalkitsis/spirula-studio-mask-editor`.
- It ships as one self-contained binary, `spirula`. The binary holds a GUI
  (Dear ImGui) and a set of CLI subcommands. It needs no Python, PyTorch or
  COLMAP install (`README.md`; `src/app/README.md`).
- It is maintained almost entirely by one person (`README.md`). Releases come
  every 1 to 2 weeks, and most notes say "carries training quality difference".
  **Pin a version and record it in every run manifest.**

### License
- The license is **GPL-3.0** (`LICENSE`, and GitHub's license API reports
  `gpl-3.0`).
- **What this means for us:** we run the unmodified binary as a separate process
  and copy none of its code. That is "mere aggregation" or arm's-length use, so
  GPL obligations do not reach our notebook or our outputs. Trained splats, meshes
  and point clouds are our data, not derivative works of the program. (This is our
  reading of the GPL, not legal advice.) Two cases would change this:
  - If we **redistribute the binary**, for example by uploading it to our HF
    dataset, we must also offer the matching source. Linking to the upstream
    release and tag is the simplest way to comply.
  - If we **copy or port code**, say a Python port of its rig solver, that code
    becomes GPL.
- **Third-party model weights carry their own licenses.** They are never bundled
  and are fetched separately (`LICENSES/`, `README.md` "Notes regarding
  third-party licensing", `docs/dense.md`):
  - SAM 2.1: Apache-2.0
  - SAM 3: Meta's own non-standard license
  - Grounding DINO: Apache-2.0
  - BiRefNet: MIT
  - RoMa v2: MIT plus the **DINOv3 License**
  - FlexGlue: MIT plus the **DINOv3 License**
  - MoGe, Metric3D, Marigold: their own licenses
- **Headless license gate.** Commands that fetch a licensed model need
  `--accept-license <family>=yes`. The flag works with every subcommand and is
  stripped from argv before the subcommand parses it. Families: `sam2`, `sam3`,
  `gdino`, `birefnet`, `roma`, `flexglue` (`src/app/Main.cpp`,
  `src/app/cli/LicenseCli.cpp`, `src/core/LicenseConsent.h`,
  `src/app/ModelLicenses.h`).
  - Acceptance is saved under `XDG_CONFIG_HOME` or `HOME`. molab wipes that at
    shutdown, so **pass the flag in every session**.
  - Without a TTY and without `=yes`, the command fails. It does not hang.
- **Patent-encumbered video decoding.** `-DSS_ENABLE_PATENTED=ON` enables
  in-process H.264/HEVC GPU decoding. The release binary references
  `VK_KHR_video_decode_queue`, so it appears to include this. The user is
  responsible for AVC/HEVC patent compliance (`README.md`, `docs/build.md`).
  With `--decoder ffmpeg`, decoding goes to an external ffmpeg instead.

### Platforms and distribution
Assets on the `v2026.11.12` release (`gh api repos/.../releases`):

| Asset | Platform |
|---|---|
| `spirula-2026.11.12-ubuntu-vulkan-x86_64.zip` | Linux x86_64, Vulkan backend (the zip holds one ELF, `spirula`, 263 MB) |
| `spirula-2026.11.12-windows-vulkan-x86_64.zip` | Windows x86_64 |
| `spirula-2026.11.12-macos-vulkan-arm64.dmg` | macOS **Apple silicon only** |

- **There is no CUDA release binary.** CUDA is a "legacy" backend you build from
  source (`-DSS_BACKEND=cuda`). It has the same training and meshing features but
  **no native SfM, frame extraction or AI masking**, and **no spherical-beta
  lobes** (`README.md` backend table; `docs/notes/spherical-beta.md`).
- **Use the Vulkan Linux binary on molab's NVIDIA GPU.** "Linux/CUDA" for us means
  Vulkan on the NVIDIA driver.

#### Linux runtime requirements
Read from the release binary (`objdump -p` NEEDED entries and `strings`):
- Shared libraries the binary requires:
  - `libvulkan.so.1`
  - `libOpenGL.so.0` (glvnd). It is linked even for CLI use because the GUI is
    compiled in.
  - `libgomp.so.1`, `libstdc++.so.6`, `libgcc_s.so.1`, `libm`, `libc`
- **glibc ≥ 2.38 and GLIBCXX_3.4.32.** This is roughly Ubuntu 24.04 or newer.
  **On Ubuntu 22.04 (glibc 2.35) it will not start.** Check molab's base image
  (see §6).
- X11, Wayland and GLFW libraries are only loaded at runtime for the GUI. They
  are not needed for CLI use.
- The container must expose the **NVIDIA Vulkan ICD**: `nvidia_icd.json`, plus
  `NVIDIA_DRIVER_CAPABILITIES` that include `graphics`. Compute-only CUDA
  containers often lack it. Verify with `vulkaninfo --summary` or with
  `spirula sam devices`.

#### macOS (the owner's machines)
- **Apple silicon:** supported. The official arm64 DMG has been validated since
  v2026.8.14 (`README.md` News). It uses statically linked MoltenVK.
  - v2026.11.12 sped up masking and depth/normals on Apple silicon.
  - MoltenVK has no Vulkan video decode. `sam extract` therefore needs ffmpeg on
    `PATH` (`--decoder auto` falls back to it). The CLI fallback landed in
    v2026.9.30 (issue #118).
- **Intel Mac (x86_64 + AMD Radeon Pro 580X): no official binary.** Building from
  source on x86_64 macOS looks possible on paper, but nobody has tested it
  (**unconfirmed**):
  - `cmake/SsVulkan.cmake` fetches a *universal* MoltenVK.
  - `cmake/SsSlang.cmake` notes that macOS x86_64 Slang assets exist.
  - Build with `brew install cmake ninja libomp` and
    `bash build_develop.bash -DSS_BACKEND=vulkan -DSS_ENABLE_PATENTED=ON`
    (`docs/build.md` "macOS").
  - `docs/build.md` also warns that Homebrew archives are host-only.
  - Treat it as a viewer or light-work machine at best. Do the training on molab.

### Versions (all 2026)
These are from GitHub release notes, which are authoritative over the
radiancefields articles.

| Version | Features relevant to us |
|---|---|
| v2026.8.1 / 8.14 | First binaries; macOS support (8.14) |
| 8.17 | MoGe / Metric3D depth and normals |
| 8.23 | Options to delay distortion refinement; PPISP exposure from EXIF |
| 9.2 | 360-camera preset tuning; flip masks |
| 9.8 | LoMa; EXIF-GPS metric scale; centered-object preset; pseudorandom background |
| 9.10 (pre) / 9.13 | **Metric scale and orientation from IMU/GPS telemetry** (.insv tested); **rig constraint for dual fisheye**; resumable dataset creation |
| 9.20 | Adaptive frame extraction; warm start from PLY (`init_ply`); dataset presets and batch |
| **9.24** | Editing; render export; **MCP server**; insp/lrv input; fps 0 extracts every frame |
| **9.30** | **Partitioned training and merge**; **SAM 2.1 natural-language prompts**; BiRefNet; **training VRAM forecast and OOM warning**; per-camera fixed-area masks for dual fisheye |
| **10.6** | **ROI training**; **LiDAR scans (E57/LAS/PLY) for metric scale and depth/normal maps (experimental)**; separate feature masks |
| **10.16** | **Spherical-beta lobes**; **dense init (`spirula dense`, RoMa v2)**; I-Log LUT support; reduced partition seams; revised 360 mask prompts |
| 10.30 | MoGe 3 / Marigold v2; **two-point distance scaling**; **AprilTag/ArUco alignment (experimental)**; skip blurry and duplicate frames |
| 11.12 (current) | Calibration-residual correction (rolling shutter); improved floater suppression (now mild/moderate/strong); GLOMAP-style global mapper; FlexGlue matcher; `finish_command`; **distraction robustness moved to "advanced"** |

Articles used for cross-checking only; no flags were taken from them:
- [radiancefields.com platform page](https://radiancefields.com/platforms/spirula-studio)
- [tag page](https://radiancefields.com/tags/spirula-studio)
- [v2026.9.24](https://radiancefields.com/spirula-studio-v2026.9.24-adds-editing-and-an-mcp-server)
- [v2026.9.30](https://radiancefields.com/spirula-studio-v2026.9.30-trains-large-scenes-in-parts-and-merges-them)
- [v2026.10.6](https://radiancefields.com/spirula-studio-v2026.10.6-brings-laser-scans-into-its-training-pipeline)
- [v2026.10.16](https://radiancefields.com/spirula-studio-v2026.10.16-adds-spherical-beta-lobes-and-roma-v2-dense-initialization)
- [pyshine overview](https://pyshine.com/Spirula-Studio-3D-Gaussian-Splatting-Training-Without-the-Python-Stack/)

The articles list no CLI flags, so none of the flags below come from them.

---

## 2. CLI reference

### 2.0 Top level
Source: `src/app/Main.cpp`, `src/app/Tools.h`, `src/i18n/catalog/Cli.h`.

```
spirula                       # GUI
spirula <file-or-folder>      # GUI, opens the path
spirula <command> [options]   # gui sfm train sam geometry dense mesh e57 lidar encode partition marker
spirula export-bg <checkpoint_dir|run_dir|state.tar> [output.webp]
spirula --help | help | --version | -v
global: --lang <code>   --accept-license <family>[=yes][,...]
```

- Each subcommand prints its own `--help`.
- A binary renamed or symlinked to `spirula-<tool>` runs that tool directly.
- stdout is line-buffered when it is not a TTY, so piped logs stream (`Main.cpp`).
- Environment variables:
  - `SS_WORKERS_PER_GPU`
  - `SS_VK_DEVICE`
  - `SS_NN_LOG=0..3`
  - `SS_PROFILE=1`
  - `SS_FORECAST_LOG=1` (train)
  - `SS_SFM_MAP_PROF=1` (sfm)
  - `SS_GUI_AUTOMATION=1`, `SS_GUI_OFFSCREEN=1` (GUI and MCP)

### 2.1 `spirula train`
Sources: `src/app/cli/main.cpp`; field table `src/config/TrainConfig.h`
(`SS_CONFIG_FIELDS`); help text `src/i18n/catalog/TrainFields.h`; presets in the
same header (`train_apply_preset`).

```
spirula train [<preset>] --data <dir> [--flag value ...] [--device <index|name|auto|uuid:hex>]
spirula train <preset> --help        # basic flags, with preset-resolved defaults
spirula train <preset> --help-all    # every flag
```

**Parsing rules:**
- Flag names are the field names. `-` and `_` are interchangeable.
- **Booleans take a value**: `--disable-viewer 1`.
- `--key=value` works for single-value flags.
- `none`, `None` and `null` clear optional and string fields.
- Tuples take N tokens: `--bilagrid-shape 16 16 8`.
- Run config is saved as `config.json` in the run folder. Its keys are the field
  names, which is the format of our earlier run's config.

**Resolution order:** compiled defaults, then preset, then macros (`quality`,
`distraction_robustness`, `calib_correction`, `floater_suppression`,
`sb_lobes`), then explicit flags. A macro **never overwrites a flag you set
explicitly** (`train_resolve_macros`).

**Exit codes and signals:**
- Exit code 0 means OK, 1 means error, 130 means stopped by SIGINT.
- The first SIGINT finishes the current step, writes a resumable checkpoint and
  prints the resume line. A second SIGINT kills immediately.
- **There is no SIGTERM handler.** SIGTERM or a kill loses everything since the
  last periodic save.

Every field follows, grouped by the table's sections, in the form
`name [default] {choices}`.

**run**
- `data` (required)
- `resume [""]` (folder)
- `output_dir_prefix [outputs]`
- `output_dir_name [""]`
- `num_iterations [30000]`
- `steps_per_save [2000]`: -1 saves only at the end; 0 never saves
- `save_only_latest_checkpoint [1]`
- `save_full_checkpoint [0]`
- `save_eval_images [0]`
- `eval_lpips [1]`
- `eval_align [unset]`
- `lpips_checkpoints`
- `log_performance [0]`
- `viewer_port [7007]`
- `disable_viewer [0]`
- `keep_viewer_alive [1]`
- `finish_command [""]`

**dataset**
- Format and folders:
  - `data_format [auto] {colmap|nerfstudio|metashape}`
  - `image_dir [images]`
  - `mask_dir [masks]`
  - `load_masks [1]`
  - `apply_loss_for_mask [unset]`
  - `flip_mask [0]`
  - `mask_boundary_offset [0]`
  - `depth_dir [depths]`
  - `normal_dir [normals]`
  - `load_depths [1]`
  - `load_normals [1]`
  - `depth_unit_scale_factor [0.001]`
  - `colmap_recon_dir`
  - `metashape_xml`, `metashape_ply`, `metashape_psx`
- Seeds:
  - `seed_pointcloud`
  - `init_ply`
  - `init_ply_add_points [0]`
- Partition and ROI:
  - `partition`
  - `partition_part [-1]`
  - `roi_region`
  - `roi_outside_weight [1e-4]`
  - `roi_outside_opacity_decay [1.0]`
  - `roi_splat_samples [4]`
  - `roi_mask_pixels [1]`
- Resolution:
  - `sampling_seed [0]`
  - `train_resolution_divisor [0]`
  - `downscale_rounding_mode [floor]`
  - `cache_downscaled_images [1]`
  - `progressive_resolution [0]`
  - `progressive_resolution_start [4]`
  - `progressive_resolution_full_at [0.3]`
  - `progressive_resolution_schedule`
  - `progressive_splat_budget [1]`
  - `progressive_splat_budget_schedule`
- Evaluation split:
  - `eval_mode [all] {fraction|filename|interval|all}`
  - `eval_interval [8]`
  - `train_split_fraction [0.9]`
  - `validation_fraction [0]`
- Wide-lens warping:
  - `warp_to_pinhole [0]`
  - `warp_spherical_to_pinhole [1]`
  - `warp_face_fit [uniform] {uniform|per-face}`
  - `warp_back_face [0]`

**scene**
- `exif_orientation [orient] {none|orient|apply}`
- `orientation_method [up] {pca|up|vertical|none|gsplat}`
- `center_method [poses] {poses|focus|none|gsplat}`
- `auto_scale_poses [1]`
- `outlier_threshold [inf]`
- `scene_center [auto] {auto|none|point-median|camera-median|camera-focus|point-mean|camera-mean}`
- `scene_center_threshold [20]`
- `relative_scale [unset]`

**splats**
- Basis and primitive:
  - `primitive [3dgs] {3dgs|mip|3dgut}`
  - `sh_degree [3]`
  - `sb_lobes [0]`
  - `sh_degree_warmup_every [0]`
- Background:
  - `background_mode [color] {color|noise|pseudorandom|random|sh}`
  - `background_color [0 0 0]`
  - `background_sh_degree [4]`
  - `background_export_height [512]`
  - `background_noise_warmup [2000]`
  - `background_noise_pre_warmup [0.25]`
  - `background_match_luminance [0]`
- Initialization:
  - `viewer_kernel_fraction [0.3]`
  - `scale_init [0.35]`
  - `opacity_init [unset]`
  - `suppress_initial_scales [0]`
  - `random_init [auto] {never|auto|always}`
  - `random_init_fraction [0.1]`
  - `random_init_distribution`, `random_init_center`, `random_init_spread`,
    `random_init_std [1]`

**detail** (densification and budget)
- Macros and budget:
  - `quality [medium] {low|medium|high|ultra}`
  - `cap_max [1000000]`
  - `distraction_robustness [off] {off|mild|strong}`
  - `min_init_fraction [0.1]`
  - `growth_factor [1.05]`
  - `min_opacity [0.005]`
  - `dead_criterion [either] {opacity|max_weight|either}`
- Refinement schedule:
  - `refine_every [100]`
  - `refine_start_iter [500]`
  - `refine_stop_num_iter [2500]`
  - `refine_stop_iter [14000]`
- Noise:
  - `noise_lr [160]`
  - `noise_lr_final [1.6]`
  - `noise_gate_peak_weight [1]`
- Densify scoring:
  - `use_revised_densification [1]`
  - `densify_score_mode [mean] {mean|max|median|geom}`
  - `densify_score_blend_world_grad [0]`
  - `densify_loss_map_mode [auto] {auto|none|loss_full|ssim_full|ssim_cs|ssim_structure|s_cielab|flip|flip_feature|edge_aware|robust_edge_aware|…_nms}`
  - `densify_robust_edge_aware_quantile [0.9]`
  - `densify_nms_falloff [0.5]`
  - `densify_loss_map_normalize [0]`
  - `densify_loss_map_clip_quantile [1]`
  - `densify_loss_map_power [2]`
  - `densify_accum_mode [sum]`
  - `densify_score_power [0.2]`
  - `densify_score_clip_quantile [1]`
  - `densify_final_score_power [1]`
  - `densify_learned_score [0]`
  - `densify_oversize_split_fraction [0.15]`
  - `densify_oversize_score_blend [1]`
- Splitting and size limits:
  - `use_long_axis_split [1]`
  - `long_axis_split_opacity_k [0.5 0.55 15000]`
  - `max_split_fraction [0.1]`
  - `split_weight_by_renders [0]`
  - `dead_after_epochs [2]`
  - `max_screen_size [0.3]`
  - `max_screen_size_clip_hardness [1.5]`
  - `max_screen_size_penalty [1]`
  - `max_world_size [inf]`

**loss**
- `ssim_lambda [0.2]`
- `perceptual_loss [ssim_blur_tolerant] {ssim|ssim_blur_tolerant|s_cielab|flip}`
- `l1_weight [1]`, `l2_weight [0]`
- `l1_weight_y`, `l2_weight_y`, `l2_weight_u`, `l2_weight_v` `[0]`
- `loss_scale_min_pixels [1920]`
- `num_loss_scales [0]`
- `alpha_loss_weight [0.5]`
- `alpha_loss_weight_under [0]`
- `loss_saturation_threshold [-1]`
- `loss_luminance_normalization [0]`
- `view_sampling [uniform] {uniform|deficit}`
- `view_deficit_power [0.5]`
- `view_deficit_max_ratio [8]`

**geometry**
- Floaters and distortion:
  - `floater_suppression [off] {off|mild|moderate|strong}`
  - `depth_distortion_reg [0]`
  - `normal_distortion_reg [0]`
  - `rgb_distortion_reg [0]`
  - `distortion_reg_warmup [6000]`
- Regularizers:
  - `normal_reg_weight [0.04]`
  - `normal_reg_warmup [6000]`
  - `alpha_reg_weight [0]`
  - `alpha_reg_warmup [12000]`
  - `reg_warmup_length [0]`
- Supervision from depth and normal maps:
  - **`depth_supervision_weight [0]`**
  - `normal_supervision_weight [0.01]`
  - `input_depth_is_ray_depth [unset]`
  - `supervision_warmup [0]`
- Median-depth terms:
  - `mean_median_depth_weight [0]`
  - `median_depth_normal_reg_weight [0]`
  - `median_normal_supervision_weight [0]`
  - `median_render_normal_reg_weight [0]`
  - `median_warmup [6000]`
- PCA regularizer:
  - `pca_reg_neighbors [0]`
  - `pca_reg_knn [morton-best]`
  - `pca_reg_window`, `pca_reg_refresh_every`
  - `pca_reg_start_iter [7000]`
  - `pca_reg_weight [0.1]`
  - `pca_reg_weight_final [1.0]`
  - `pca_reg_schedule [linear]`
  - `pca_reg_tangent_weight [0.001]`
  - `pca_reg_normal_weight [0.1]`
  - `pca_reg_surfel_weight [0]`
  - `pca_reg_erank_weight [0.01]`
  - `pca_reg_transparency_weight [0]`
  - `pca_reg_covariance [centers]`
  - `pca_reg_scale_agnostic [1]`

**shape**
- `opacity_reg [0.01]`
- `reg_rendered_only [1]`
- `scale_reg [0.01]`
- `opacity_reg_decay_power [1]`
- `scale_reg_decay_power [0.4]`
- `opacity_decay [0]`, `scale_decay [0]`
- `erank_reg [0.001]`
- `erank_reg_s3 [0]`
- `scale_regularization_weight [0]`
- `max_gauss_ratio [10]`
- `dc_reg [0.001]`
- `sh_reg [0.025]`
- `overexposure_reg [0]`
- `quat_norm_reg [0.01]`

**correction** (exposure and white balance)
- Bilateral grid:
  - `use_bilateral_grid [1]`
  - `bilagrid_type [ppisp] {affine|ppisp|loglinear}`
  - `bilagrid_shape [16 16 8]`
  - `bilagrid_tv_loss_weight [10]`
  - `color_shift_reg_weight [0]`
  - `color_shift_reg_ema_period [750]`
  - `use_bilateral_grid_for_geometry [1]`
  - `bilagrid_shape_geometry [8 8 4]`
  - `bilagrid_tv_loss_weight_geometry [10]`
  - `use_adagrad_bilagrid_optim [1]`
- PPISP:
  - `use_ppisp [1]`
  - `ppisp_param_type [no_crf_no_vig] {original|rqs|no_crf|no_crf_clamp|no_crf_no_vig|no_crf_no_vig_clamp}`
  - `ppisp_exposure_from_exif [0]`
  - `ppisp_exposure_arithmetic_mean [1]`
  - `apply_ppisp_before_bilagrid [1]`
  - `apply_ppisp_before_color_space [0]`
  - `use_adagrad_ppisp_optim [1]`
  - `ppisp_reg_*`
- Learning rates for the corrections:
  - `bilagrid_adagrad_lr`, `bilagrid_adagrad_depth_lr`,
    `bilagrid_adagrad_normal_lr`, `ppisp_adagrad_lr`
  - `bilagrid_lr*`, `bilagrid_depth_lr*`, `bilagrid_normal_lr*`, `ppisp_lr*`
- Calibration warp:
  - `calib_correction [basic] {off|basic|accurate}`
  - `use_calib_warp [1]`
  - `calib_warp_grid [9]`
  - `calib_warp_parallax [0]`
  - `calib_warp_start_iter [1000]`
  - `calib_warp_step [0.5]`
  - `calib_warp_smooth [0.05]`

**colorspace**
- `image_color_is_linear`, `image_color_transfer`, `image_color_gamut`
- `splat_color_is_linear`, `splat_color_transfer`, `splat_color_gamut`
- `point_color_is_linear`, `point_color_transfer`, `point_color_gamut`
- Gamut choices are `Rec.709|ACES2065-1|ACEScg|Rec.2020|AdobeRGB|DCI-P3`.

**perf**
- `cache_images [disk] {cpu|disk}`
- `max_batch_per_epoch [800]`
- `min_renders_per_refine [0]`
- `render_quantile [0.1]`
- `max_train_batch_size [-1]`
- `split_batch [1]`
- `use_fused_proj_bwd_optim [1]`
- `packed [1]`
- `quantization_level [1]`
- `bin_tile_size [0]`
- `preallocate_splat_tensors [1]`

**rates**
- `projective_depth_lr*`
- `means_lr [2.56e-4]`, `means_lr_final [3.2e-6]`
- `scales_lr [0.02]`, `scales_lr_final [0.005]`
- `quats_lr [0.0015]`
- `opacities_lr [0.025]`
- `features_dc_lr [0.005]`
- `features_sh_lr [2.5e-4]`
- `features_sb_lr [0.0025]`
- `background_dc_lr`, `background_sh_lr`
- `max_steps [unset]`
- `use_scale_agnostic_mean [1]`
- `use_per_splat_bias_correction [1]`

**Macro effects** (`train_resolve_macros` in `src/config/TrainConfig.h`):

| Macro | What it sets (only fields you did not set explicitly) |
|---|---|
| `quality low` / `medium` / `high` / `ultra` | `cap_max` 200k / 1M / **3M** / 10M and `num_iterations` 15k / 30k / **50k** / 80k |
| `distraction_robustness mild` | `densify_loss_map_power 1.0`, `densify_score_power 1.0`, `ssim_lambda 0.1` |
| `distraction_robustness strong` | the mild settings, plus `densify_loss_map_mode robust_edge_aware`, `densify_robust_edge_aware_quantile 0.75`, `densify_score_mode median` |
| `floater_suppression mild` / `moderate` / `strong` | `depth_distortion_reg` 0.01 / 0.03 / 0.1; `rgb_distortion_reg` 0.01 / 0.05 / 0.1; `sh_reg` 0.067 / 0.1 / 0.15; `max_screen_size` 0.2 / 0.1 / 0.1; clip hardness 1.25 / 1.1 / 1.1; strong also sets `pca_reg_neighbors 31`, `pca_reg_start_iter 4500` |
| `calib_correction off` / `basic` / `accurate` | `use_calib_warp` 0 / 1 / 1; `calib_warp_parallax` only for accurate; `calib_warp_grid` 9, or 15 for accurate |
| `sb_lobes > 0` (fresh run) | `sh_degree 0`, unless you set it |

### 2.2 `spirula sfm`
Sources: `src/app/cli/sfm_main.cpp`; descriptor table `src/sfm/SfmConfig.h`
(`SFM_CONFIG_FIELDS`); presets `src/sfm/SfmConfig.cpp` (`applyPresets`); help
text `src/i18n/catalog/SfmHelp.h` and `SfmFields.h`; `src/sfm/README.md`.

```
spirula sfm auto [IMAGE_DIR|DATASET_DIR] -o WORKSPACE [options]   # extract→match→map→merge
spirula sfm extract <IMAGE|DIR> [-o OUT]
spirula sfm match   <FEATURE_DIR> -o MATCHES.BIN
spirula sfm map     <MATCHES.BIN> <FEATURE_DIR> -o SPARSE_DIR
spirula sfm merge   <SPARSE_DIR|MODEL_DIR> [more...] -o DIR | --in-place
spirula sfm ba      <in_model> <out_model> [--real cpu]
```

**Exit codes for `auto`:** 0 ok, 1 usage error, 2 means no reconstruction,
3 means partial, 4 is an error.

**Boolean syntax differs from `train`:** it is `--name` / `--no-name`.

**Hand-parsed options:**
- `-o/--output`
- `--manifest FILE`, a YAML/JSON capture file. It can hold images, masks,
  camera groups, lenses, focals, `params`, `rigs:`, and `captures:` (videos with
  IMU/GPS) plus `exif:`.
- `--rig [KIND=]PREFIX,PREFIX,...`, repeatable. Forms include
  `cam0,cam1`, `'clip1,clip2:cam0,cam1'`, `'*:cam0,cam1'` and
  `dual-fisheye=cam0,cam1`.
- `--sequence PREFIX[,…]`
- `--no-masks`
- `--no-manage`
- `--progress-dir DIR`
- `--camera-model PREFIX=MODEL`
- `--focal PREFIX=F`
- `--check`, `--audit`

Table options follow as `name [default] {choices}`. **B** marks the Basic tier.

**pipeline**
- `--quality [high] {low|medium|high|extreme}` **B**
- `--data-type [individual] {individual|video|internet}` **B**
- `--pairs [auto] {auto|exhaustive|sequential|prefilter}` **B**. `auto` means
  prefilter at 100 images or more, sequential for video below that, and
  exhaustive otherwise.
- `--overlap [10]`
- `--loop-closure [on]`
- `--quadratic-overlap [off]`
- `--prefilter-sequential [off]`
- `--rig-pairs [on]`
- `--rig-pair-angle [30]`
- `--rig-pair-min-inliers [30]`
- `--max-error [3.0 px]`
- `--max-image-size [0 = frontend default]`
- `--masks` (alias `--mask-dir`) **B**
- `--flip-mask`
- `--feature-masks`

**colour**
- `--image-gamut [Rec.709]`
- `--image-linear`
- `--image-exposure`
- `--point-color [srgb] {srgb|image}`

**camera**
- `--camera-mode [folder] {single|folder|image}` **B**
- `--camera-model [opencv] {simple-pinhole|pinhole|radial|opencv|full-opencv|opencv-fisheye|thin-prism-fisheye|equirectangular}` **B**
- `--focal` **B**
- `--distortion "k1,k2,…"`
- `--exif-focal`
- `--exif-groups`
- `--exif-focal-tol`
- `--exif-orientation [orient]`

**features**
- `--features [sift] {sift|aliked-n16rot|aliked-n32|loma-b128|loma-b}` **B**
- `--max-features`
- `--aliked-max-features`, `--aliked-min-score`, `--aliked-model`
- `--loma-max-features`, `--loma-min-score`, `--loma-detector-model`,
  `--loma-descriptor-model`
- `--octaves`, `--peak-threshold`, `--edge-threshold`, `--max-orientations`
- `--profile`, `--spv-path` (extract only)

**matching**
- `--matcher [bruteforce] {bruteforce|lightglue|flexglue|loma-b128|loma-b|loma-r|loma-l|loma-g}` **B**
- `--lightglue-min-score`, `--lightglue-model`
- FlexGlue (new in 11.12): `--flexglue-min-covisibility`, `--flexglue-min-score`,
  `--flexglue-max-distance`, `--flexglue-early-stop-decay`, `--flexglue-cache`,
  `--flexglue-model`, `--flexglue-images`
- `--loma-min-match-score`, `--loma-matcher-model`
- `--ratio`, `--min-similarity`, `--cross-check`, `--max-matches`
- `--verify` (match)
- `--min-inliers`
- `--prefilter-features`, `--prefilter-train`, `--prefilter-neighbors`,
  `--prefilter-min-score`, `--prefilter-ratio`

**mapper**
- Mapper choice and intrinsics:
  - `--mapper [flat] {flat|bottom-up|global}` **B**. `global` is the
    GLOMAP-style mapper from 11.12.
  - `--compact-unused-features [on]`
  - `--focal-trials`
  - `--refine-principal-point`, `--final-principal-point [on]`, `--pp-min-images`
  - `--refine-extra-params`, `--final-extra-params [on]`
  - `--final-per-image-intrinsics [off]`
- Orientation:
  - `--orient [on]`
  - `--level [ground] {ground|cameras}`
- Metric gauge:
  - `--metric-positions FILE` (lines of `image X Y Z` in metres)
  - `--metric-gps [auto] {auto|none|horizontal|full}`
  - `--exif-attitude [auto] {auto|up|none}`
  - `--metric-max-error`, `--metric-max-error-frac [0.03]`
- Telemetry and sensor priors:
  - `--telemetry VIDEO`
  - `--sensor-gauge [auto] {auto|up|none}`
  - `--sensor-verify [on]`
  - `--sensor-map [on]`
  - `--level-erp [on]`
  - `--sensor-pairs [off]`
  - `--sensor-pair-radius [20 m]`
  - `--sensor-max-dt [3 s]`
- Registration and bundle adjustment:
  - `--min-tri-angle`, `--init-min-tri-angle`
  - `--min-pnp-inliers`, `--min-pnp-ratio`, `--min-image-points`
  - `--ba-loss {trivial|huber|cauchy}`, `--ba-loss-param`
  - `--seed-homography`
  - `--ba-real {float|double|df|cpu}`, `--ba-real-coarse`
  - `--ba-solver {auto|dense|cg}`
  - `--retri-scale`
  - `--merge-tracks`
  - `--seam-weld`
  - `--gps-scale-band`
  - `--rank-by-visibility`
  - `--seed-blocking`
- Bottom-up mapper: `--bup-atom-size`, `--bup-overlap`, `--bup-rounds`,
  `--bup-atom-threads`, `--bup-atom-ba-growth`, `--bup-joint-every`,
  `--bup-atom-tight-final`, `--bup-coarse-ba`, `--bup-atom-init-trials`,
  `--bup-atom-min-fraction`, `--bup-joint-intrinsics`, `--bup-grow-every`,
  `--bup-grow-budget`
- Growth and model limits:
  - `--ba-growth`, `--ba-growth-rtol`, `--ba-growth-patience`
  - `--max-models`, `--model-overlap`, `--model-overlap-ratio`, `--min-model-size`
  - `--pnp-ratio-visible`, `--strong-pnp-inliers`, `--strong-pnp-max-rival`
  - `--audit-evidence`

**rig**
- `--rigs`
- `--refine-rigs`
- `--rig-blind`
- `--rig-min-frames [3]`
- `--rig-max-spread [1°]`
- `--final-free-rig [off]`

**manage**
- `--max-bridges`
- `--merge`, `--grow`, `--reseed`, `--audit`, `--split`
- `--fold-split`, `--fold-max-cut`, `--fold-min-overlap`
- `--seam-min-agreement`, `--seam-relative-bar`, `--seam-min-pairs`,
  `--seam-rescue`, `--seam-max-rescues`

**merge**
- `--max-error` (merge alignment)
- `--merge-max-error`
- `--min-common`, `--merge-min-common`
- `--merge-arbitrate`
- `--min-inlier-ratio`
- `--filter-error`
- `--min-tri-angle`
- `--ba`
- `--in-place`

**input**
- `--images`
- `--features`
- `--resume` (two meanings: on `map` it is a model directory; on `auto` it is
  workspace reuse, on by default)
- `--reuse-features {auto|keep|redo}`
- `--reuse-matches {auto|keep|redo}`
- `--check`

**runtime**
- `--threads`
- `--decode-threads`
- `--decode-budget`
- `--device`
- `--quiet`

**SfM `--quality` presets** (`applyPresets`). Values for learned features are
in parentheses:

| Level | `max-image-size` | `max-features` | `prefilter-neighbors` |
|---|---|---|---|
| low | 1000 (800) | 2048 | 16 |
| medium | 1600 (1200) | 4096 | 24 |
| high | 2400 (1600) | 8192 | default |
| extreme | 3200 (2400) | 16384 | 48 |

Other preset effects:
- `--data-type video` sets `pairs sequential` (below 100 images) and halves
  `init-min-tri-angle`.
- A learned matcher forces `ratio 1.0`, `min-similarity 0` and
  `pairs prefilter`.

### 2.3 `spirula sam`: frames, masks, segmentation
Sources: `src/app/cli/sam_main.cpp`, `src/app/cli/sam_extract.cpp`,
`src/i18n/catalog/SamHelp.h`.

```
spirula sam devices
spirula sam segment --model <file> --image <file> [--text --detector --detector-threshold --box --neg-box --point --neg-point --prompt-box --multimask --threshold --nms --out]
spirula sam track   --model <file> --frames <dir> [--text --neg-text --point --neg-point --object --at-frame --mask-mode --detect-every --memory-frames --max-frames --out --detector --keep-prompted|--remove-prompted --dilate-ratio --overlay]
spirula sam mask    <images> [--out --shape <spec> --shrink [0.01] --samples [24] --dark --mask-image --preview --print --replace]
spirula sam video   --info <file>
spirula sam extract <video> [options]
common: --device --vram --profile --validate --img-size --max-size [1600] --image-gamut --image-linear/--no-image-linear --image-exposure auto|<stops>
```

`sam extract` options:
- Frame selection:
  - `-o/--out [<video>/images]`
  - `-s/--skip [1]`: one frame every n source frames
  - `-k/--keep [-1 = round(skip/2)]`: pick the sharpest of the last n
  - `-n/--max-frames`
  - `--start`, `--end`
  - `-q/--quality [95]`
  - `-r/--rotate`
  - `--no-autorotate`
  - `--scale`
  - `--lut <file|name|auto>`; built-ins include `insta360-ilog`
  - `--track` (default all tracks, written to `<out>/cam0`, `<out>/cam1`)
  - **`--sync`**: decode the tracks in lockstep so the frames of one stem form a
    rig frame
  - `--adaptive`
  - `--adaptive-range [4]`
  - `--blur-reject <px> [0 = off]`
  - `--similar <bits> [0]`
  - `--skipped-dir`
  - `--report <csv>`
  - `--threads`
  - `--decoder auto|builtin|ffmpeg`
  - `--ffmpeg`
- 360 cameras (GoPro `.360`):
  - `--360 faces|equirect|off`
  - `--360-size`
  - `--360-orient y,p,r`
- Masking (needs `--model`):
  - `--model`
  - `--detector [gdino-*]`
  - `--detector-threshold [0.3]`
  - `--text "a; b"`
  - `--neg-text`
  - `--mask-mode video|image`
  - `--mask-keep background|subject`
  - `--mask-out`
  - `--detect-every [1]`
  - `--memory-frames`
  - `--max-size`
  - `--threshold [0.5]`
  - `--nms [0.1]`
  - `--dilate-ratio`
  - `--overlay`

Model IDs that appear in the source and the binary:
- SAM: `sam2.1-tiny`, `sam2.1-small`, `sam2.1-base-plus` (the GUI default),
  `sam2.1-large`, `sam3`
- Detectors: `gdino-tiny`, `gdino-base` (the GUI default)
- Subject masking without a prompt: `birefnet`, `birefnet-lite`

`README.md` says that on the CLI, "point `--model` at a file you downloaded
yourself". Whether `sam extract --model sam2.1-base-plus` fetches the model by ID
is **unconfirmed**. A license gate on the model name hints that it does.

### 2.4 `spirula geometry`: depth and normals
Sources: `src/app/cli/geometry_main.cpp`, `src/i18n/catalog/Geometry.h`,
`docs/datasets.md`.

```
spirula geometry <dataset> [--image-dir --model <id|file> --install <id> --max-size --num-tokens --refine-steps --depth
  --normal-format png|jpg --jpeg-quality --depth-units relative|mm --ray-depth auto|yes|no --split auto|yes|no
  --face-res output|source --overwrite --image-gamut --image-linear --image-exposure --check
  --worker-devices <uuid,...> --worker-memory-mb <n> --device]
```

- Model IDs:
  - `moge2-vits`, `moge2-vitb`, `moge2-vitl`, `moge3-vitl`
  - `metric3d-vit-small`, `metric3d-vit-large`, `metric3d-vit-giant2`
  - `marigold-v2`, which needs `--install marigold-v2`: about 45 GB streamed,
    11 GB kept
  - MoGe-2 is the default.
- **Normals are written by default. Depth only with `--depth`.**
- `--depth-units relative` is the default. The depth loss ignores overall scale.
- `--split auto` splits fisheyes into pinhole faces.
- Outputs go to `depths/` and `normals/` beside `images/`.
- Reuse is guarded by `.geometry-complete` markers. Use `--overwrite` to replace.

### 2.5 `spirula dense`: RoMa v2 dense seed cloud
Source: `docs/dense.md`, `src/app/cli/dense_main.cpp`.

```
spirula dense DATASET --checkpoint romav2.0.1.pt --preset {fast|balanced|high} [--source-workflow true] [--matching-space source]
  [--samples-per-reference n] [--min-overlap f] [--recon-dir --metashape-xml --metashape-psx --metashape-component]
  [--config f.json] [--write-config f.json] [--progress-dir --perf-dir]
```

- `spirula dense --help` lists every setting.
- The CLI **does not download weights**. Use the official
  `romav2.0.1.pt`, SHA-256 `1557dec0…28b7`, under the `roma` (DINOv3) license.
- Camera poses stay fixed.
- Fisheye images are split into upright cube faces for matching.
- Output is `dense/roma.ply`. Training picks it up automatically unless
  `--seed-pointcloud sparse` is set.
- SIGINT and SIGTERM are both handled here.
- RoMa is used **here, not in SfM**. SfM matching uses SIFT, ALIKED, LoMa,
  LightGlue or FlexGlue.

### 2.6 `spirula lidar` and `spirula e57`: laser scans
Sources: `src/app/cli/lidar_main.cpp`, `src/i18n/catalog/Lidar.h`,
`docs/notes/lidar-alignment.md`, `docs/datasets.md` "E57 laser scans".

```
spirula lidar <dataset> --cloud <scan.(e57|las|ply)> [--cloud …] [--mode auto|anchors|keep|refine] [--points <n>|all [500000]]
  [--track-cap [12]] [--no-depth] [--no-gap-points] [--anchors <file>] [--image-dir] [--mask-dir]
  [--scan-frames auto|shared|separate] [--flip-masks] [--overwrite] [--scanner-poses]
spirula lidar --extract <scan.e57> <dataset> [<subfolder>]
spirula lidar --render-anchors <scan>... <dataset>
spirula lidar --info <scan>
spirula e57 … [--info --no-depth --no-panoramas --no-pinhole --overwrite --points]
```

**What `lidar` does:**
1. Fits a Sim(3) (rotation, translation, scale) from SfM to scan using
   **anchors**. Anchors are images with known scan-frame poses: either the scan's
   own photos, or views rendered from where the scanner stood.
2. Refines with point-to-plane ICP.
3. Writes `sparse/0` in scan coordinates, with `gauge.txt` set to `metric 1`. The
   original model moves to `sparse_unaligned/`.
4. Seeds from scan points that carry image tracks.
5. Renders depth (16-bit mm) and normals from the scan through each lens.

### 2.7 `spirula partition`: large scenes
Source: `src/app/cli/partition_main.cpp`, `docs/notes/scene-partition.md`.

```
spirula partition split <dataset> [--parts n | --max-images n] [--method graph|viewgraph] [--ring 0.1]
  [--ring-min-points n] [--max-seeds n] [--source auto|tracks|projection|proximity] [-o partition.json]
spirula partition merge <partition.json> [--runs <dir>] [--part <k> <run|ply> ...] [-o merged.ply]
train each part: spirula train … --partition partition.json --partition-part k
```

### 2.8 `spirula mesh`
Source: `src/app/cli/mesh_main.cpp`, `src/i18n/catalog/Mesh.h`,
`src/mesh/Meshing.h`.

```
spirula mesh <run_dir|*.ckpt|splat.ply> [--data <dir> | --no-data] [--data-format] [--output <path>] [--device]
  [--format ply,obj,gltf,glb,stl (+glb+png|glb+jpg|glb+jpeg75)] [--color none,vertex,texture]
  [--texture-size] [--tex-gutter-px] [--chart-angle-deg] [--iso (0.5 with cameras, 0.2 without)]
  [--merge-factor] [--bisection-iters] [--max-cameras [-1]] [--max-grid-res [512]] [--grid-cell-factor [2]]
  [--num-threads] [--carve-k [1]] [--cull-unseen 0|1] [--merge-max-flip-deg] [--floater-min-faces]
  [--fill-hole-ratio] [--fill-hole-max-edges] [--degenerate-angle-deg] [--quality-iters] [--progress-dir] [--quiet]
```

- Default output is `--format ply --color vertex`.

### 2.9 `spirula marker`: metric scale and frame from tags
Source: `src/app/cli/marker_main.cpp`, `docs/notes/markers.md`.

```
spirula marker detect <dataset> [--family auto|tag36h10|tag36h11|aruco4x4_1000|…] [--decimate 1..8] [--threads]
spirula marker align  <dataset> --origin <id> --x-axis <id> --xy-plane <id> [--dist-x <metres>] [--splat in.ply --out out.ply]
spirula marker crop   <dataset> [--pad 0.10] [--z-min -0.05] [--z-max 1.00] [--roi-name marker_crop.json]
spirula marker auto   <dataset> --origin … --x-axis … --xy-plane … [...]
```

- Each marker needs at least 2 registered cameras.
- Markers whose mean reprojection error exceeds 4 px are rejected.
- `--dist-x 0` keeps the existing scale.

### 2.10 Other commands
- `spirula encode`: raw RGB on stdin to MP4, H.264 or H.265, or AV1 on the GPU.
  Options: `--codec --fps --quality --size --spherical --output --probe`. It is
  patent-gated.
- `spirula export-bg`: writes a 1024×512 SH skybox as WebP
  (`docs/notes/webp-export.md`).

### 2.11 MCP server
Source: `tools/gui_mcp.py`, `docs/notes/gui-automation.md`.

- It is a **Python stdio MCP server that drives the GUI**, not the CLI.
- It needs the GUI process running with `SS_GUI_AUTOMATION=1`. It talks to a
  loopback HTTP surface on port 7777, protected by a token written to
  `<config dir>/automation.json`.
- Tools: `gui_launch`, `gui_state`, `gui_tree`, `gui_click`, `gui_move`,
  `gui_drag`, `gui_scroll`, `gui_key`, `gui_text`, `gui_wait`, `gui_drop`,
  `gui_screenshot`.
- With `SS_GUI_OFFSCREEN=1` the window is invisible but still needs a display.
  The docs say to use Xvfb when there is none.
- **For our notebook, prefer the CLI.** The MCP server only helps for GUI-only
  flows (see §6).

### 2.12 VRAM and RAM forecasting
Source: `docs/notes/train-forecast.md`, `docs/notes/memory-forecast.md`,
`src/app/TrainerCore.cpp`.

- `train` forecasts the ETA and the VRAM peak while it runs, and logs a
  `vram_forecast_warn` line when the risk of running out of memory is medium or
  high.
- The progress lines print the step, percent, splat count, elapsed time and ETA.
- `SS_FORECAST_LOG=1` dumps the forecast state every 100 steps.
- With the viewer on, `GET /progress` on `viewer_port` returns progress.
- `sfm`, `dense` and `mesh` take `--progress-dir`, where a `memory.json` is
  written twice a second.
- **There is no pre-run "dry forecast" CLI flag** (unconfirmed that none exists).

---

## 3. Presets explained

### 3.1 Training presets
From `train_apply_preset` in `src/config/TrainConfig.h`. `3dgs` is the base and
changes nothing.

| Preset | What it changes |
|---|---|
| **`360-camera`**: "original distorted images captured by 360 cameras" | `warp_to_pinhole 1`, `mask_boundary_offset -0.005`, `erank_reg 0.01` (10× the default), `long_axis_split_opacity_k 0.5 0.55 15000`. A `primitive mip` line is commented out. |
| `in-the-wild` | `center_method focus`, `outlier_threshold 10`, depths and normals on, `mask_boundary_offset -0.005`, `floater_suppression strong`, `noise_lr 20→0.2`, `erank_reg 0.1`, lower `means_lr`, `long_axis_split… 30000` |
| `centered-object` | `cap_max 200k`, `apply_loss_for_mask 1`, `center_method focus`, `background_mode sh`, depth and RGB distortion 0.01, `erank_reg 0.05` |
| `hdr` | linear ACEScg splats from Rec.709 images, `ppisp_exposure_from_exif 1`, random background with matched luminance, `loss_saturation_threshold 0.98`, `dc_reg 0`, `max_screen_size 0.15`, `features_sh_lr 1e-4`, `ssim_lambda 0.1`, `noise_gate_peak_weight 0` |
| `synthetic` | bilateral grid, PPISP and calibration warp off |
| **`meshing`** | `primitive mip`, `sh_degree 0`, `dc_reg 10`, `overexposure_reg 10`, `background_mode noise`, `floater_suppression strong`, `normal_distortion_reg 0.01`, median-depth/normal terms 0.01, `normal_supervision_weight 0.01`, `erank_reg 0.01`, `erank_reg_s3 0.01` |
| `academic-baseline` | Hidden. Turns all extras off, for benchmarking. |

**How the earlier run's settings resolve:**

| Setting | Meaning | Alternatives |
|---|---|---|
| `"preset": "360-camera"` | **Splits each fisheye into five 90° pinhole faces**: front, ±x, ±y, each cropped to the lens's rays. Without it, the native fisheye camera model is used (K=1). | `3dgs` with `warp_to_pinhole 0` trains on native fisheye. The `meshing` preset, combined with `--warp-to-pinhole 1`, gives the geometry-focused run. |
| `warp_spherical_to_pinhole: true` | This is already the default. It **only applies to equirectangular panoramas**: six cube faces. **It does nothing for our dual-fisheye frames.** The fisheye switch is `warp_to_pinhole`, which the preset sets. | Set it to 0 to train directly on the equirect. |
| `distraction_robustness: "mild"` | Densification scoring that people walking through cannot dominate: `densify_loss_map_power 1`, `densify_score_power 1`, `ssim_lambda 0.1`. It does **not** mask anything. | `strong` uses robust edge-aware maps and median scoring; use it when transients remain unmasked. `off` is the default. Since 11.12 the GUI hides it under advanced. |
| `quality: "high"` | `cap_max` 3M and **`num_iterations` 50k**, unless set explicitly. | `ultra` is 10M and 80k. |
| `num_iterations: 30000` | **Explicit, so it overrode high's 50k.** The run got a 3M budget but only 30k steps. Densify stops at `refine_stop_iter` 14000 either way. | 50k (high's intent), or longer with resume across sessions. |
| `cap_max: 3000000` | The same as high's value, so it changes nothing. | Raise it per partition part rather than globally. |
| `mask_dir: "combined_masks"` | Not a Spirula name; the default is `masks`. It is presumably our border mask combined with SAM masks. `sam mask` *intersects* with existing masks unless `--replace` is given. The GUI likewise combines the frame stencil with found masks in place. | Keep one canonical folder. White means keep. With `apply_loss_for_mask` unset, the masked pixels are ignored in the loss. |
| `load_depths / load_normals: true` | Both are defaults. **But `depth_supervision_weight` defaults to 0, so depth maps were loaded and *not used*.** Normals were used, because `normal_supervision_weight` defaults to 0.01. | Set `--depth-supervision-weight 0.05` (the GUI's "Use dataset depth maps" value) for LiDAR-rendered metric depth. Keep it at 0 or A/B test it for monocular depth. |
| `primitive: "3dgs"` | Default, and the most compatible with viewers. | `mip` reduces aliasing across distances and is what the meshing preset uses. `3dgut` gives "more accurate wide/distorted lenses and cleaner mesh geometry", but with pinhole faces this matters less (unconfirmed). |
| `sb_lobes: 0` | Default; view-dependent colour is SH degree 3. | `2` is the published setting and replaces SH. It matched or beat SH3 PSNR on 4 scenes, with about 0.3× the kernel time and 0.63× the splat VRAM (`docs/notes/spherical-beta.md`). Vulkan only. Readable by gsplat and PlayCanvas; other viewers show base colour. |

### 3.2 GUI dataset presets
From `src/app/gui/DatasetPreset.cpp`. These are **not reachable from the CLI**;
reproduce them by hand. The `360-camera` dataset preset sets:
- SfM `camera_model thin-prism-fisheye`
- Masking enabled, with prompt
  `"tourist; visitor; pedestrian; photographer; child; person; hand; backpack; selfie stick; shadow of person"`
- Negative prompt `"painting; statue; poster"`, which suits a historic lodge with
  portraits and carvings.
- Feature-only mask prompt `"sky; cloud; water; wave"` (written to
  `feature_masks/`, read only by SfM)
- Fisheye border masking on

GUI defaults (`src/app/gui/DatasetPrep.h`, `DatasetPreset.h`):
- `video_fps 2`
- `sharp_window 3`
- `blur_px 8`
- `similar_bits 0`
- mask model `sam2.1-base-plus` with `gdino-base`

---

## 4. Recommended settings for our capture, by stage

The policy throughout is that **scale stays unknown unless LiDAR, markers or a
measured distance constrains it**. Record `sparse/0/gauge.txt` (`metric 0|1`) in
our run manifest.

### 4.1 Frames
Run once per `.insv` clip:

```
spirula sam extract CLIP.insv -o DS/images/<clip> --sync --skip 15 --adaptive --blur-reject 8 --similar 4 --report DS/reports/<clip>_frames.csv
```

- **`--sync`** is mandatory for a rig. Without it, each track picks its own
  sharpest frame. Rig calibration then sees only 55–80% agreeing frames and may
  be declined (`src/sfm/README.md` "Rigs").
- Output goes to `DS/images/<clip>/cam0` and `/cam1`.
- `--skip 15` at 29.97 fps is about 2 fps, the GUI default. `--adaptive` keeps
  the average but adds frames while walking and removes them while turning on the
  spot. The sphere model makes rotation free (`docs/datasets.md` "Adaptive
  spacing").
- `--blur-reject 8` is the GUI default threshold. `--similar 4` is our choice
  (the default 0 is off), to drop standstill duplicates.
- The decoder: `auto` uses in-process NVIDIA Vulkan video decode and falls back
  to ffmpeg. Install ffmpeg as a backstop.
- Do not use a LUT unless the clip was shot in I-Log. If it was, use
  `--lut insta360-ilog`.
- Frame stems carry the source frame index. SfM uses it to time-align IMU data.

### 4.2 Masks
Order: border first, then people, then a separate sky feature mask.

1. Fisheye border:
   `spirula sam mask DS/images --out DS/masks` (defaults `--shrink 0.01`,
   `--samples 24`). Check one frame with `--preview DS/reports/border.png`.
   Per-camera border shapes are supported (`docs/notes/frame-stencil.md`
   "Per camera").
2. Moving people, intersected into the same folder. Use `sam track` on each
   extracted frame folder, or the masking options of `sam extract`:
   `--model <sam2.1-base-plus file> --detector gdino-base --text "tourist; visitor; pedestrian; photographer; person; hand; selfie stick; shadow of person" --neg-text "painting; statue; poster" --mask-mode video`
   plus `--accept-license sam2,gdino=yes`.
   - `sam mask` intersects with existing masks unless `--replace` is given, so the
     two stack.
   - The exact folder layout `track` writes for `cam0`/`cam1` subfolders, and the
     ordering against `sam mask`, are unconfirmed. Test on one clip.
3. Feature-only sky mask, so sky does not produce drifting SfM features while
   training still learns the sky: `--text "sky; cloud"` into `DS/feature_masks`.
   Pass it to SfM as `--feature-masks`.
- Training: keep `mask_dir masks` and leave `apply_loss_for_mask` unset, which
  means masked pixels are ignored. The `360-camera` preset's
  `mask_boundary_offset -0.005` trims halos.

### 4.3 SfM

```
spirula sfm auto DS/images -o DS --masks DS/masks --feature-masks DS/feature_masks \
  --data-type video --quality high --camera-model thin-prism-fisheye --camera-mode folder \
  --rig 'dual-fisheye=*:cam0,cam1' --sequence <clip prefixes> \
  --manifest DS/capture.yaml   # captures: [{prefix: <clip>, telemetry: <clip>.insv}]
  --sensor-gauge up --metric-gps none
```

- **Rig.** `dual-fisheye=` makes the second lens a 180° turn with its baseline
  held along the optical axis (`refine: axial`), used from the seed pair onward.
  Insta360 X lenses measured within 0.8–1.4° of this. The combined spelling
  `dual-fisheye=*:cam0,cam1` (kind plus capture wildcard) is **unconfirmed**. The
  fallback is a manifest `rigs:` entry with `kind: dual-fisheye`.
- **Camera model.** `thin-prism-fisheye` is what both the dataset preset and the
  COLMAP `.insv` path use. The legacy COLMAP path used focal factor 0.269×width
  for the X5 (`src/app/README.md`). `--camera-mode folder` gives each lens its
  own intrinsics. `opencv-fisheye` is the alternative to A/B test.
- **Pairs.** Above 100 images, `auto` switches to prefilter plus loop closure.
  `--rig-pairs` (on) extends verified pairs to the other lens.
- **Matcher.** Try SIFT bruteforce first. For repetitive stone and low texture,
  A/B `--features aliked-n16rot --matcher lightglue`, or `--matcher flexglue`
  (11.12; needs `--accept-license flexglue=yes`).
- **Mapper.** Use `flat` (the default). Try `--mapper global` if `flat` breaks
  into pieces.
- **Scale policy.** `.insv` IMU telemetry is used **by default** to set metric
  scale, as was the GPS when present (`src/sfm/README.md`, 9.13 notes). To keep
  "unknown stays unknown":
  - Use `--sensor-gauge up` (orientation only) and `--metric-gps none`.
  - Keep `--sensor-verify` and `--sensor-map` on for gyro-aided robustness.
  - Whether `--sensor-map` still injects accelerometer-scale factors into BA when
    `--sensor-gauge up` is set is **unconfirmed**. If strictness matters, A/B it
    against `--sensor-gauge none`, or against dropping telemetry.
  - Any IMU scale it prints is a diagnostic, never a deliverable.
- **Resume.** `auto` reuses finished features and matches by default
  (`--resume`, `--reuse-features`, `--reuse-matches`). Persist
  `DS/features`, `DS/matches.bin` and `DS/sparse` to HF between sessions.

### 4.4 Depth and normal priors
- Monocular normals:
  `spirula geometry DS --model moge2-vitl --split auto`. MoGe-3 (`moge3-vitl`) is
  an option to test. Normals feed `normal_supervision_weight` (default 0.01),
  which helps flat stone walls stay flat.
- Monocular depth: add `--depth` (relative units). Keep
  `depth_supervision_weight 0` by default. A/B 0.05 on interiors, since
  "a heavily biased prediction can pull quality down".
- Where LiDAR covers an area, `spirula lidar` renders **metric mm depth** and
  normals in place of the monocular step. Then set
  `--depth-supervision-weight 0.05`. `depth_unit_scale_factor 0.001` matches mm
  depth. `input_depth_is_ray_depth` is auto.
- How partial LiDAR depth maps mix with monocular maps for frames the scan does
  not cover is **unconfirmed**.

### 4.5 LiDAR (SiteScape PLY)
- Alignment needs **anchors**: images with known scan-frame poses. They come from
  E57 photos, or from views rendered at scanner positions. Positions come from E57
  stations, a PLY `camera` element, or a `<name>.trajectory.las`.
- **A SiteScape PLY probably has no photos and no scanner element**
  (**unconfirmed**). Without anchors, "a model with no anchor is lost", and ICP
  from nothing does not converge.
- ICP converges from about 5° / 10% scale / 10% of scene size
  (`docs/notes/lidar-alignment.md`).
- Plan:
  1. Pick at least 3 correspondences between the SfM model and the scan. Use
     features visible in both, or AprilTags.
  2. Compute an approximate Sim3 and apply it to the COLMAP model (pycolmap).
  3. Run `spirula lidar DS --cloud scan.ply --mode refine --scan-frames separate`.
- Scale is then metric (`gauge.txt` `metric 1`).
- Multiple partial scans in their own frames can only be placed through their
  images. Pre-register them together, or align one at a time.
- Validate with the printed median distance to the surface.
- LiDAR support is "experimental".

### 4.6 Scale without LiDAR
- Two-point distances are GUI-only in 10.30 (unconfirmed for CLI).
- On the CLI: `spirula marker detect DS --family auto`, then
  `spirula marker align DS --origin A --x-axis B --xy-plane C --dist-x <measured m>`.
  This needs printed tags placed at capture time.
- Whether marker detection handles fisheye frames correctly is **unconfirmed**.

### 4.7 Training
Photoreal run:

```
spirula train 360-camera --data DS --quality high --num-iterations 50000 \
  --distraction-robustness mild --floater-suppression mild \
  --eval-mode interval --eval-interval 8 \
  --disable-viewer 1 --keep-viewer-alive 0 --steps-per-save 2000 --save-only-latest-checkpoint 1 \
  --cache-images disk --scene-center none  # if the dataset frame is metric and must be preserved
  [--depth-supervision-weight 0.05  # only with LiDAR depths]
```

- **Exposure, indoor and outdoor.** Keep the defaults `use_bilateral_grid 1`,
  `bilagrid_type ppisp` and `use_ppisp 1`. A/B `--ppisp-exposure-from-exif 1`:
  - Extraction writes the Insta360 trailer's shutter and ISO per frame into EXIF.
  - Aperture is not logged, so comparisons happen only within a folder
    (`docs/datasets.md` "The exposure each frame records").
- **Rolling shutter.** `calib_correction basic` is the default. A/B `accurate`
  (11.12).
- **Resolution.** Each lens is 3840². Five faces come out at about 1717 px each
  (`ceil(sqrt(W·H/K))`), so roughly 10 faces per rig frame. Watch the VRAM
  forecast. Options:
  - `--warp-face-fit per-face` uses 15–40% fewer pixels.
  - `--train-resolution-divisor 2`
  - `--progressive-resolution 1`
- **Lobes.** A/B `--sb-lobes 2` (cheaper, equal or better quality). Ship SH3 if
  viewer compatibility matters.
- **Measured geometry run.** A separate
  `spirula train meshing --data DS --warp-to-pinhole 1 --floater-suppression strong`
  (the preset's own floater setting).
- **Frames.** Training uses the dataset frame translated by `scene_center`
  (default `auto`) and scaled by `relative_scale` (unset means 1)
  (`docs/notes/pose-normalization.md`). Whether exports undo the `scene_center`
  shift is **unconfirmed**. Use `--scene-center none` for metric or registered
  datasets.

### 4.8 Partitioning
- `spirula partition split DS --max-images <n> -o DS/partition.json`. Ring 0.1
  and graph method are the defaults. Each part trains in its own session:
  `--partition DS/partition.json --partition-part k`.
- Then run `spirula partition merge DS/partition.json --part k RUN_k ... -o merged.ply`.
- Each splat goes to the part owning its position, with no feathering.
- Exposure seams between parts are not yet addressed.
- Pick `--max-images` so one part finishes within about 10 h.
- Whether "images" counts input frames or pinhole faces is **unconfirmed**.

### 4.9 Mesh

```
spirula mesh outputs/<meshing-run> --format ply,glb --color vertex,texture
```

- Keep the dataset, because camera-based occupancy and colours need it.
- Metric only if `gauge.txt` says `metric 1`.

### 4.10 Export
- Splats: `splat.ply` inside each `step-*.ckpt/`. It is standard 3DGS PLY; with
  lobes, extra fields as described in `docs/notes/spherical-beta.md`.
- Meshes: `ply`, `obj`, `gltf`, `glb`, `stl`.
- Skybox: `background.webp`.
- No SPZ, SOG or compressed export was found in the CLI. Convert outside.

---

## 5. Headless on molab with checkpoint/resume to Hugging Face

1. **Bootstrap each session.**
   - Download the pinned release zip into scratch and `chmod +x` the binary.
   - Ensure `libvulkan1`, `libopengl0`, `libgomp1` and `ffmpeg` are installed.
   - Verify the GPU with `spirula sam devices`.
   - Check glibc is 2.38 or newer (`ldd --version`).
   - Set `XDG_CACHE_HOME` and `XDG_CONFIG_HOME` to scratch. Re-fetch models from
     HF (our own mirror of the weights, within license terms) and pass
     `--accept-license …=yes`.
2. **Run each stage as a subprocess** with stdout streamed to a log file, which
   works because output is line-buffered. Parse the progress lines.
   - Check exit codes. For `sfm auto`, 2 and 3 mean no or partial
     reconstruction.
3. **Training must never hang.**
   - Use `--disable-viewer 1`. The default `keep_viewer_alive 1` blocks forever
     after training (`main.cpp`). Issue #329 also found idle viewer sockets
     blocking exit, fixed in 3308142.
4. **Checkpoints.**
   - The default `steps_per_save 2000` with `save_only_latest_checkpoint 1`
     writes a resumable `outputs/<run>/step-NNNNNNNNN.ckpt/` (`state.tar` plus
     `splat.ply`) next to `config.json`.
   - The size is about 330 MB per 1M-splat cap, so **about 1 GB at 3M**.
   - molab does not keep files over 1 GB, so upload each new checkpoint to the HF
     bucket as soon as it appears. Files are renamed from `.tmp` once complete,
     so upload only the final names.
5. **Graceful stop before shutdown.**
   - Send **SIGINT** (`proc.send_signal(signal.SIGINT)`). The trainer finishes
     the step, writes a resumable checkpoint and exits with 130.
   - SIGTERM is unhandled and loses work. Schedule the stop at about 11.5 h, and
     keep the notebook active so the 90 min idle shutdown does not trigger.
6. **Resume.**
   - Download the run folder from HF, keeping the dataset at the same path that
     `config.json` records. Or pass `--data` again; that it overrides the stored
     path is unconfirmed.
   - Run `spirula train --resume outputs/<run>` or
     `--resume outputs/<run>/step-…ckpt`. The CLI still controls run length, save
     cadence and viewer settings.
   - `--finish-command` is not carried over; give it again.
7. **SfM, geometry and dense resume themselves.**
   - SfM reuses workspace files.
   - Geometry reuses maps with matching `.geometry-complete` markers.
   - `lidar` skips work when inputs are unchanged.
   - Persist these folders: `features/`, `matches.bin`, `sparse*/`, `depths/`,
     `normals/`, `dense/`, `masks/`.
8. **Record provenance in each run manifest:** binary version and SHA-256, full
   command lines, `config.json`, `gauge.txt` and `lidar_alignment.json`.

---

## 6. Unknowns to test

1. molab's glibc and libstdc++ versions, and whether the NVIDIA Vulkan ICD is
   present. If not, build from source with `-DSS_BUILD_GUI=OFF`, or the CUDA
   backend, which lacks SfM and masking.
2. Whether in-process video decode works on molab's NVIDIA driver for our `.insv`
   codec. We were told H.264; issue #118 reports X5 files as HEVC. Otherwise fall
   back to ffmpeg.
3. The exact `--rig` spelling that combines `dual-fisheye=` with a capture
   wildcard, and the manifest `rigs:` / `captures:` schema details.
4. Whether `--sensor-gauge up` keeps metric-scale factors out of BA entirely.
5. Whether the CLI resolves SAM and gdino model IDs to downloads, or needs file
   paths.
6. The output layout of `sam track` and masking for `cam0`/`cam1` subfolders, and
   whether border and person masks combine correctly.
7. Whether SiteScape PLYs carry a `camera` element. The manual pre-alignment plus
   `--mode refine` path, and ICP behaviour on noisy, partial phone LiDAR.
8. How LiDAR-rendered depth and monocular depth combine when a scan covers only
   part of the scene.
9. Whether `marker detect` works on fisheye frames, and whether two-point
   distance scaling exists outside the GUI.
10. Whether exported `splat.ply` and meshes are in the dataset frame or shifted by
    `scene_center`.
11. Whether partition `--max-images` counts input images or pinhole faces, and
    how long a part takes on molab's GPU.
12. Quality A/B tests:
    - SIFT vs ALIKED+LightGlue vs FlexGlue
    - `flat` vs `global` mapper
    - `sb_lobes 2` vs SH3
    - `ppisp_exposure_from_exif`
    - `calib_correction accurate`
    - `distraction_robustness mild` vs `strong`
    - `depth_supervision_weight`
    - Use the held-out metrics from `--eval-mode interval`.
13. The Intel-Mac source build: macOS x86_64 with MoltenVK on a Radeon Pro 580X.
