# Spirula local runs: what the files show (2026-11-12)

Evidence-only review of the four Spirula run folders under `frasier/cliff-house/runs/spirula/`, plus `results/clip_032_cuda/` and `datasets/clip_032_dataset/` in this repository. Every number below was read from a log, CSV, `.resume/*.sig`, `config.json`, or recomputed from the run's own files: sparse models with `pycolmap`, mask percentages averaged from the per-frame `kept` lines, and PSNR windows averaged from `train.log` step lines. Anything the files do not contain is marked **not recorded**. No source file was modified.

Paths are relative to the data root (`frasier/cliff-house/`) or to this repository.

## 0. What is not in the files

- **Spirula version: not recorded.** No log, sig, config or scene transform prints a Spirula version. The only version fields are `scene_transform.json` `"version": 1`, which is the file format, and the Swift toolchain (6.4) used for the extraction scripts. Model weights load from a `spirula-studio` model cache, so the GUI/Studio build was installed. Before reproducing on molab, record `spirula --version` (or the equivalent) on both machines.
- **Exact CLI command lines: not recorded.** The logs echo flag names when presets change them, for example `--max-image-size`, `--pairs`, `--init-min-tri-angle`, `--aliked-max-features`, `--loma-max-features`, `--ratio`, `--no-loop-closure`, `--no-rig-pairs` and `--metric-gps auto`. The `.resume/extract.sig` and `.resume/match.sig` files record the complete effective SfM option set as `key=value`, and `config.json` records the complete training option set. The subcommand name `spirula sfm` appears in the headers of `rigs.txt` and `gauge.txt`. The subcommand names for training, masking and extraction are inferred from log file names.
- **LPIPS: not recorded.** `eval_lpips` is `true`, but no eval or LPIPS line appears in any train log, and `save_eval_images` is `false`. The PSNR and SSIM values below are **per-step training-batch metrics** printed every 100 steps. They are not held-out metrics, and they are not geometric accuracy.
- **VRAM: not recorded.** Only the device total appears: M3 Max with 128 GiB unified memory; RTX PRO 6000 Blackwell with 97,251 MB.

## 1. Per-run settings and results

### 1.1 Input, extraction and masking

| | `clip_032_native` | `clip_041_20261110` | `pttfffffthrt_run` | `pttfffffthrt_review` |
|---|---|---|---|---|
| Date (file mtimes) | 2026-11-11 00:14–00:17 | 2026-11-10 21:29 → 11-11 01:52 | 2026-11-11 02:33–02:46 | 2026-11-11 02:33 |
| Source | `VID_20261109_174428_032.insv`. Run from an MP4 alias `source.mp4`: 2 × H.264 3840×3840, 30000/1001 fps, 269 frames per lens, 8.98 s | `VID_20261110_132328_041.insv`, read directly | edited `pttfffffthrt.mp4`, a single perspective stream 3839×2160 (odd width) | same MP4 |
| Scene (from PROGRESS.md) | short, mostly stationary courtyard view | cottage interior | grounds/courtyard/lodge sequence | contact sheet only |
| Extractor | `extract.swift`, AVFoundation `AVAssetReader` on both tracks, every 10th frame, JPEG q 0.95. **First attempt on the `.insv` failed:** `Fatal error: Expected two video tracks, found 0`. AVFoundation does not see INSV tracks; the MP4 rename worked. | Spirula's own extractor (`extraction.log`): "frames decoded 360, frames measured 180, frames written 60", sharpness pass 2.49 s, total 6.7 s | `extract.swift`: `AVAssetImageGenerator`, t = 0.1 + i/3 s (3 fps), 58 frames, max 3840×2160. Re-run as `extract_precise.swift` with `requestedTimeTolerance = .zero` | `inspect.swift`: 8 frames at 2.4 s spacing, 1280×720 max, plus a `sequence-review.jpg` |
| Frame rate actually sampled | every 10th frame, about 3.0 fps per lens | sharpness-selected. Indices 11…354, mean spacing 11.8 frames (about 2.5 fps). `extraction.csv` has `edge_width_px` and `blur_px` = −1 for every row, so per-frame sharpness scores were **not recorded** | 3 fps | n/a |
| Lenses/streams | both (cam0, cam1) | both (cam0, cam1) | one | one |
| Images | 27 + 27 = 54, 3840×3840 | 30 + 30 = 60, 3840×3840 | 58, 3839×2160 | 8 |
| Duplicate frames | none checked | none checked | **Non-precise extraction: only 47 unique of 58 (11 duplicates by md5).** The precise extraction gave 58 unique. `sharpness.csv` (Laplacian variance at quarter resolution, 337–2267) shows the duplicates as repeated values | — |
| Border mask | `border.log`. cam0 ellipse (0.4898, 0.5264, r 0.4658) keeps **68.1 %**. cam1 ellipse (0.4986, 0.4947, r 0.4946) keeps **76.8 %**. 54 masks | `mask.log`. cam0 (0.4974, 0.4961, r 0.4933) and cam1 (0.4987, 0.4952, r 0.4933), both keep **76.4 %**. 60 masks in `masks/` | none (perspective) | — |
| Person mask | Grounding-DINO-tiny + SAM 2.1 hiera base+ f16 GGML. 27 + 27 masks. Mean kept: cam0 98.5 % (min 97.3), cam1 99.1 % (min 96.4). About 1.2 s/frame | **First cam0 attempt failed:** `sam2.1_hiera_small.pt has magic 0x04034b50; expected "sam3" or "sam2"`, because a raw PyTorch zip is not accepted and a converted `.ggml` is required. Retry with base+ f16 GGML. Mean kept: cam0 **91.9 %** (min 84.6), cam1 96.6 % (min 89.9). About 0.6 s/frame | `person_masks/` stopped at 55/58 (the log ends mid-run). `person_masks_precise/` 58/58, mean kept 98.6 % (min 75.7). 0.61 s/frame | — |
| Combined mask | `combined_masks/` 27 + 27 | `combined_masks/` 30 + 30 | person masks used directly | — |
| Mask effect at SfM | 54/54 matched. Keypoints dropped 40,983 (9.3 %). Per image, cam0 lost about 1,250 of 8,192 and cam1 about 300 | 60/60 matched. Dropped 68,513 (**13.9 %**) | 58/58 matched. Dropped 5,526 (1.2 %) | — |

The mask counts are the same in every folder (images = person = combined = features). Person-mask files are named `frame_00000.png…` and image files `00011.jpg…`. The two name sequences are paired by order, not by name.

### 1.2 SfM (`spirula sfm`)

Common effective options in every run (from `.resume/*.sig`): `features=sift`, `max-features=8192`, `octaves=4`, `peak-threshold=0.00666667`, `edge-threshold=10`, `max-orientations=2`, `matcher=bruteforce`, `ratio=0.8`, `cross-check=on`, `max-matches=32768`, `verify=on`, `min-inliers=15`, `max-error=3`, `loop-closure=on`, `camera-mode=folder`, `focal=0`, `exif-focal=on`, `image-gamut=Rec.709`, `point-color=srgb`. Every log shows the `high` quality preset setting `--max-image-size 2400` (was 0), `--aliked-max-features 4096`, `--loma-max-features 4096` and `--init-min-tri-angle 8` (was 16). Video input also gets `--pairs sequential` (was auto).

| | `clip_032_native` | `clip_041_20261110` | `pttfffffthrt_run` (SIFT) | `pttfffffthrt_run/reconstruction_loma` |
|---|---|---|---|---|
| Camera model | `opencv-fisheye`, one camera per folder | `opencv-fisheye`, one camera per folder | `opencv`, 1 camera | `opencv`, 1 camera |
| Rig | `rig dual-fisheye: cam0 = I, cam1 = diag(−1, 1, −1)` (180° about Y), `rig-pairs=on`, angle 30, min inliers 30 | same | none | none |
| Pairs / overlap | sequential, overlap 10 + loop closure: 430 + 529 = 959 | overlap 10: 490 + 741 → 1,231 | overlap 12: 618 + 505 → 1,123 | overlap 16: 792 + 113 → 905 |
| Telemetry | INSV gyro/accel 1000 Hz (reported as "Antigravity A1"). GPS 6 positions over 0 m. **Sensor priors not calibrated (0 pairs)**. IMU-to-lens: "camera did not turn enough" | gyro/accel 1000 Hz. GPS 8 positions over 12 m. **Gyro priors calibrated: cam0 1.19°, cam1 3.30°.** Gyro-held verification dropped **177 pairs "turning the wrong way"** and rejected 1,604 matches | `telemetry=none` | none |
| Focal search (px) | cam1 912.7 (FOV 170°), cam2 889.0 (174°) | cam1 1144.7 (135°), cam2 1116.4 (139°) | guessed 4607 → epipolar 1613 → 1609 | 4607 → 1496 → probe 2142 |
| Pairs kept / inliers | **959/959; 2,576,024 / 2,653,109 (97 %)** | 512/1,232; 49,214 / 140,703 (35 %) | 707/1,123; 84,778 / 149,752 (57 %) | 848/905; 375,649 / 550,048 (68 %) |
| Seeding | No seed passed until relaxed to "inliers 100, angle 8°, forward motion allowed". First seed collapsed to 0 points | first seed (56, 57): 952 pts, 29.5°, sideways | needed relax to 50 inliers / 4° | 20-attempt budget exhausted. Relaxed to 30 inliers / 2° |
| Components | 1 | 2 (50 + 10 images) | 2 (35 + 15) | 2 (24 + 12), 22 images never placed |
| Registered (main / all) | 54/54 | 50/60 (both models cover 60) | 35/58 (50 covered) | **24/58** (36 covered) |
| Points (main) | **1,127** | 14,685 (+ 1,738) | 11,363 (+ 5,337) | 18,912 (+ 10,831) |
| Mean reprojection (pycolmap) | 0.899 px. The Spirula summary printed "mean 1.536, median 0.074 px over **3 observations**", which is a broken statistic | 0.812 px (log 0.856 / median 0.673 over 30,420 obs) | 1.094 px (log 1.149) | 1.963 px (log 2.018) |
| Mean track length | 11.03 | 2.28 | 2.56 | 2.70 |
| Final intrinsics (pycolmap) | OPENCV_FISHEYE cam1 f = 925.2/918.5, cam2 956.6/950.2 | cam1 f = 1102.3/1100.2, cam2 1112.3/1110.2, small k1–k4 | f = 1234/1249 (model 0). **Model 1: fx 1304 vs fy 1662** | **Model 1: fx 1189 vs fy 1736**. Principal point moved 17.8 px |
| Rig solve | "Images placed by the rig: 52, of them on the rig's word alone: **19**". Many registrations show `PnP inliers 0/300+` for one lens of the frame pair | placed by rig 50, rig-only 14 | — | — |
| Gauge (`gauge.txt`) | oriented, `metric 0`, up = ground, scale none (levelled on ground plane, ×1.7456) | model 0: `metric 1`, up = sensors, **scale = IMU, sigma 0.0183** (accelerometer scale 0.2467 ± 1.83 %, gravity 9.77 m/s², 0.8° from up). Model 1: not metric (17.6 % uncertainty) | not metric (×0.0404) | not metric |
| Rig translation (`rigs.txt`) | cam1 tz −7.6e-5 (non-metric units) | cam1 tz −0.0795 in metric model 0. Model 1 −0.066 | — | — |
| Time | 1 min 04 s (matching 54 s) | 54 s | 51 s | **8 min 56 s** (matching 7 min 58 s). Downloaded `loma_matcher_B128.onnx` (48 MB) from GitHub at run time |
| Result line | `OK -- 100 %, 1.54 px` | `OK -- 83 %, 0.86 px` | `OK -- 60 %, 1.15 px` | `PARTIAL -- 41 %, 2.02 px` |

The LoMa run differs from the SIFT run only in these sig keys: `max-image-size=1600`, `features=loma-b128`, `matcher=loma-b128`, `ratio=1`, `overlap=16`.

### 1.3 Training

| | `clip_041 training/high-360` | `clip_041 repair/cleanup-pass-01` | `results/clip_032_cuda` (molab) |
|---|---|---|---|
| Data | `sparse/0` (50 images) | same, initialised from `repair/original-50000.ply` (2,998,361 splats) | `clip_032_dataset` (54 images, 1,127 seed points). Byte-identical to `runs/spirula/clip_032_native` images, masks and `sparse/0` |
| Device | Apple M3 Max | Apple M3 Max | NVIDIA RTX PRO 6000 Blackwell (97 GB) |
| Cameras after fisheye split | 50 → 250 (5 pinhole faces per fisheye, no back face) | 250 | 54 → 270 |
| `train_frame_scale` | 4.009 | 4.009 | **0.003415** |
| Iterations | 50,000 | 5,000 | 30,000 |
| Splats | 300 k start, cap 3,000,000 reached at step about 5,300 | 3 M throughout | 300 k (held about 2,000 steps; first refine killed 197,931), 3 M at step about 6,300 |
| Training PSNR / SSIM (mean of last 5 k steps) | **34.77 / 0.936** (0–5 k 23.5; 10–15 k 30.0; 20–25 k 32.9) | 32.06 over the last 1 k steps. Mean over the run 31.95 | **26.09 / 0.787** (0–5 k 19.0; 10–15 k 23.8; 20–25 k 25.1) |
| Final step line | psnr 34.52, ssim 0.946, rgb_loss 0.0164 | psnr 33.51, ssim 0.923 | psnr 25.75, ssim 0.849, rgb_loss 0.0401 |
| LPIPS / held-out | not recorded | not recorded | not recorded |
| Wall time | **3 h 41 min** (0.27 s/step) | 22 min 37 s | **1 h 24 min** (0.17 s/step; 0–10 k in 14 min, 10–30 k in 70 min at 3 M splats) |
| Output | `splat.ply` 744 MB + `state.tar` 9.4 MB | 744 MB | 713 MB |
| Config | full config in §2 | differs from high-360 only as listed in §2.13 | identical to high-360 except `data`, `output_dir_*` and `num_iterations` |

`scene_transform.json` is byte-identical across all three runs: identity, scale 1, `centering.mode = none`. It does not carry the `train_frame_scale`. Do not use it as the georegistration record.

## 2. Full training config, annotated (`results/clip_032_cuda/config.json`)

Values are verbatim. The notes describe what each key does as far as the run evidence shows. Where only the key name supports a meaning, the note says "(name)". The keys appear in file order within each group.

### 2.1 Run and I/O

| key | value | note |
|---|---|---|
| preset | `"360-camera"` | Studio preset that produced this config |
| data | `"/marimo/Cliff_house_run_032/dataset"` | molab path. The dataset folder holds `images/cam{0,1}`, `combined_masks/cam{0,1}` and `sparse/0` |
| resume | null | |
| output_dir_prefix / output_dir_name | `/marimo/Cliff_house_run_032/training` / `clip_032_cuda` | |
| num_iterations | 30000 | clip_041 used 50000 |
| steps_per_save | 2000 | |
| save_only_latest_checkpoint | true | the repair pass set false and kept the 2 k/4 k/5 k checkpoints |
| save_full_checkpoint | false | the checkpoint is `splat.ply` + `state.tar` |
| save_eval_images | false | so there are no eval renders to inspect |
| eval_lpips | true | no LPIPS appears in any log |
| lpips_checkpoints | null | |
| log_performance | false | turn on to get timing/VRAM (name) |
| viewer_port / disable_viewer / keep_viewer_alive | 7007 / false / true | The process keeps running after training ("Viewer still running -- press Ctrl-C"). In a notebook, set `keep_viewer_alive=false` or the cell never returns |

### 2.2 Dataset layout and masks

| key | value | note |
|---|---|---|
| data_format | null | auto-detected COLMAP layout |
| image_dir | `"images"` | |
| mask_dir | `"combined_masks"` | person ∪ fisheye-border masks |
| load_masks | true | |
| apply_loss_for_mask | false | (name) Masked pixels are not used as a supervised alpha target. Semantics unconfirmed |
| flip_mask | false | |
| mask_boundary_offset | -0.005 | (name) shrinks or grows the mask edge |
| depth_dir / normal_dir | `"depths"` / `"normals"` | **neither folder exists** in any dataset |
| load_depths / load_normals | true / true | no-ops here because the folders are absent |
| depth_unit_scale_factor | 0.001 | |
| colmap_recon_dir | `"sparse/0"` | only the main component is trained. clip_041 `sparse/1` (10 images) is unused |
| metashape_xml / _ply / _psx | null | |
| seed_pointcloud / init_ply | null / null | repair pass: `init_ply = repair/original-50000.ply` |
| init_ply_add_points | false | |
| partition / partition_part | null / -1 | |

### 2.3 Region of interest and resolution

| key | value | note |
|---|---|---|
| roi_region | `"off"` | |
| roi_outside_weight / roi_outside_opacity_decay / roi_splat_samples / roi_mask_pixels | 0.0001 / 1 / 4 / true | inactive while roi is off |
| train_resolution_divisor | 0 | 0 = auto (name) |
| downscale_rounding_mode | `"floor"` | |
| progressive_resolution | false | start / full-at / schedule = 4 / 0.3 / null, unused |
| progressive_splat_budget | true | Matches the logs: the splat count grows about 5 % per refine from 300 k to the cap |
| progressive_splat_budget_schedule | null | |

### 2.4 Evaluation split

| key | value | note |
|---|---|---|
| eval_mode | `"all"` | (name) all views also used for training. So logged PSNR is not held-out |
| eval_interval | 8 | |
| train_split_fraction | 0.9 | |
| validation_fraction | 0 | no validation set |

### 2.5 Fisheye handling and frame normalisation

| key | value | note |
|---|---|---|
| warp_to_pinhole | true | each fisheye is split into pinhole faces: 54 → 270 and 50 → 250 cameras, so 5 faces each |
| warp_spherical_to_pinhole | true | |
| warp_face_fit | `"uniform"` | |
| warp_back_face | false | the face behind the lens is skipped, giving 5 faces, not 6 |
| deblur_training_images | false | |
| exif_orientation | `"orient"` | |
| orientation_method / center_method | `"up"` / `"poses"` | |
| auto_scale_poses | true | Likely source of `train_frame_scale` (4.009 for clip_041, 0.003415 for clip_032) |
| outlier_threshold | Infinity | |
| scene_center / scene_center_threshold | `"auto"` / 20 | |
| relative_scale | null | |
| train_frame | `"points"` | the training frame is normalised from the sparse points |

### 2.6 Representation, background and initialisation

| key | value | note |
|---|---|---|
| primitive | `"3dgs"` | |
| sh_degree | 3 | |
| sb_lobes | 0 | spherical-basis lobes off |
| sh_degree_warmup_every | 0 | |
| background_mode / background_color | `"color"` / [0,0,0] | |
| background_sh_degree | 4 | |
| background_noise_warmup / _pre_warmup | 2000 / 0.25 | |
| background_match_luminance | false | |
| viewer_kernel_fraction | 0.3 | |
| scale_init / opacity_init / suppress_initial_scales | 0.35 / null / false | |
| random_init | `"auto"` | Starts at 300 k splats even though there are only 1,127 seed points (clip_032), so most are random. The first clip_032 refine killed 197,931 |
| random_init_fraction / _distribution / _center / _spread / _std | 0.1 / isotropic-gaussian / camera-median / median / 1 | |
| use_camera_optimizer | false | poses are frozen. Bad SfM poses are not corrected in training |

### 2.7 Densification and splat budget (MCMC-style relocation)

| key | value | note |
|---|---|---|
| quality | `"high"` | repair: `"medium"` |
| cap_max | 3000000 | reached in both runs, so this is the binding limit |
| distraction_robustness | `"mild"` | repair: `"strong"`. This is the transient/person-robust loss setting |
| min_init_fraction | 0.1 | |
| growth_factor | 1.05 | matches the log (+5 % per refine) |
| min_opacity | 0.005 | |
| dead_criterion | `"either"` | |
| refine_every / refine_start_iter | 100 / 500 | the first `num_dead` appears at step 601 in both logs |
| refine_stop_num_iter / refine_stop_iter | 2500 / 14000 | relocations (`num_dead`) still appear in the clip_041 log until step 47,401 |
| noise_lr / noise_lr_final / noise_gate_peak_weight | 160 / 1.6 / true | MCMC position noise |
| use_revised_densification | true | |
| densify_score_mode | `"mean"` | repair: `"median"` |
| densify_score_blend_world_grad | 0 | |
| densify_loss_map_mode | `"auto"` | repair: `"robust_edge_aware"` |
| densify_robust_edge_aware_quantile | 0.9 | repair: 0.75 |
| densify_nms_falloff | 0.5 | |
| densify_loss_map_normalize / _clip_quantile / _power | false / 1 / 1 | |
| densify_accum_mode | `"sum"` | |
| densify_score_power / _clip_quantile / densify_final_score_power | 1 / 1 / 1 | |
| densify_learned_score | false | |
| densify_oversize_split_fraction / _score_blend | 0.15 / 1 | |
| use_long_axis_split / long_axis_split_opacity_k | true / [0.5, 0.55, 15000] | |
| max_split_fraction | 0.1 | |
| split_weight_by_renders | false | |
| dead_after_epochs | 2 | |
| max_screen_size / _clip_hardness / _penalty | 0.3 / 1.5 / 1 | repair: 0.1 / 1.1 |
| max_world_size | Infinity | |

### 2.8 Photometric loss

| key | value | note |
|---|---|---|
| ssim_lambda | 0.1 | |
| perceptual_loss | `"ssim_blur_tolerant"` | |
| l1_weight / l2_weight | 1 / 0 | |
| l1_weight_y / l2_weight_y / l2_weight_u / l2_weight_v | 0 / 0 / 0 / 0 | |
| loss_scale_min_pixels / num_loss_scales | 1920 / 0 | |
| alpha_loss_weight / alpha_loss_weight_under | 0.5 / 0 | |
| loss_saturation_threshold | -1 | |
| loss_luminance_normalization | 0 | |
| view_sampling | `"uniform"` | |
| view_deficit_power / view_deficit_max_ratio | 0.5 / 8 | |

### 2.9 Geometry regularisers (all relevant to measured geometry)

| key | value | note |
|---|---|---|
| floater_suppression | `"off"` | repair: `"strong"` |
| depth_distortion_reg / normal_distortion_reg / rgb_distortion_reg | 0 / 0 / 0 | repair: depth 0.03, rgb 0.05 |
| distortion_reg_warmup | 6000 | |
| normal_reg_weight / normal_reg_warmup | 0.04 / 6000 | |
| alpha_reg_weight / alpha_reg_warmup | 0 / 12000 | |
| reg_warmup_length | 0 | |
| depth_supervision_weight | 0 | no depth priors were supplied |
| normal_supervision_weight | 0.01 | no normals folder, so effectively inactive |
| input_depth_is_ray_depth | null | |
| supervision_warmup | 0 | |
| mean_median_depth_weight, median_depth_normal_reg_weight, median_normal_supervision_weight, median_render_normal_reg_weight | 0, 0, 0, 0 | median_warmup 6000 |
| opacity_reg / scale_reg | 0.01 / 0.01 | |
| reg_rendered_only | true | |
| opacity_reg_decay_power / scale_reg_decay_power | 1 / 0.4 | |
| opacity_decay / scale_decay | 0 / 0 | |
| erank_reg / erank_reg_s3 | 0.01 / 0 | |
| scale_regularization_weight / max_gauss_ratio | 0 / 10 | |
| dc_reg / sh_reg | 0.001 / 0.025 | repair: sh_reg 0.1 |
| overexposure_reg / quat_norm_reg | 0 / 0.01 | |

### 2.10 Appearance compensation (bilateral grid + PPISP)

| key | value | note |
|---|---|---|
| use_bilateral_grid / bilagrid_type / bilagrid_shape | true / `"ppisp"` / [16,16,8] | per-image colour/exposure absorption |
| bilagrid_tv_loss_weight | 10 | |
| color_shift_reg_weight / color_shift_reg_ema_period | 0 / 750 | |
| use_bilateral_grid_for_geometry / bilagrid_shape_geometry / bilagrid_tv_loss_weight_geometry | true / [8,8,4] / 10 | |
| use_adagrad_bilagrid_optim | true | |
| use_ppisp / ppisp_param_type | true / `"no_crf_no_vig"` | exposure and colour, no response curve or vignette |
| ppisp_exposure_from_exif / ppisp_exposure_arithmetic_mean | false / true | |
| apply_ppisp_before_bilagrid / apply_ppisp_before_color_space | true / false | |
| use_adagrad_ppisp_optim | true | |
| ppisp_reg_exposure_mean / _color_mean / _vig_center / _vig_non_pos / _vig_channel_var / _crf_channel_var | 1 / 1 / 0.02 / 0.01 / 0.1 / 0.1 | |
| bilagrid_adagrad_lr / _depth_lr / _normal_lr | 0.04 / 0.04 / 0.01 | |
| ppisp_adagrad_lr | 0.1 | |
| bilagrid_lr → final, warmup | 0.002 → 0.0001, 1000 | |
| bilagrid_depth_lr → final, warmup | 0.002 → 0.0001, 2000 | |
| bilagrid_normal_lr → final, warmup | 0.0005 → 4e-05, 2000 | |
| ppisp_lr → final, warmup | 0.002 → 2e-05, 500 | |

### 2.11 Colour spaces

All of `image_color_is_linear`, `image_color_transfer`, `image_color_gamut`, `splat_color_*` and `point_color_*` are `null`, so they are auto. SfM used `image-gamut=Rec.709`, `image-linear=off` and `point-color=srgb`.

### 2.12 Performance and optimiser

| key | value | note |
|---|---|---|
| cache_images | `"disk"` | |
| max_batch_per_epoch / min_renders_per_refine / render_quantile | 800 / 0 / 0.1 | |
| max_train_batch_size / split_batch | -1 / true | |
| use_fused_proj_bwd_optim / packed | true / true | |
| quantization_level / bin_tile_size | 1 / 0 | |
| preallocate_splat_tensors | true | |
| optimizer_offload / use_bvh | null / false | |
| means_lr → final | 0.000256 → 3.2e-06 | |
| scales_lr → final | 0.02 → 0.005 | |
| quats_lr / opacities_lr | 0.0015 / 0.025 | |
| features_dc_lr / features_sh_lr / features_sb_lr | 0.005 / 0.00025 / 0.0025 | |
| background_dc_lr / background_sh_lr | 0.0025 / 0.0005 | |
| max_steps | null | |
| use_scale_agnostic_mean / use_per_splat_bias_correction | true / true | |

### 2.13 The only differences in the clip_041 "cleanup-pass-01" repair config

`num_iterations` 5000, `save_only_latest_checkpoint` false, `viewer_port` 7008, `init_ply` = the 50 k result, `quality` medium, `distraction_robustness` **strong**, `densify_score_mode` median, `densify_loss_map_mode` robust_edge_aware (quantile 0.75), `max_screen_size` 0.1 (hardness 1.1), `floater_suppression` **strong**, `depth_distortion_reg` 0.03, `rgb_distortion_reg` 0.05, `sh_reg` 0.1. Training PSNR fell from about 34.8 to about 32.1. That is expected when the clean-up removes floaters fitted to training views. Whether the repair looked better was **not recorded**.

## 3. Comparison and lessons

1. **Camera motion, not settings, decided SfM quality.** clip_032 and clip_041 used identical SfM options apart from paths and telemetry. clip_032 is a mostly stationary view: GPS 0 m, "camera did not turn enough", seeding only succeeded after relaxing to "forward motion allowed", and **97 % of matches passed verification**. Under near-pure rotation almost every match fits the verification model, so a 97 % pass rate is a warning sign. The run reported "100 % registered", but it triangulated only **1,127 points**, placed 19 images on the rig constraint alone with 0 PnP inliers, and printed a reprojection statistic over 3 observations. clip_041 moved: 12 m GPS track, camera extent about 3× the median point distance. It produced 14,685 points at 0.81 px with a 35 % inlier rate. **Treat the `RESULT: OK -- N %` line as a coverage count, not a quality verdict.** Check the point count, the "on the rig's word alone" count and the inlier ratio.
2. **Fisheye focal is a health check.** For a 3840-px image circle and roughly 200° lens, an equidistant focal of about 1,100 px is physically plausible. clip_041 converged to 1,100–1,112 px. clip_032 converged to 918–957 px, which implies more than 230° FOV. Its cam0 border ellipse was also off-centre (y 0.526, r 0.466, keeping 68 % vs 76 % elsewhere). **Reuse the clip_041 per-lens OPENCV_FISHEYE intrinsics as the prior or fixed calibration for every clip.** The previous engineer already did this for the COLMAP path (PROGRESS.md "calibration-041").
3. **Gyro priors help when there is motion.** clip_041 calibrated the gyro to the lenses (1.19° / 3.30°), rejected 177 pairs that turned the wrong way, and produced an **IMU-derived metric scale, 0.2467 ± 1.83 %** (`gauge.txt metric 1`). This is the only scale constraint in any run, and it is a candidate, not a survey value: it needs an independent check distance. The fitted lens offset of 7.95 cm (`rigs.txt` tz in the metric model) is one test of that scale against the physical camera.
4. **Masking is consistent and cheap, but the operator lives in cam0.** clip_041 cam0 masks 8 % of every frame for people (min 84.6 % kept) versus 3.4 % on cam1. Combined masks removed 9–14 % of SIFT keypoints. The border ellipse should be fixed per lens, using the clip_041 values, not re-estimated per clip.
5. **Frame extraction details matter.** AVFoundation cannot open `.insv` (0 tracks) without an MP4 rename. `AVAssetImageGenerator` without zero tolerance silently returned **11 duplicate frames out of 58**. Spirula's own extractor read the INSV directly with sharpness selection (~2.5 fps per lens), but it wrote −1 for every sharpness score.
6. **SIFT beat LoMa B128 here.** On the same 58 perspective frames: SIFT at 2400 px registered 35/58 at 1.09 px in 51 s. LoMa at 1600 px with ratio 1 registered 24/58 at 1.96 px in 8 min 56 s, and its sub-model search exhausted its budget. Both perspective solves let fx and fy drift apart (model 1 fx/fy 1304/1662 and 1189/1736), which is impossible for square pixels. The edited MP4 has an unknown reframing, so it is a poor SfM source compared with the native INSV.
7. **Training quality tracks SfM quality, not device.** clip_041 (14,685 seed points, good poses) reached a training PSNR of about 34.8 and SSIM 0.94 at 50 k. clip_032 on a far faster GPU (0.17 vs 0.27 s/step) plateaued at about 26.1 / 0.79 at 30 k. It started from 1,127 points, most of the 300 k random-init splats died at the first refine, and `train_frame_scale` was 0.0034 instead of about 4. `use_camera_optimizer=false` means training cannot repair weak poses. These are different scenes, so the comparison is indicative only, and neither number is held-out.
8. **The 3 M splat cap was hit by step 5–6 k in both runs**, and output PLYs are 0.71–0.74 GB. Capacity, not iterations, is the limit for these scenes.
9. **Unused evidence:** only `sparse/0` was trained, so clip_041's 10-image second component was dropped. No depth or normal priors were given, though the config loads them if present. No eval split was produced. LPIPS was requested and never logged.

## 4. Reproduce on molab (reconstructed from the logs)

The flag syntax below comes from the sig keys and the flags echoed in the logs. **The CLI invocation form is not recorded in any file. Verify every flag against `spirula <subcommand> --help` on molab before running.** Data comes from Hugging Face. All writes go to a new run folder.

```bash
# 0. Record versions first. The previous runs did not.
spirula --version; nvidia-smi --query-gpu=name,memory.total --format=csv

# 1. Frames. The Swift/AVFoundation scripts are macOS-only and failed on raw .insv.
#    On Linux, either use Spirula's own extractor (it read .insv directly for clip_041),
#    or split the lenses with ffmpeg and sample about 3 fps per lens:
ffmpeg -i VID_..._041.insv -map 0:v:0 -vf "select=not(mod(n\,10))" -vsync vfr -q:v 2 run/images/cam0/%05d.jpg
ffmpeg -i VID_..._041.insv -map 0:v:1 -vf "select=not(mod(n\,10))" -vsync vfr -q:v 2 run/images/cam1/%05d.jpg
#    Check that no frames are duplicated (md5) and that each lens has the same count.

# 2. Masks: fisheye border ellipse per lens (clip_041: centre about 0.497,0.496, r 0.4933 -> 76.4 % kept)
#    plus person masks from Grounding-DINO-tiny + SAM 2.1 hiera base+ in .ggml form
#    (a raw sam2.1_*.pt checkpoint is rejected). Union them into combined_masks/cam{0,1}.

# 3. SfM (effective options from clip_041 .resume/*.sig; quality preset "high")
spirula sfm --images run/images --output run --masks run/combined_masks \
  --features sift --max-features 8192 --max-image-size 2400 \
  --camera-mode folder --camera-model opencv-fisheye \
  --pairs sequential --overlap 10 --loop-closure on \
  --rig-pairs on --rig-pair-angle 30 --rig-pair-min-inliers 30 \
  --matcher bruteforce --ratio 0.8 --cross-check on --min-inliers 15 --max-error 3 \
  --telemetry VID_..._041.insv --sensor-verify on --init-min-tri-angle 8 --metric-gps auto
#    The rig is auto-detected as dual-fisheye: cam1 = 180 deg about Y.
#    Gate: inlier ratio well below 97 %, "on the rig's word alone" small,
#    points >> 1k, per-lens focal about 1100 px.

# 4. Train (config keys as in section 2; start from results/clip_032_cuda/config.json)
spirula train --preset 360-camera --data run --colmap-recon-dir sparse/0 \
  --mask-dir combined_masks --num-iterations 50000 --cap-max 3000000 \
  --keep-viewer-alive false --save-eval-images true --log-performance true
#    Optional clean-up pass: --init-ply <50k splat.ply> --num-iterations 5000 --quality medium \
#    --distraction-robustness strong --floater-suppression strong \
#    --depth-distortion-reg 0.03 --rgb-distortion-reg 0.05 --sh-reg 0.1 --max-screen-size 0.1
```

Settings to try first on molab, based on the evidence above. These are hypotheses to test, not results:

- Use moving clips only (035/037/038/040/041). clip_032 is too static.
- Fix or prior the intrinsics from clip_041.
- Train every SfM component, or merge them first.
- Set a real `validation_fraction` so PSNR and LPIPS are held-out.
- Consider `use_camera_optimizer`.
- Keep the IMU scale as a candidate until an independent tape or control distance confirms it.
