# Notebook cell harvest — 2026-11-12

Reusable cells from public notebooks and READMEs, to port into the Cliff House Marimo notebook. That notebook runs on molab: Linux x86_64 with an NVIDIA GPU. Packages come from a PEP 723 header, and pixi installs COLMAP, OpenMVS and ffmpeg. Pixeltable is the catalog, and Hugging Face stores the data.

## Rules for this harvest

- Code is copied only from repos licensed MIT, Apache-2.0 or BSD. The license was checked through the GitHub API (`repos/<r> .license.spdx_id`).
- Each code block is a contiguous excerpt copied verbatim from the cited cell or README section. Lines were trimmed only at the start or end of an excerpt. Where lines inside an excerpt were left out, the gap is marked `# [...]`. Nothing was rewritten.
- "Cell [n]" is the 0-based index into the notebook's `cells` array. Marimo `.py` files are cited by line range.
- All files were fetched on 2026-11-12 from the default branch at the commit SHA listed below.
- Copied code must keep its attribution. For Apache-2.0 sources, keep a NOTICE or header comment naming the source.

## Sources fetched

| Repo | License (API) | Commit | Files read | Status |
|---|---|---|---|---|
| nv-tlabs/3dgrut | Apache-2.0 | dfd3d54c8c61 | `threedgrut_playground/headless.ipynb`, `README.md` | OK |
| abolhoseinisina/Colab_COLMAP_3DGS | MIT | bcd6272ef203 | `Colab_COLMAP.ipynb`, `Colab_3DGS.ipynb` | OK |
| JittoJoseph/GaussianSplat-Colab | MIT | 41dfaf038426 | `Video_to_GaussianSplat_Colab.ipynb` | OK |
| nerfstudio-project/nerfstudio | Apache-2.0 | 50e0e3c70c77 | `colab/demo.ipynb` | OK |
| pixeltable/pixeltable | Apache-2.0 | f4b18e096cc1 | `docs/release/howto/cookbooks/video/video-extract-frames.ipynb`, `.../video/video-scene-detection.ipynb`, `.../images/img-promptable-segmentation.ipynb` | OK. Two of these are over 1 MB, so the contents API returned no body and they were fetched from raw.githubusercontent.com. |
| marimo-team/gallery-examples | MIT | 7572474a4df6 | `notebooks/external/dlthub-huggingface.py`, `notebooks/cad/trimesh-demo.py` | OK |
| meyerls/aruco-estimator | MIT | 2fde86aaddb6 | `README.md` | OK |
| maturk/dn-splatter | Apache-2.0 | 97588b429012 | `README.md` | OK |
| libishm1/Colmap_Photogrammetry_Drone_video | **NONE** (no LICENSE file; the README text claims CC BY-NC-SA 4.0) | 8b64485ec49a | `README.md` | Technique notes only. No code copied. |

Every requested path existed.

---

## Stage 1 — Frame extraction per lens, with sharpness and overlap selection

### C01 — Pixeltable video table and fixed-FPS frame view
- **Source:** https://github.com/pixeltable/pixeltable/blob/main/docs/release/howto/cookbooks/video/video-extract-frames.ipynb, cells [6], [7] and [10]. Apache-2.0.
- **Stage:** 1

```python
import pixeltable as pxt
from pixeltable.functions.video import frame_iterator

# Create a fresh directory
pxt.drop_dir('video_demo', force=True)
pxt.create_dir('video_demo')
# Create table for videos
videos = pxt.create_table('video_demo/videos', {'video': pxt.Video})
# Extract 1 frame per second
frames = pxt.create_view(
    'video_demo/frames',
    videos,
    iterator=frame_iterator(
        videos.video,
        fps=1.0,  # 1 frame per second
    ),
)
```

**Adaptation notes**
- `.insv` files hold two video streams, and `frame_iterator` reads the default stream. Before inserting, split each `.insv` into one file per lens with ffmpeg (`-map 0:v:0` and `-map 0:v:1`). Insert one row per lens with a `lens` column (`'front'` / `'back'`) so lens is a value in the data, not a second table.
- Remove the `drop_dir(..., force=True)` call. It deletes the catalog on every run. Create the directory only if it does not exist (`if_exists='ignore'`).
- Sharpness selection goes in a computed column on `frames`, such as a variance-of-Laplacian UDF. None of the harvested sources include one. See the gaps list.

### C02 — Keyframe-only extraction (cheap pre-pass)
- **Source:** same notebook, cell [13]. Apache-2.0.
- **Stage:** 1

```python
# Extract only keyframes (much faster for long videos)
keyframes = pxt.create_view(
    'video_demo/keyframes',
    videos,
    iterator=frame_iterator(videos.video, keyframes_only=True),
)
keyframes.select(keyframes.frame).head(3)
```

**Adaptation notes**
- Per the notebook's explanation cell, only one of `fps`, `num_frames` or `keyframes_only` can be set. Make the mode one value in a config dataclass rather than three flags.
- Insta360 I-frame spacing depends on the encoder. Check `pos` spacing on a real `.insv` before relying on keyframes for SfM overlap.

### C03 — Adaptive scene detection as a computed column
- **Source:** https://github.com/pixeltable/pixeltable/blob/main/docs/release/howto/cookbooks/video/video-scene-detection.ipynb, cell [13]. Apache-2.0.
- **Stage:** 1. Use it to segment a walkthrough into rooms or passes, and to drop segments where the camera is static or covered.

```python
# Adaptive detection adjusts to video content dynamically
videos.add_computed_column(
    scenes_adaptive=videos.video.scene_detect_adaptive(
        adaptive_threshold=3.0,  # Lower = more scenes detected
        min_scene_len=15,
        fps=2.0,  # Analyze at 2 FPS for speed
    )
)
```

**Adaptation notes**
- Needs `scenedetect` and `opencv-python` (from notebook cell [4]). Add both to the PEP 723 header.
- The output is a list of `{start_time, start_pts, duration}`, per the notebook's explanation cell. Join it against the frame `pts` in Polars to tag frames by segment.

### C04 — ffprobe a video and fail loudly on bad input
- **Source:** https://github.com/JittoJoseph/GaussianSplat-Colab/blob/main/Video_to_GaussianSplat_Colab.ipynb, cell [10], tail. MIT.
- **Stage:** 1

```python
probe = subprocess.run(
    "ffprobe -v error -select_streams v:0 -show_entries "
    f"stream=width,height:format=duration -of json '{VIDEO_PATH}'",
    shell=True, capture_output=True, text=True)
print(f"Video ready: {os.path.basename(VIDEO_PATH)} ({os.path.getsize(VIDEO_PATH) / 1e6:.1f} MB)")
try:
    info = json.loads(probe.stdout)
    stream = info["streams"][0]; dur = float(info["format"]["duration"])
    print(f"  {stream['width']}x{stream['height']}, {dur:.1f} s")
    if dur < 5:
        print("  Warning: very short (<5 s); reconstruction may be poor.")
except Exception:
    pass
```

**Adaptation notes**
- Remove `-select_streams v:0` and assert `len(info["streams"]) == 2` for `.insv`. Each lens gets its own row.
- Remove the `try/except: pass`. It hides parse failures, which breaks the project's no-silent-fallback rule. Use `check=True` and let a bad probe raise.
- Use `shell=False` with an argument list. The path then needs no quoting.

---

## Stage 2 — Camera poses (COLMAP, GLOMAP, pycolmap; OPENCV_FISHEYE)

### C05 — Headless COLMAP CLI sequence: features, matching, mapper, undistort
- **Source:** https://github.com/abolhoseinisina/Colab_COLMAP_3DGS/blob/main/Colab_COLMAP.ipynb, cells [13], [15], [17] and [19]. MIT.
- **Stage:** 2

```bash
!export QT_QPA_PLATFORM=offscreen
!colmap feature_extractor \
  --database_path /content/project/database.db \
  --image_path /content/project/images \
  --ImageReader.single_camera 0 \
  --FeatureExtraction.use_gpu 0
!colmap exhaustive_matcher \
  --database_path /content/project/database.db \
  --FeatureMatching.use_gpu 0
!mkdir -p /content/project/sparse
!colmap mapper \
  --database_path /content/project/database.db \
  --image_path /content/project/images \
  --output_path /content/project/sparse
!colmap image_undistorter \
    --image_path /content/project/images \
    --input_path /content/project/sparse/0 \
    --output_path /content/project/undistorted \
    --output_type COLMAP \
    --max_image_size 1600
```

**Adaptation notes**
- Replace each `!` with `subprocess.run([...], check=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})`. A `!export` in its own cell does not carry over to the next command. Use pixi's `colmap`, and set `use_gpu 1` on molab.
- For fisheye input, add `--ImageReader.camera_model OPENCV_FISHEYE` and lay out images as `images/front/*` and `images/back/*` with `--ImageReader.single_camera_per_folder 1`. The source cell does not do this; it is our adaptation. Use `sequential_matcher` for video, as in C06, instead of `exhaustive_matcher`.
- Keep the undistorted output for the PINHOLE-only consumers (aruco-estimator in C14, OpenMVS). 3DGUT (C08) should consume the distorted fisheye `sparse/0` directly.

### C06 — `ns-process-data video` with pose-count validation
- **Source:** https://github.com/JittoJoseph/GaussianSplat-Colab/blob/main/Video_to_GaussianSplat_Colab.ipynb, cell [12]. MIT.
- **Stage:** 2 (also extracts frames for stage 1)

```python
match = "sequential" if sfm_tool == "colmap" else "exhaustive"
gpu_flag = "--no-gpu" if sfm_tool == "colmap" else ""
cmd = (f"xvfb-run -a ns-process-data video --data '{VIDEO_PATH}' --output-dir '{DATA_DIR}' "
       f"--num-frames-target {target_frames} --sfm-tool {sfm_tool} "
       f"--matching-method {match} {gpu_flag}").strip()
# [...]
rc, tail = run_live(cmd, "/content/ns_process.log", stage_map=stage_map)
if rc != 0:
    print("\n--- log tail ---\n", tail)
    raise RuntimeError("SfM failed. Try sfm_tool='hloc', or recapture with more overlap.")

frames = json.load(open(os.path.join(DATA_DIR, "transforms.json"))).get("frames", []) \
    if os.path.isfile(os.path.join(DATA_DIR, "transforms.json")) else []
if not frames:
    raise RuntimeError("SfM produced no valid poses. See /content/ns_process.log")
images = len(glob.glob(os.path.join(DATA_DIR, "images", "*")))
print(f"\nRegistered {len(frames)} / {images} frames.")
```

**Adaptation notes**
- `ns-process-data` also accepts `--camera-type fisheye`. Use it, or better, feed it frames from C01 through `ns-process-data images` so Pixeltable remains the single source of frame selection.
- Keep the "registered / total" check. Store the result as a column (`registered: bool`) on the Pixeltable frames view rather than printing it.
- Replace the `/content/...` paths with a molab scratch root. Copy `sparse/` and `transforms.json` to the HF bucket after each run, because scratch is wiped at shutdown.

### C07 — Subprocess runner that streams output and raises with the log tail
- **Source:** https://github.com/JittoJoseph/GaussianSplat-Colab/blob/main/Video_to_GaussianSplat_Colab.ipynb, cell [6], function `run`. MIT.
- **Stage:** 2, 3 and 7. Every native-tool call.

```python
def run(cmd, desc=None, log_path=None):
    """Run a command, streaming a compact status line. Raises on failure."""
    if desc:
        print(f"-> {desc}")
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    tail, logf = [], open(log_path, "w") if log_path else None
    for line in proc.stdout:
        if logf:
            logf.write(line)
        tail.append(line.rstrip()); tail = tail[-400:]
        sys.stdout.write("\r   " + line.rstrip()[:100].ljust(102)); sys.stdout.flush()
    proc.wait()
    if logf:
        logf.close()
    sys.stdout.write("\r" + " " * 106 + "\r"); sys.stdout.flush()
    if proc.returncode != 0:
        print(f"   failed: {desc or cmd}")
        for l in tail[-25:]:
            print("   " + l)
        raise RuntimeError(f"Command failed (exit {proc.returncode}): {cmd}")
    print("   done")
    return "\n".join(tail)
```

**Adaptation notes**
- Marimo does not render `\r` progress lines well. Send lines to `mo.output.replace(...)` or use `mo.status.progress_bar`.
- Make `log_path` required and always write it, so the log tail is always available. Upload logs alongside outputs to the HF bucket.
- Take `cmd: list[str]` with `shell=False`.

---

## Stage 3 — Gaussian splat training (3DGUT for fisheye; gsplat or nerfstudio)

### C08 — 3DGUT training on a COLMAP dataset, plain and MCMC
- **Source:** https://github.com/nv-tlabs/3dgrut/blob/main/README.md, section "2. Train 3DGRT or 3DGUT scenes". Apache-2.0.
- **Stage:** 3

```bash
python train.py --config-name apps/colmap_3dgut.yaml path=data/mipnerf360/bonsai out_dir=runs experiment_name=bonsai_3dgut dataset.downsample_factor=2
python train.py --config-name apps/colmap_3dgut_mcmc.yaml path=data/mipnerf360/bonsai out_dir=runs experiment_name=bonsai_3dgut dataset.downsample_factor=2
python train.py --config-name apps/colmap_3dgut.yaml path=data/mipnerf360/bonsai out_dir=runs experiment_name=bonsai_3dgut dataset.downsample_factor=2 optimizer.type=selective_adam
python train.py --config-name apps/colmap_3dgut.yaml path=data/mipnerf360/garden/ out_dir=runs experiment_name=garden_3dgut dataset.downsample_factor=2 export_usd.enabled=true
```

**Adaptation notes**
- `path=` points at the distorted COLMAP model from C05, with the OPENCV_FISHEYE cameras. 3DGUT handles distorted cameras natively, so do not undistort. The README lists "datasets with multiple sensors (only for COLMAP-style datasets)" (2025/07), which fits a two-lens rig.
- Run with `subprocess` and C07 from a 3dgrut checkout. Its installer is `install_env_uv.sh`, which needs uv and a CUDA toolkit. Pin this in the pixi environment, not the PEP 723 header.
- The README says gsplat also supports 3DGUT. Prefer gsplat if it keeps one trainer for both stage 3 and stage 5.

### C09 — 3DGRUT headless engine render of a checkpoint (QA thumbnails)
- **Source:** https://github.com/nv-tlabs/3dgrut/blob/main/threedgrut_playground/headless.ipynb, cells [4], [12], [17] and [18]. Apache-2.0.
- **Stage:** 3 (training QA) and 7 (preview renders)

```python
gs_object = "3dgrut/runs/<YOUR_MODEL_HERE>/ckpt_last.pt"
mesh_assets_folder = "./assets"
default_config = "apps/colmap_3dgrt.yaml"
engine = Engine3DGRUT(
    gs_object=gs_object,
    mesh_assets_folder=mesh_assets_folder,
    default_config=default_config
)
camera = kaolin.render.easy_render.default_camera(512).cuda()
camera.move_forward(-1.5)
camera.move_up(1.5)
camera.rotate(yaw=1.0, pitch=0.5, roll=2.5)
# Render a full quality frame
framebuffer = engine.render(camera)
rgba_buffer = torch.cat([framebuffer['rgb'], framebuffer['opacity']], dim=-1)

# Display
chw_buffer = rgba_buffer[0].permute(2, 0, 1)
img = F.to_pil_image(chw_buffer)
```

**Adaptation notes**
- Return `img` as the cell output, or `mo.image(img)`, instead of `plt.show()`. Leave out the ipywidgets and IpyTurntableVisualizer cells; use `mo.ui.slider` for yaw and pitch.
- Needs `kaolin` and the 3dgrut repo on `sys.path` (cell [8]). The playground engine uses OptiX, so confirm the molab GPU driver supports it before relying on this cell.
- Store renders as a Pixeltable `pxt.Image` computed column keyed by checkpoint, so QA images are versioned with the run.

### C10 — splatfacto / splatfacto-mcmc command builder with an OOM retry
- **Source:** https://github.com/JittoJoseph/GaussianSplat-Colab/blob/main/Video_to_GaussianSplat_Colab.ipynb, cell [14]. MIT.
- **Stage:** 3

```python
common = [
    f"--data '{DATA_DIR}'", f"--output-dir '{OUTPUT_DIR}'",
    f"--max-num-iterations {train_iterations}",
    "--viewer.quit-on-train-completion True", "--vis tensorboard",
    f"--experiment-name {scene_name}",
    "--pipeline.model.camera-optimizer.mode SO3xR3",
    "--pipeline.model.use-bilateral-grid True",
    "--pipeline.model.rasterize-mode classic",
]
common += [f"--pipeline.datamanager.cache-images {cache_mode}",
           "--pipeline.datamanager.cache-images-type uint8"]

def model_flags(cap):
    if method == "splatfacto-mcmc":
        return [f"--pipeline.model.max-gs-num {cap}"]
    return ["--pipeline.model.use-scale-regularization True"]

def build(cap):
    return (f"ns-train {method} " + " ".join(common + model_flags(cap)) +
            f" nerfstudio-data --data '{DATA_DIR}' --downscale-factor {factor}")
# [...]
if rc != 0 and "out of memory" in tail.lower() and method == "splatfacto-mcmc":
    cap = int(gs_cap * 0.55)
```

**Adaptation notes**
- Keep `camera-optimizer SO3xR3` and `use-bilateral-grid True`. The bilateral grid corrects auto-exposure differences between the two Insta360 lenses.
- Replace the `method` and preset branching with a frozen `TrainConfig` dataclass holding `method` and `gs_cap`, so the flags derive from one value.
- The OOM retry is a hidden fallback. If kept, record the actual `cap` used in the run's output table rather than only printing it.

### C11 — gsplat CUDA smoke test before a long training run
- **Source:** https://github.com/JittoJoseph/GaussianSplat-Colab/blob/main/Video_to_GaussianSplat_Colab.ipynb, cell [8], the `_check` string. MIT.
- **Stage:** 3 (environment gate)

```python
import warnings; warnings.filterwarnings('ignore')
import torch, gsplat
try:
    from gsplat import csrc  # noqa: F401
    mode = 'precompiled wheel'
except ImportError:
    mode = 'JIT-compiled'
d = 'cuda'; N = 64
means = torch.rand(N, 3, device=d); quats = torch.randn(N, 4, device=d)
scales = torch.rand(N, 3, device=d) * 0.01; opac = torch.rand(N, device=d)
colors = torch.rand(N, 3, device=d); viewmats = torch.eye(4, device=d)[None]
Ks = torch.tensor([[[100., 0, 32], [0, 100, 32], [0, 0, 1]]], device=d)
gsplat.rasterization(means, quats, scales, opac, colors, viewmats, Ks, 64, 64)
torch.cuda.synchronize()
print('READY', mode)
```

**Adaptation notes**
- Use this as the first GPU cell in the Marimo notebook. It replaces Colab's "Runtime → GPU" check (cell [2]) with a real end-to-end kernel call. Show the result with `mo.stop(...)` so downstream cells do not run on a broken environment.
- Drop `warnings.filterwarnings('ignore')`.
- Log the JIT versus precompiled result. A JIT build on each 12-hour molab session costs minutes, so pin a gsplat wheel in pixi or PEP 723.

### C12 — Move COLMAP `.bin` files into `sparse/0`
- **Source:** https://github.com/abolhoseinisina/Colab_COLMAP_3DGS/blob/main/Colab_3DGS.ipynb, cell [11], last two lines. MIT.
- **Stage:** 2→3 handoff

```bash
!mkdir -p /content/project/undistorted/sparse/0
!mv /content/project/undistorted/sparse/*.bin /content/project/undistorted/sparse/0/
```

**Adaptation notes**
- `colmap image_undistorter` writes `sparse/*.bin` flat, but 3DGS-style loaders expect `sparse/0/`. Use `pathlib` moves.
- Do **not** adopt the rest of this notebook. Its trainer is a clone of graphdeco-inria `gaussian-splatting` (via the camenduru fork), which uses Inria's non-commercial license, not MIT. Its environment cells (Python 3.7, CUDA 11.8) are also obsolete.

---

## Stage 4 — Transient and person masking

### C13 — SAM 3 text-prompted segmentation in Pixeltable
- **Source:** https://github.com/pixeltable/pixeltable/blob/main/docs/release/howto/cookbooks/images/img-promptable-segmentation.ipynb, cells [5] (imports) and [7]. Apache-2.0.
- **Stage:** 4

```python
import pixeltable as pxt
from pixeltable.functions.huggingface import (
    sam3_for_segmentation,
    sam_automatic_mask_generation,
)
from pixeltable.functions.vision import bboxes_draw, overlay_segmentation
# [...]
images.select(
    images.image,
    segmented=overlay_segmentation(
        images.image,
        sam3_for_segmentation(images.image, text='zebra').masks,
        draw_contours=True,
    ),
).where(images.name == 'zebra').collect()
```

**Adaptation notes**
- Make it a computed column on the frames view: `frames.add_computed_column(person=sam3_for_segmentation(frames.frame, text='person'))`. Then add a UDF that unions `.masks` and inverts the result into the 3DGRUT mask convention. Per the 3dgrut README ("Using image masks"), each mask is a 0/1 grayscale `<image>_mask.png` next to its image, and 0 pixels are ignored in the loss.
- `facebook/sam3` is gated (cell [2]). Provide `HF_TOKEN` through molab secrets, using the same token cell as C19.
- Fisheye edges are strongly distorted, so check that the person masks hold up at the image periphery.

### C14 — SAM 3 tracked video segmentation as an iterator view
- **Source:** same notebook, cell [13]. Apache-2.0.
- **Stage:** 4

```python
from pixeltable.functions.huggingface import sam3_for_video_segmentation
from pixeltable.functions.video import clip, make_video

videos = pxt.create_table('sam3_video/videos', {'video': pxt.Video})
videos.add_computed_column(
    clipped_video=clip(videos.video, start_time=0, end_time=2)
)
videos.insert([{'video': bangkok}])

frames = pxt.create_view(
    'sam3_video/frames',
    videos,
    iterator=sam3_for_video_segmentation(
        videos.clipped_video, text=['car', 'motorcycle'], fps=5
    ),
)
```

**Adaptation notes**
- Use `text=['person']` on each per-lens video. Tracking keeps the mask on the same person across frames, which a per-frame mask (C13) does not. Use the same `fps` as frame extraction so `pos` lines up.
- Drop `clip(...)`, which is demo-only.
- Per the notebook's note in cell [14], SAM 3 looks ahead a few frames, so pad the end of each clip.

---

## Stage 5 — Depth and normal supervision, and metric scale

### C15 — Scale and orient a COLMAP model from an ArUco marker
- **Source:** https://github.com/meyerls/aruco-estimator/blob/main/README.md, section "Scripting". MIT.
- **Stage:** 5 (metric scale)

```python
from aruco_estimator.sfm.colmap import COLMAPProject
from aruco_estimator.utils import get_transformation_between_clouds,get_corners_at_origin
import cv2
project = COLMAPProject('./door', )
/sparse/0
target_id = 7
aruco_size = .15
aruco_results = project.detect_markers(dict_type=cv2.aruco.DICT_4X4_50)

# Get 3D corners for normalization
target_corners_3d = aruco_results[target_id]
print(target_corners_3d) 

# Calculate 4x4 transform with scaling so tag is at the origin 
transform = get_transformation_between_clouds(target_corners_3d, get_corners_at_origin(side_length=aruco_size))

# Apply normalization to the project
print("Normalizing poses and 3D points...")
project.transform(transform)
project.save("./transformed_output/")
```

**Adaptation notes**
- The README itself contains a stray `/sparse/0` line, a copy error upstream. Delete it when porting.
- The README's "Known Limitations" say only SIMPLE_RADIAL and PINHOLE cameras are supported. Run this on the **undistorted** model (C05 `image_undistorter`), then apply the same 4x4 `transform` to the fisheye model that 3DGUT trains on. Keep the transform as a single stored artifact (one source of truth).
- Needs `opencv-contrib-python`; see the README troubleshooting section. Record `aruco_size` in metres in the run config table, not as a literal in the code.

### C16 — Scale-aligned mono depth and dn-splatter training
- **Source:** https://github.com/maturk/dn-splatter/blob/main/README.md, sections "Generate scale aligned mono-depth estimates" and "Recommended settings". Apache-2.0.
- **Stage:** 5

```bash
python dn_splatter/scripts/align_depth.py --data [path_to_data_root] \
                                      --skip-colmap-to-depths, --no-skip-colmap-to-depths \
                                      --skip-mono-depth-creation, --no-skip-mono-depth-creation \
# [...]
ns-train dn-splatter --pipeline.model.use-depth-loss True \
                 --pipeline.model.depth-lambda 0.2 \
                 --pipeline.model.use-normal-loss True \
                 --pipeline.model.use-normal-tv-loss True \
                 --pipeline.model.normal-supervision (mono/depth)
                 <dataparser_name (normal-nerfstudio, mushroom, scannetpp, etc)> --data PATH_TO_DATA 
```

**Adaptation notes**
- `align_depth.py` expects `colmap/sparse/0` in the data root. Point it at the ArUco-scaled model from C15 so mono depths come out in metres.
- Use `--pipeline.model.depth-loss-type PearsonDepth` for mono depth and `EdgeAwareLogL1` for sensor depth, as the README recommends.
- dn-splatter is a nerfstudio method for pinhole cameras. Feed it the undistorted frames, or treat it as the pinhole alternative to the 3DGUT fisheye path. Do not mix the two in one run.

### C17 — Phone LiDAR RGB-D capture into a dn-splatter dataset
- **Source:** https://github.com/maturk/dn-splatter/blob/main/README.md, section "Custom RGB-D Smartphone (Android/iPhone) Data". Apache-2.0.
- **Stage:** 5 (and stage 6 input)

```bash
pip install spectacularAI
python dn_splatter/scripts/process_sai.py [PATH_TO_SAI_INPUT_FOLDER] [PATH_TO_OUTPUT_FOLDER]
ns-train dn-splatter --pipeline.model.use-depth-loss True \
                 --pipeline.model.depth-lambda 0.2 \
                 --pipeline.model.use-normal-loss True \
                 --pipeline.model.use-normal-tv-loss True \
                 --pipeline.model.normal-supervision depth \
                 normal-nerfstudio --data PATH_TO_DATA
```

**Adaptation notes**
- This applies only if the phone captures are RGB-D streams, such as SpectacularAI or Record3D (see C18). Bare LiDAR PLY scans skip this and go to stage 6 registration.
- Move `pip install spectacularAI` into the PEP 723 header.

### C18 — Record3D (iPhone LiDAR) and Polycam ingest with `ns-process-data`
- **Source:** https://github.com/nerfstudio-project/nerfstudio/blob/main/colab/demo.ipynb, cell [4], two branches. Apache-2.0.
- **Stage:** 5 (LiDAR depth frames into a nerfstudio dataset)

```python
    record_3d_zipfile = preupload_datasets[0]
    !unzip $record_3d_zipfile -d /content/data/nerfstudio/custom_data
    custom_data_directory = glob.glob("/content/data/nerfstudio/custom_data/*")[0]
    !ns-process-data record3d --data $custom_data_directory --output-dir /content/data/nerfstudio/custom_data/
# [...]
    dataset_dir = [os.path.join(dir, f) for f in uploaded.keys()][0]
    !ns-process-data polycam --data $dataset_dir --output-dir /content/data/nerfstudio/custom_data/
```

**Adaptation notes**
- Replace `files.upload()` and `!unzip` with `huggingface_hub.hf_hub_download` from the sources dataset repo, plus `zipfile` and `subprocess.run([...], check=True)`.
- The `[0]` glob silently picks one directory. Assert there is exactly one match.
- Use this only if the phone app exports Record3D or Polycam bundles. The resulting `transforms.json` with depth feeds C16/C17's `normal-nerfstudio` dataparser.

---

## Stage 7 — Mesh extraction and export

### C19 — Mesh from a trained splat with `gs-mesh` (dn-splatter)
- **Source:** https://github.com/maturk/dn-splatter/blob/main/README.md, section "Mesh". Apache-2.0.
- **Stage:** 7

```bash
gs-mesh {dn, tsdf, o3dtsdf, sugar-coarse, gaussians, marching} --load-config [PATH] --output-dir [PATH]
python dn_splatter/scripts/isooctree_dn.py <root_folder> --transformation_path <pose_json_path> \
--tsdf_rel 0.03 --output_mesh_file <output_path/output.ply> --subdivision_threshold=100
```

**Adaptation notes**
- The README recommends `gs-mesh o3dtsdf`. Make the method a `Literal[...]` value in config, not separate cells.
- `--load-config` is the nerfstudio `config.yml` found the way C10 finds it, by newest `config.yml` under the output dir. Record the exact path in the run table instead of searching by mtime.
- Upload the `.ply` to the HF bucket. Load it back with trimesh (C21) for QA.

### C20 — Export the splat to `.ply` and compress it to `.spz`
- **Source:** https://github.com/JittoJoseph/GaussianSplat-Colab/blob/main/Video_to_GaussianSplat_Colab.ipynb, cell [16]. MIT.
- **Stage:** 7

```python
export_py = r"""
import sys, warnings, torch
warnings.filterwarnings("ignore")
_orig_load = torch.load
torch.load = lambda *a, **k: _orig_load(*a, **{**k, "weights_only": False})
cfg, out = sys.argv[1], sys.argv[2]
sys.argv = ["ns-export", "gaussian-splat", "--load-config", cfg, "--output-dir", out]
from nerfstudio.scripts.exporter import entrypoint
entrypoint()
"""
with open("/content/_export_splat.py", "w") as f:
    f.write(export_py)
run(f"TORCHDYNAMO_DISABLE=1 python /content/_export_splat.py '{CONFIG_YML}' '{EXPORT_DIR}'",
    "Exporting .ply", log_path="/content/ns_export.log")
# [...]
    run(f"splat-transform '{PLY_PATH}' '{SPZ_PATH}'", "Compressing to .spz",
        log_path="/content/spz_convert.log")
```

**Adaptation notes**
- The `torch.load` `weights_only=False` patch is needed on PyTorch 2.6 and later for nerfstudio checkpoints. Keep it, with a comment explaining why.
- Install `@playcanvas/splat-transform` (Node) through pixi, not `apt-get` or `npm -g` at runtime. The source wraps this step in `try/except` and prints a warning; make it fail loudly instead.
- For 3DGUT checkpoints, use the 3dgrut export path instead (C08: `export_usd.enabled=true`, and the README's PLY/USD export docs).

### C21 — Load and slice a mesh in Marimo with trimesh
- **Source:** https://github.com/marimo-team/gallery-examples/blob/main/notebooks/cad/trimesh-demo.py, lines 56–82. MIT.
- **Stage:** 7 (mesh QA: floor-plan section through the exported mesh)

```python
@app.cell
def _():
    slider = mo.ui.slider(-0.5, 0.5, 0.01, debounce=True, label="cutoff")
    slider
    return (slider,)


@app.cell
def _(mesh, slider):
    origin = mesh.centroid + np.array([0, 0, slider.value])
    mesh_slice = mesh.section(plane_origin=origin, plane_normal=[0, 0, 1])
    slice_2D, to_3D = mesh_slice.to_2D()
    slice_2D.show()
    return


@app.cell
def _():
    stl_path = Path(__file__).parent / "featuretype.STL"
    if not stl_path.exists():
        urllib.request.urlretrieve(
            "https://github.com/mikedh/trimesh/raw/main/models/featuretype.STL",
            stl_path,
        )

    mesh = trimesh.load_mesh(stl_path)
    return (mesh,)
```

**Adaptation notes**
- Replace the STL download with `hf_hub_download(...)` of the mesh `.ply` from the outputs bucket.
- After ArUco scaling (C15), the slider range is in metres. Set it from `mesh.bounds` rather than the hard-coded ±0.5.
- `slice_2D` can be converted to shapely polygons and written as GeoParquet for the tabular-spatial layer.

---

## Stage 8 — Reading and writing Hugging Face data from Marimo

### C22 — HF token config cell with a visible warning
- **Source:** https://github.com/marimo-team/gallery-examples/blob/main/notebooks/external/dlthub-huggingface.py, lines 93–118. MIT.
- **Stage:** 8

```python
@app.cell
def _():
    from wigglystuff import EnvConfig 

    config = EnvConfig(["HF_TOKEN"])
    config
    return (config,)


@app.cell(hide_code=True)
def _(config):
    hf_token = config.get("HF_TOKEN", None)
    _out = None

    if not config.all_valid:
        _out = mo.callout(
            mo.md(
                "**Warning:** `HF_TOKEN` not set. You may hit Hugging Face rate limits (HTTP 429). "
                "Get a token at https://huggingface.co/settings/tokens and set it with "
                "`export HF_TOKEN=hf_...`"
            ),
            kind="warn",
        )

    _out 
    return
```

**Adaptation notes**
- Writing to the HF dataset and bucket requires a token. Replace the warning with `mo.stop(not config.all_valid, mo.callout(..., kind="danger"))` so write cells cannot run without one.
- Add `wigglystuff` to PEP 723. Set the token through molab secrets and never write it into the notebook.

### C23 — Stream Parquet straight from `hf://` with DuckDB
- **Source:** https://github.com/marimo-team/gallery-examples/blob/main/notebooks/external/dlthub-huggingface.py, lines 126–128 and 179–194. MIT.
- **Stage:** 8

```python
HF_PARQUET_URL = "hf://datasets/lance-format/openvid-lance@~parquet/**/*.parquet"
EXCLUDED_COLUMNS = {"video_blob", "embedding"}
BATCH_SIZE = 1000
# [...]
    @dlt.resource(write_disposition="replace")
    def openvid_videos(limit: int = 100):
        with duckdb.connect() as conn:
            schema = conn.execute(
                f"DESCRIBE SELECT * FROM '{HF_PARQUET_URL}' LIMIT 0"
            ).fetchall()
            columns_sql = ", ".join(
                col[0] for col in schema if col[0] not in EXCLUDED_COLUMNS
            )
            result = conn.execute(
                f"SELECT {columns_sql} FROM '{HF_PARQUET_URL}' LIMIT {limit}"
            )
            columns = [desc[0] for desc in result.description]

            while rows := result.fetchmany(BATCH_SIZE):
                yield [dict(zip(columns, row)) for row in rows]
```

**Adaptation notes**
- The essential part is the DuckDB `hf://datasets/<org>/<repo>/**/*.parquet` read and the `DESCRIBE` column pruning. Use it to read source manifests and GeoParquet pose and registration tables straight into Polars (`conn.execute(...).pl()`), without dlt.
- Keep dlt only if we also want its HF write-back (C24). Otherwise drop the `@dlt.resource` wrapper.

### C24 — Write a curated table back to an HF dataset repo with dlt
- **Source:** same file, lines 356–380 (code inside a `mo.md` documentation cell). MIT.
- **Stage:** 8

```python
hf_pipeline = dlt.pipeline(
    pipeline_name="openvid_curated",
    destination="filesystem",
    dataset_name="openvid_curated",
)
hf_pipeline.run(
    [filtered_arrow],
    table_name="videos",
    write_disposition="replace",
)
```
```toml
# .dlt/secrets.toml
[destination.filesystem]
bucket_url = "hf://datasets/my-org"

[destination.filesystem.credentials]
hf_token = "hf_..."  # Your Hugging Face User Access Token
```

**Adaptation notes**
- Per the notebook, `dataset_name` becomes the repo name. All files for a table are committed in one commit, and dlt keeps the dataset card up to date. That suits frame, pose and registration manifests (tabular). Large binaries such as splats and meshes should go to the HF storage bucket through `huggingface_hub` instead.
- Do not commit `.dlt/secrets.toml`, because this repo is public. Set `DESTINATION__FILESYSTEM__CREDENTIALS__HF_TOKEN` from molab secrets.

### C25 — Run-mode-aware gating of an expensive cell (`mo.app_meta`, `mo.stop`)
- **Source:** same file, lines 201–235. MIT.
- **Stage:** 8 (and every long stage: keeps `marimo run` and app mode from running 12-hour jobs)

```python
    RUN_MODE_LIMIT = 5

    is_run_mode = mo.app_meta().mode == "run"

    match mo.app_meta().mode:
        case "run":
            limit_slider = None

        case _:
            limit_slider = mo.ui.slider(
                start=0,
                stop=50,
                step=1,
                value=5,
                label="Rows to load",
                full_width=True,
            )
# [...]
    _limit = limit_slider.value if limit_slider is not None else RUN_MODE_LIMIT
    mo.stop(_limit == 0, mo.md("**Set rows > 0 to run the pipeline**"))
```

**Adaptation notes**
- Use one "budget" value for each stage (frames, iterations) with a small run-mode default. The `mo.stop` gate then replaces ad-hoc `if run_training:` flags.

---

## Unlicensed source — technique notes only (no code copied)

**libishm1/Colmap_Photogrammetry_Drone_video** (https://github.com/libishm1/Colmap_Photogrammetry_Drone_video). GitHub reports no license. The README prose claims CC BY-NC-SA 4.0, which is non-commercial and share-alike and is not on our allowed list either way. Its techniques, in our words:

- **Stage 1:** extract frames with ffmpeg at a fixed low rate (2 fps) and high JPEG quality, to reduce redundancy before SfM.
- **Stage 2:** run COLMAP's all-in-one reconstruction under a virtual X server (`xvfb-run`) so GPU SIFT works headless. The repo also contains a GLOMAP-based pipeline script and notebook (`glomap_colab_pipeline.py`, `Drone3D_GLOMAP_Colab_MCP_Debug.ipynb`). These were not read in detail because no code can be taken from them.
- **Stage 7:** take the dense path through undistortion, patch-match stereo and stereo fusion to a fused point cloud. Build an Open3D Poisson surface at high octree depth, remove unreferenced vertices and recompute normals. Transfer vertex colours from the dense cloud with a 1-nearest-neighbour KD-tree lookup per mesh vertex, then export a vertex-coloured PLY. In our notebook, write this from Open3D's own documentation (MIT), not from this repo.
- **Performance note:** dense COLMAP on network-mounted storage is I/O-bound. The molab equivalent is to keep the workspace on local scratch and sync results to HF at the end.

---

## Gaps (no adoptable cell found in the requested sources)

- **Stage 6, LiDAR-to-reconstruction registration with Open3D ICP:** no licensed source includes ICP or point-cloud registration code. The aruco-estimator README mentions `fused.ply` dense-cloud alignment only as a feature (no code), and dn-splatter covers training only. Write this from Open3D's MIT-licensed registration tutorials.
- **Stage 1, sharpness scoring and overlap selection:** no source scores blur (for example, variance of Laplacian) or selects frames by overlap. The closest is `ns-process-data --num-frames-target` in C06, which samples evenly. Write it as a Pixeltable UDF computed column.
- **Dual-fisheye `.insv` handling:** every source assumes one video stream. Splitting per lens (`-map 0:v:N`) and the per-lens OPENCV_FISHEYE camera rig are not in any harvested cell. The adaptation notes on C01, C04 and C05 describe the change.
- **GLOMAP and pycolmap:** none of the licensed sources call GLOMAP or pycolmap. The only GLOMAP pipeline seen is in the unlicensed repo.

---

## Non-commercial sources (added 2026-11-12)

The owner confirmed that this project is not a commercial product, so code under non-commercial licenses is allowed here. This section follows the same copy rules as the sections above: verbatim contiguous excerpts, `# [...]` marks dropped lines, and nothing was rewritten. Two rules are added:

- Every adapted cell keeps the source's copyright and license notice. The exact lines are given with each piece under **Notice to keep**.
- **Share-alike:** cells adapted from GGPS (CC BY-NC-SA 4.0) must stay CC BY-NC-SA 4.0. PGSR's license also requires derivatives to be open source and non-commercial. These cells are flagged **[SA]**. Keep them in their own notebook module, so that the share-alike terms do not spread to the rest of the notebook.

Licenses were read from each repo's LICENSE file through `gh api repos/<r>/license`. The API reports `NOASSERTION` for all five, so the text itself was checked. Everything was fetched from the default branch at the SHAs below.

| Repo | License (LICENSE text) | Commit | Files read | Status |
|---|---|---|---|---|
| tuallen/GOFish | CC BY-NC 4.0 for Amazon files. `configs/` and the 3DGRUT-derived code are Apache-2.0. Files ported from SOF, StopThePop, CoMe and GOF are under the Inria Gaussian-Splatting License (see `THIRD-PARTY-LICENSES`). | 1a33e7a9ff73 | `README.md`, `THIRD-PARTY-LICENSES`, `docs/components.md`, `configs/apps/fiord.yaml`, `configs/dataset/colmap.yaml`, `gofish/data/fiord.py`, `gofish/camera/{domain,make_domain}.py`, `gofish/camera/data/{README.md,fiord.json}`, `mesh.py`, `benchmark/{common,fiord}.sh`, `gofish/eval/fiord/{mesh_metrics,observed_gt}.py` | OK. Full code release. |
| Insta360-Research-Team/GGPS | **CC BY-NC-SA 4.0** in `LICENSE.md`. The README says CC BY-NC 4.0, so we apply the stricter BY-NC-SA. The ERP rasterizer under `submodules/diff-gaussian-rasterization` is **GPL-3.0** (from OmniGS, see `NOTICE_OMNIGS.md`). Files that carry the Inria header are also under the Gaussian-Splatting License. | b30b236c6657 | `README.md`, `NOTICE_OMNIGS.md`, `requirements.txt`, `config_360/{templates/lonlat_template,self_captured/nsk_c4}.yaml`, `tools/{make_depth_scale,generate_depth_and_skymask,_pano_colmap_utils}.py`, `scripts_new/prepare_pano_scene.sh`, `utils/{large_utils,loss_utils}.py`, `data_partition.py`, `scene/dataset_readers.py` | OK. Training code was released 2026-07-09. The pretrained `.ply` models are still listed as "late July 2026", not released. |
| Anttwo/MILo | Inria Gaussian-Splatting License in the top-level `LICENSE.md`. `milo/LICENSE` is an unfilled Apache-2.0 template. The two conflict, so we treat all of MILo as Inria non-commercial. | 0c38aa65f8b7 | `README.md`, `install.py`, `milo/configs/mesh/default.yaml`, `milo/convert.py`, file headers | OK. "Estimate camera poses with VGGT" is still "Coming soon". |
| Metaverse-AI-Lab-THU/DirectFisheye-GS | Inria Gaussian-Splatting License | db9b3a25bff7 | `README.md`, `environment.yml`, `convert.py`, `training_cli.py`, `scene/dataset_readers.py`, `utils/find_camera_groups.py`, `submodules/diff-gaussian-rasterization/cuda_rasterizer/{auxiliary.h,forward.cu}` | OK |
| zju3dv/PGSR | Custom ZJU license: "educational, research and non-profit purposes only. Any modification based on this work must be open-source and prohibited for commercial use." `render.py` and others also carry the Inria header. | de24f1a38b35 | `README.md`, `LICENSE.md`, `requirements.txt`, `render.py`, `arguments/__init__.py`, `scripts/run_tnt.py`, `scene/dataset_readers.py` | OK |

**Findings that apply to every piece below**

- **No repo reads `.insv`.** None of them splits dual-fisheye video or handles Insta360 files directly. Stage 1 remains our own code (ffmpeg `-map 0:v:0` and `-map 0:v:1`, as in the earlier gap note). GOFish is the closest match: its FIORD benchmark *is* Insta360 dual 200° fisheye footage, with two `OPENCV_FISHEYE` cameras (one per lens, 3264×3264) in one COLMAP model.
- **Field-of-view limits differ.** GOFish rasterizes beyond 180°. DirectFisheye-GS culls any Gaussian with view-space `z <= 0.2` (`cuda_rasterizer/auxiliary.h` line 194), so it trains only the front hemisphere of each lens. MILo and PGSR take pinhole input only (PGSR asserts this in `scene/dataset_readers.py` line 111). GGPS takes ERP panoramas only (`default_camera_type: 3`).
- **The environments cannot be merged.**
  - GOFish: Python ≥3.11, torch 2.8.0+cu128, numpy 2.4.6, open3d 0.19.0, plus the Slang compiler and CGAL.
  - GGPS: Python 3.9, torch 2.8.0 cu128, numpy==1.26.2.
  - DirectFisheye-GS: Python 3.12.11, torch 2.8.0+cu126.
  - MILo: torch 2.3.1, CUDA 11.8 (12.1 untested), CGAL, nvdiffrast.
  - PGSR: Python 3.8, cu118, pytorch3d, open3d.

  Give each trainer its own pixi environment and call it from the notebook through the C07 subprocess runner. Do not try to fit them into one PEP 723 header.
- **molab build status: not built or run during this harvest.** Each trainer compiles CUDA extensions, so each needs `nvcc` matching its torch build (for example, pixi `cuda-nvcc` at the right version). GOFish and MILo also need CGAL and GMP, which pixi provides from conda-forge as `cgal-cpp` and `gmp`. Use those instead of `sudo apt`. Set `TORCH_CUDA_ARCH_LIST` to the molab GPU's compute capability, and pass `--no-build-isolation` as GGPS's README explains.

---

### Stage 2 — Poses and fisheye camera models

#### N01 — Write a calibrated-domain record for each OPENCV_FISHEYE lens (GOFish)
- **Source:** tuallen/GOFish @ 1a33e7a9ff73, `gofish/camera/make_domain.py` lines 38–54. CC BY-NC 4.0.
- **Stage:** 2 (camera models), consumed by stage 3 (`dataset.camera_domains`).

```python
    apertures = {int(row[0]): (float(row[1]), float(row[2]), float(row[3])) for row in args.aperture}
    records = []
    for camera_id, intrinsic in sorted(_read_cameras(args.model_dir).items()):
        if intrinsic.model != "OPENCV_FISHEYE":
            continue
        params = [float(value) for value in intrinsic.params]
        theta_limit = monotone_branch_limit(params[4:8])
        record = {"camera_id": int(camera_id), "model": intrinsic.model, "width": int(intrinsic.width),
                  "height": int(intrinsic.height), "params": params}
        if camera_id in apertures:
            cx, cy, radius = apertures[camera_id]
            record |= {"kind": "aperture", "aperture_center": [cx, cy], "aperture_radius": radius,
                       "theta_limit": theta_limit, "rho_limit": radial_value(theta_limit, params[4:8])}
        else:
            record |= {"kind": "max_angle", "max_angle": theta_limit}
        records.append(record)
    args.output.write_text(json.dumps({"cameras": records}, indent=1) + "\n")
```

**Notice to keep:** `# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.` / `# SPDX-License-Identifier: CC-BY-NC-4.0` / `# Adapted from tuallen/GOFish@1a33e7a gofish/camera/make_domain.py`

**Adaptation notes**
- Write one record per lens (two `camera_id`s). Measure each lens's image circle (`cx, cy, radius`) once from a frame of our 3840×3840 streams, and keep those values as data in the Pixeltable camera table.
- `_read_cameras` imports from `threedgrut`. On molab, run this inside the GOFish pixi environment through a subprocess (`python -m gofish.camera.make_domain <sparse/0> domains.json --aperture 1 CX CY R --aperture 2 CX CY R`). Do not import it into the notebook kernel.
- For reference, `gofish/camera/data/fiord.json` holds Insta360 lens records at 3264 px: fx≈998, `theta_limit = π`. Use them only as a sanity range for our own calibration, not as a calibration.

#### N02 — First monotone branch of the Kannala–Brandt polynomial (GOFish)
- **Source:** tuallen/GOFish @ 1a33e7a9ff73, `gofish/camera/domain.py` lines 39–48 and 53–66. CC BY-NC 4.0.
- **Stage:** 2 (check that an `OPENCV_FISHEYE` calibration stays valid past 90° off-axis)

```python
def radial_value(theta: float, coefficients: Iterable[float]) -> float:
    k1, k2, k3, k4 = (float(value) for value in coefficients)
    y = theta * theta
    return theta * (1.0 + y * (k1 + y * (k2 + y * (k3 + y * k4))))


def radial_derivative(theta: float, coefficients: Iterable[float]) -> float:
    k1, k2, k3, k4 = (float(value) for value in coefficients)
    y = theta * theta
    return 1.0 + y * (3.0 * k1 + y * (5.0 * k2 + y * (7.0 * k3 + y * 9.0 * k4)))
# [...]
    k1, k2, k3, k4 = (float(value) for value in coefficients)
    polynomial = np.asarray([9.0 * k4, 7.0 * k3, 5.0 * k2, 3.0 * k1, 1.0], dtype=np.float64)
    nonzero = np.flatnonzero(np.abs(polynomial) > 0.0)
    roots = np.roots(polynomial[int(nonzero[0]):])
    roots_y = sorted(
        float(root.real)
        for root in roots
        if abs(float(root.imag)) <= 1.0e-10 * max(1.0, abs(float(root.real))) and float(root.real) > 0.0
    )
    folds = [math.sqrt(value) for value in roots_y if math.sqrt(value) < math.pi]
    limit = math.nextafter(folds[0] if folds else math.pi, 0.0)
    while radial_derivative(limit, (k1, k2, k3, k4)) <= 0.0:
        limit = math.nextafter(limit, 0.0)
    return limit
```

**Notice to keep:** `# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.` / `# SPDX-License-Identifier: CC-BY-NC-4.0` / `# From tuallen/GOFish@1a33e7a gofish/camera/domain.py`

**Adaptation notes**
- This needs only `math` and `numpy`, so it runs in the notebook kernel. Make it a Pixeltable UDF that checks each COLMAP lens: a `theta_limit` below the lens half-FoV (≥ 100° for our lenses) means the fit folds back before the image circle edge, so that pose run should be rejected.
- Feed it `params[4:8]` (k1..k4) of each lens from `cameras.bin`, read with pycolmap.

#### N03 — COLMAP feature extraction and mapper for native fisheye (DirectFisheye-GS)
- **Source:** Metaverse-AI-Lab-THU/DirectFisheye-GS @ db9b3a25bff7, `convert.py` lines 81–96 and 120. Inria Gaussian-Splatting License.
- **Stage:** 2

```python
def build_feature_extraction_cmd(colmap_command, source_path, camera_model, use_gpu, image_list_path):
    return (
        colmap_command
        + " feature_extractor "
        + "--database_path "
        + os.path.join(source_path, "distorted", "database.db")
        + " --image_path "
        + os.path.join(source_path, "input")
        + " --image_list_path "
        + image_list_path
        + " --ImageReader.single_camera 1 "
        + " --ImageReader.camera_model "
        + camera_model
        + " --SiftExtraction.use_gpu "
        + str(use_gpu)
    )
# [...]
        + " --Mapper.ba_global_function_tolerance=0.000001"
```

**Notice to keep:** `# Copyright (C) 2023, Inria, GRAPHDECO research group. All rights reserved.` / `# Free for non-commercial, research and evaluation use under the Gaussian-Splatting License.` / `# Adapted from Metaverse-AI-Lab-THU/DirectFisheye-GS@db9b3a2 convert.py`

**Adaptation notes**
- `--ImageReader.single_camera 1` would merge both lenses into one camera, which is wrong for us. Run the extractor twice with `--image_list_path` set to the lens-0 list and then the lens-1 list. Each run then creates its own `OPENCV_FISHEYE` camera in the same database.
- DirectFisheye's loader opens `os.path.basename(extr.name)`, so frame names must be unique in one flat folder (for example, `l0_000123.jpg` and `l1_000123.jpg`), not split into `lens0/` and `lens1/` subfolders.
- Build the argv as a list and run it through the C07 runner instead of `os.system`. `exhaustive_matcher` is too slow for video, so use `sequential_matcher` with loop detection.

#### N04 — ERP (lon/lat) projection convention for panoramic poses (GGPS) [SA]
- **Source:** Insta360-Research-Team/GGPS @ b30b236c6657, `tools/_pano_colmap_utils.py` lines 174–186. CC BY-NC-SA 4.0.
- **Stage:** 2 (only on the ERP route, that is, if we stitch to equirectangular and train with GGPS)

```python
    for img_id, fr in enumerate(frames, start=1):
        qvec = fr["qvec"]
        tvec = fr["tvec"]
        R = _qvec2rotmat(qvec)
        pts_cam = xyz @ R.T + tvec  # (N, 3)

        r = np.sqrt(np.sum(pts_cam ** 2, axis=-1))
        valid = r > min_dist

        lon = np.arctan2(pts_cam[:, 0], pts_cam[:, 2])
        lat = np.arcsin(np.clip(pts_cam[:, 1] / np.clip(r, 1e-8, None), -1, 1))

        u = (lon / np.pi + 1.0) * (W / 2.0)
```

**Notice to keep:** `# Adapted from Insta360-Research-Team/GGPS@b30b236 tools/_pano_colmap_utils.py — CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/). Changes: <list>. This cell is licensed CC BY-NC-SA 4.0.`

**Adaptation notes**
- This is the projection GGPS's rasterizer expects: +z forward, lon = atan2(x, z), v grows with +y. Any ERP frames we stitch from the two fisheyes (for example, with ffmpeg `v360=dfisheye:e`) must use the same convention, or the poses and images will disagree.
- Use it as an assertion cell: project the sparse points into a few ERP frames and overlay them, to check the stitch and pose convention before training.

---

### Stage 3 — Splat training on fisheye or panoramic input

#### N05 — Package a COLMAP fisheye scene into `sparse/0` + `images_<k>/` (GOFish)
- **Source:** tuallen/GOFish @ 1a33e7a9ff73, `gofish/data/fiord.py` lines 56–77. CC BY-NC 4.0.
- **Stage:** 1→3 (dataset layout that GOFish's `train.py` reads)

```python
def prepare(source: Path, target: Path, factor: int = 4) -> None:
    model = next((source / d for d in MODEL_DIRS if (source / d / "images.bin").is_file()), None)
    if model is None:
        raise SystemExit(f"{source}: no fisheye COLMAP model in {', '.join(MODEL_DIRS)}")
    sparse = target / "sparse" / "0"
    sparse.mkdir(parents=True, exist_ok=True)
    for stem in MODEL_FILES:
        for suffix in (".bin", ".txt"):
            if (model / f"{stem}{suffix}").is_file():
                shutil.copyfile(model / f"{stem}{suffix}", sparse / f"{stem}{suffix}")
    names = sorted(image.name for image in read_images(model / "images.bin"))
    images = next((source / d for d in IMAGE_DIRS if (source / d / names[0]).is_file()), None)
    if images is None:
        raise SystemExit(f"{source}: no image folder ({', '.join(IMAGE_DIRS)}) holds {names[0]}")
    for name in names:
        dst = target / f"images_{factor}" / name
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(images / name) as image:
            image.resize((image.width // factor, image.height // factor), Image.Resampling.BICUBIC).save(dst)
    print(f"{target}: {len(names)} registered images at 1/{factor}")
```

**Notice to keep:** `# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.` / `# SPDX-License-Identifier: CC-BY-NC-4.0` / `# Adapted from tuallen/GOFish@1a33e7a gofish/data/fiord.py`

**Adaptation notes**
- Replace `read_images` with `pycolmap.Reconstruction(model).images` so that this runs in the notebook kernel. Set `MODEL_DIRS`/`IMAGE_DIRS` to our own layout instead of FIORD's.
- FIORD trains at ¼ resolution (3264 → 816 px). Expose `factor` as a run-mode value (C25) and record it in Pixeltable with the dataset row.
- The `dst.exists()` skip makes the cell resumable. Write `target` to local scratch, then sync it to the HF bucket (stage 8).

#### N06 — GOFish train, render and mesh for one scene, plus the own-data override (GOFish)
- **Source:** tuallen/GOFish @ 1a33e7a9ff73, `README.md` lines 107–119. CC BY-NC 4.0.
- **Stage:** 3 and 7

```bash
DATA=runs/_data/Kitchen_In
RUN=runs/Kitchen_In
python -m gofish.data.fiord scene /data/FIORD/Kitchen_In "$DATA"

# Train GOFish (add geometry=sof for + Geometry Objective)
python train.py --config-name apps/fiord path="$DATA" out_dir=runs experiment_name=Kitchen_In

# Render the test set with the exact renderer of the paper's tables, and measure the real-time frame rate
python render.py --checkpoint "$RUN/ckpt_last.pt" --out "$RUN/heldout" --renderer exact
python -m threedgrut.benchmark --checkpoint "$RUN/ckpt_last.pt" --out "$RUN/fps.json"

# Extract the mesh from the geometry checkpoint
python mesh.py --checkpoint "$RUN/ours_30000/ckpt_30000.pt" --out "$RUN/mesh"
```

**Notice to keep:** `# GOFish commands from tuallen/GOFish@1a33e7a README.md — CC BY-NC 4.0; training/rendering/meshing also run Gaussian-Splatting-License code (non-commercial).`

**Adaptation notes**
- For our data, README lines 122–125 give the override: `--config-name apps/fiord path=<scene> dataset.camera_domains=[] dataset.downsample_factor=<k>`. Point `dataset.camera_domains` at the N01 JSON instead of `[]` once the apertures are measured. Add `geometry=sof` for the mesh-quality run.
- The mesh comes from the geometry checkpoint `ours_<n_iterations - n_distillation_steps>`, not from `ckpt_last.pt`. `benchmark/common.sh` lines 63–68 compute that step from `parsed.yaml`. Compute it the same way, without hard-coding 30000.
- Run each step through C07 with the GOFish pixi environment. The checkpoints and `mesh/mesh.ply` go to the HF bucket at the end of each step, because molab wipes scratch.

#### N07 — FIORD app config: Insta360 dual-fisheye training knobs (GOFish)
- **Source:** tuallen/GOFish @ 1a33e7a9ff73, `configs/apps/fiord.yaml` lines 17–38. **Apache-2.0** (3DGRUT-derived, with Amazon modifications).
- **Stage:** 3

```yaml
# FIORD: Insta360 dual 200-degree fisheye, COLMAP OPENCV_FISHEYE, images_4/.
defaults:
  - /base_gs
  - /dataset: colmap
  - /initialization: colmap
  - /render: 3dgut
  - _self_
  - /geometry: null  # + Geometry Objective: geometry=sof

seed_initialization: 1234
dataset:
  downsample_factor: 4
  camera_sampler_seed: 771234
  camera_domains: [fiord.json]  # measured lens apertures
post_processing:
  # Wide-Angle Appearance Modeling: PPISP with 50 radial knots and a 50x50 flat-field grid per camera.
  radial_attenuation_knots: 50
  flatfield_grid: 50
render:
  # Test renders: numpy.rint PNG quantization and rgb * (W_r * W_ff), see configs/render/3dgut.yaml.
  png_rounding: half_even
  wa_order: product
```

**Notice to keep:** `# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.` / `# SPDX-FileCopyrightText: Modifications Copyright Amazon.com, Inc. or its affiliates.` / `# SPDX-License-Identifier: Apache-2.0`

**Adaptation notes**
- Copy this to `configs/apps/cliffhouse.yaml` with `camera_domains: [<N01 output>]` and our `downsample_factor`. The 50-knot radial and 50×50 flat-field appearance model handles lens falloff, so keep it on for both lenses.
- `load_exif: true` (in `configs/dataset/colmap.yaml`) expects EXIF exposure in each frame. Frames extracted from `.insv` with ffmpeg have no EXIF, so set it to `false` or write exposure into the frames.

#### N08 — DirectFisheye-GS training with cross-view joint optimization (DirectFisheye-GS)
- **Source:** Metaverse-AI-Lab-THU/DirectFisheye-GS @ db9b3a25bff7, `README.md` lines 147–161, and `submodules/diff-gaussian-rasterization/cuda_rasterizer/auxiliary.h` line 194. Inria Gaussian-Splatting License.
- **Stage:** 3

```bash
python train.py \
  -s /path/to/scene \
  -m output/scene_name
# [...]
python train.py \
  -s /path/to/scene \
  -m output/scene_name \
  --eval
```
```cpp
	if (p_view.z <= 0.2f)
```

**Notice to keep:** `# DirectFisheye-GS (Metaverse-AI-Lab-THU/DirectFisheye-GS@db9b3a2) — Gaussian-Splatting License, non-commercial research and evaluation use only.`

**Adaptation notes**
- Keep the default `--bs 2`. README line 161 says `--bs 1` falls back to single-view training and does not reproduce CVO. By default, the loader resizes large images toward about 1.6k.
- The `z <= 0.2` cull means content beyond 90° off-axis is never rendered. Mask each lens to its 180° circle, or prefer GOFish for the full >180° FoV. Treat this trainer as the baseline.
- Environment: Python 3.12.11, torch 2.8.0+cu126 (`environment.yml`). The rasterizer is a vendored `pip install` of `submodules/diff-gaussian-rasterization` and `simple-knn`.

#### N09 — COLMAP covisibility from shared 3D points (DirectFisheye-GS)
- **Source:** Metaverse-AI-Lab-THU/DirectFisheye-GS @ db9b3a25bff7, `utils/find_camera_groups.py` lines 119–130. Inria Gaussian-Splatting License.
- **Stage:** 3 (view grouping), also stage 1 (dropping redundant frames after a first SfM pass)

```python
        point_to_images = defaultdict(list)
        for idx, image_name in enumerate(image_names):
            for point_id in images[image_name]["point3D_ids"]:
                point_to_images[point_id].append(idx)

        covisibility = defaultdict(int)
        for _, img_indices in tqdm(point_to_images.items(), desc="Building covisibility matrix"):
            for i in range(len(img_indices)):
                for j in range(i + 1, len(img_indices)):
                    idx_i, idx_j = img_indices[i], img_indices[j]
                    covisibility[(idx_i, idx_j)] += 1
                    covisibility[(idx_j, idx_i)] += 1
```

**Notice to keep:** `# Adapted from Metaverse-AI-Lab-THU/DirectFisheye-GS@db9b3a2 utils/find_camera_groups.py — Gaussian-Splatting License (non-commercial research use).`

**Adaptation notes**
- `images[name]["point3D_ids"]` comes from pycolmap. Store the pair counts as a Pixeltable table `(img_a, img_b, shared_points)`. Frame selection and lens-pairing checks can then read it.
- Cross-lens covisibility (an `l0_*` frame with an `l1_*` frame at the same timestamp) should be near zero for back-to-back lenses. A high count signals a lens mix-up.

#### N10 — Panorama AABB from camera baseline × disparity factor (GGPS) [SA]
- **Source:** Insta360-Research-Team/GGPS @ b30b236c6657, `utils/large_utils.py` lines 240, 245–252 and 293–304. CC BY-NC-SA 4.0.
- **Stage:** 3 (partitioning or cropping a large exterior+interior scene)

```python
def _median_nearest_neighbor_distance(centers_np: np.ndarray) -> float:
# [...]
    n = centers_np.shape[0]
    if n < 2:
        return 0.0
    pts = torch.from_numpy(centers_np.astype(np.float32))
    d = torch.cdist(pts, pts)
    d.fill_diagonal_(float("inf"))
    nn = d.min(dim=1).values.cpu().numpy()
    return float(np.median(nn))
# [...]
    cc = np.stack(centers, axis=0).astype(np.float64)

    center = cc.mean(axis=0)
    deviations = np.abs(cc - center)
    radius = np.percentile(deviations, p_radius, axis=0)

    baseline = _median_nearest_neighbor_distance(cc)
    margin_meters = baseline * disparity_factor
    pad = np.full(3, margin_meters, dtype=np.float64)

    lo = center - radius - pad
    hi = center + radius + pad
```

**Notice to keep:** `# Adapted from Insta360-Research-Team/GGPS@b30b236 utils/large_utils.py — CC BY-NC-SA 4.0. Changes: <list>. This cell is licensed CC BY-NC-SA 4.0.`

**Adaptation notes**
- Replace the `loadCam_woImage` loop (lines 289–292) with camera centres read from pycolmap, so that `cc` is an `(N, 3)` array. The rest is plain numpy and torch.
- GGPS's own configs use `aabb_pano_disparity_factor: 30` (the function default is 15). The margin is `baseline * factor` in scene units. Until stage 5/6 fixes metric scale, it is relative to the SfM scale.
- The same AABB serves as the crop box for mesh extraction (stage 7) and LiDAR registration (stage 6).

#### N11 — GGPS six-stage coarse → partition → block → merge sequence and partition keys (GGPS) [SA]
- **Source:** Insta360-Research-Team/GGPS @ b30b236c6657, `README.md` lines 232–237, and `config_360/self_captured/nsk_c4.yaml` lines 8–27. CC BY-NC-SA 4.0.
- **Stage:** 3

```text
| 1 | `python train_large.py --config config_360/<scene>.yaml` | Coarse training (30K iterations) |
| 2 | `python data_partition.py --config config_360/<scene>_c4.yaml` | Data partitioning |
| 3 | `python train_large.py --config config_360/<scene>_c4.yaml --block_id N` | Per-block fine-tuning |
| 4 | `python merge.py --config config_360/<scene>_c4.yaml` | Merge |
| 5 | `python render_large.py --config config_360/<scene>_c4.yaml --skip_train` | Render |
| 6 | `python metrics_large.py -m output/<scene>_c4 -t test` | Evaluate |
```
```yaml
    partition_name: "nsk_c4",
    pretrain_path: "output/nsk_coarse/point_cloud/iteration_30000",
    model_path: "",
    images: "imgs",
    alpha_masks: "",
    use_alpha_masks: False,
    use_sky_masks: False,
    use_depth: False,
    block_dim: [2, 1, 1],
    partition_mode: "gradient",
    grad_ratio_threshold: 0.8,
    ssim_threshold: 0.08,
    resolution: 1,
    white_background: False,
    data_device: "cpu",
    eval: True,
    skybox_num: 0,
    skybox_locked: True,
    default_camera_type: 3,
    aabb_autofit_mode: "cameras_pano",
```

**Notice to keep:** `# From Insta360-Research-Team/GGPS@b30b236 (README.md, config_360/self_captured/nsk_c4.yaml) — CC BY-NC-SA 4.0. This cell is licensed CC BY-NC-SA 4.0.`

**Adaptation notes**
- GGPS is ERP-only (`default_camera_type: 3`), and its rasterizer is GPL-3.0. It applies only if we stitch the two fisheyes into equirectangular frames. Use it for the large exterior/courtyard pass, where partitioning pays off.
- Run each row as a separate C07 call in a GGPS pixi environment (Python 3.9, numpy 1.26.2). Each block's `point_cloud.ply` is the resume marker, so sync it to the HF bucket after each block to survive the 12 h session limit.
- `use_depth: True` requires N13 to run first (see N13).

#### N12 — Latitude-weighted SSIM for ERP images (GGPS) [SA]
- **Source:** Insta360-Research-Team/GGPS @ b30b236c6657, `utils/loss_utils.py` lines 76 and 100–107. CC BY-NC-SA 4.0. The file also carries the Inria header.
- **Stage:** 3 (loss), and evaluation of ERP renders

```python
def ssim_erp_weighted(img1, img2, window_size=11):
# [...]
    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
               ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))

    H = ssim_map.shape[-2]
    phi = pi * (0.5 - torch.arange(H, device=ssim_map.device).float() / H)
    shape = [1] * (ssim_map.dim() - 2) + [H, 1]
    w = torch.cos(phi).view(*shape)
    return (ssim_map * w).sum() / w.expand_as(ssim_map).sum()
```

**Notice to keep:** `# Copyright (C) 2023, Inria, GRAPHDECO research group. Free for non-commercial, research and evaluation use under the Gaussian-Splatting License.` / `# Modified by Insta360-Research-Team/GGPS@b30b236 utils/loss_utils.py — CC BY-NC-SA 4.0. This cell is licensed CC BY-NC-SA 4.0.`

**Adaptation notes**
- Use it as an evaluation metric when comparing ERP renders of GOFish and GGPS. Plain SSIM over-weights the poles of an equirectangular image.

---

### Stage 5 — Depth, normals and metric scale

#### N13 — Per-frame scale/offset that aligns mono inverse depth to SfM, with ERP radial depth (GGPS) [SA]
- **Source:** Insta360-Research-Team/GGPS @ b30b236c6657, `tools/make_depth_scale.py` lines 97–105 and 133–143. CC BY-NC-SA 4.0.
- **Stage:** 5

```python
    pts = points3d_ordered[pts_idx]
    R = qvec2rotmat(image_meta.qvec)
    pts_cam = np.dot(pts, R.T) + image_meta.tvec
    if camera_type == 3:
        # ERP/LonLat: rasterizer uses radial distance r = sqrt(x²+y²+z²)
        r = np.sqrt(np.sum(pts_cam ** 2, axis=-1))
        inv_colmap = 1.0 / np.clip(r, 1e-8, None)
    else:
        inv_colmap = 1.0 / np.clip(pts_cam[..., 2], 1e-8, None)
# [...]
    t_colmap = np.median(inv_colmap)
    s_colmap = np.mean(np.abs(inv_colmap - t_colmap))
    t_mono = np.median(inv_mono)
    s_mono = np.mean(np.abs(inv_mono - t_mono))
    if s_mono <= 1e-8:
        scale, offset = 0.0, 0.0
    else:
        scale = float(s_colmap / s_mono)
        offset = float(t_colmap - t_mono * scale)

    return {"image_name": os.path.splitext(image_meta.name)[0], "scale": scale, "offset": offset}
```

**Notice to keep:** `# Adapted from Insta360-Research-Team/GGPS@b30b236 tools/make_depth_scale.py — CC BY-NC-SA 4.0. Changes: <list>. This cell is licensed CC BY-NC-SA 4.0.`

**Adaptation notes**
- The robust fit (median for offset, mean absolute deviation for scale) is independent of camera model. For our fisheye frames, use the `camera_type == 3` radial branch (r = ‖p_cam‖), not z-depth, because fisheye depth is radial.
- Run it as a Pixeltable computed column over the frame view. Its inputs are the frame's COLMAP points and the 16-bit inverse-depth PNG, and its output is the `{scale, offset}` struct. GGPS flags frames whose scale is outside 0.2×–5× the median (lines 190–193).
- This aligns depth to the SfM scale, not to metres. Metric scale still comes from stage 6 (LiDAR) or a marker (C15).

#### N14 — Depth + sky mask → 16-bit inverse-depth PNG and 8-bit sky PNG (GGPS) [SA]
- **Source:** Insta360-Research-Team/GGPS @ b30b236c6657, `tools/generate_depth_and_skymask.py` lines 75–91 and 185–186. CC BY-NC-SA 4.0.
- **Stage:** 4 (sky mask) and 5 (depth file format)

```python
def depth_to_invdepth_u16(depth: np.ndarray, sky_mask: np.ndarray) -> np.ndarray:
    """将 metric depth 转为 16-bit 逆深度 PNG。

    invdepth = 1/depth（天空=0），归一化到 [0, 65535]。
    """
    eps = 1e-6
    invdepth = np.zeros_like(depth, dtype=np.float32)
    fg = ~sky_mask & (depth > eps)
    invdepth[fg] = 1.0 / depth[fg]

    max_val = invdepth.max()
    if max_val > 0:
        invdepth_norm = invdepth / max_val
    else:
        invdepth_norm = invdepth

    return (invdepth_norm * 65535).astype(np.uint16), max_val
# [...]
        sky_png = np.where(sky_mask, 0, 255).astype(np.uint8)
        cv2.imwrite(sky_out, sky_png)
```

**Notice to keep:** `# Adapted from Insta360-Research-Team/GGPS@b30b236 tools/generate_depth_and_skymask.py — CC BY-NC-SA 4.0. This cell is licensed CC BY-NC-SA 4.0.`

**Adaptation notes**
- The depth model GGPS uses (DAP, loaded from a local checkout) is not vendored here, and its license was not checked. Keep only this encoding step and feed it any depth/sky model whose license we have confirmed.
- Normalizing per frame to the frame's max inverse depth throws away cross-frame scale. That is fine only because N13 re-fits scale and offset per frame. Store `max_val` in Pixeltable anyway.

#### N15 — PGSR multi-view geometry neighbour defaults (PGSR) [SA]
- **Source:** zju3dv/PGSR @ de24f1a38b35, `arguments/__init__.py` lines 59–62, and `scripts/run_tnt.py` line 16. PGSR license, with the Inria header.
- **Stage:** 5 (planar depth/normal training on undistorted pinhole crops)

```python
        self.multi_view_num = 8
        self.multi_view_max_angle = 30
        self.multi_view_min_dis = 0.01
        self.multi_view_max_dis = 1.5
# [...]
    common_args = f"--quiet -r2 --ncc_scale 0.5 --data_device {data_devices[id]} --densify_abs_grad_threshold 0.00015 --opacity_cull_threshold 0.05 --exposure_compensation"
```

**Notice to keep:** `// Copyright 2023-2024 3D Vision Group at the State Key Lab of CAD&CG, Zhejiang University. All Rights Reserved. Educational, research and non-profit use only; modifications must be open-source and non-commercial. (zju3dv/PGSR@de24f1a)` and the Inria Gaussian-Splatting notice.

**Adaptation notes**
- `multi_view_max_dis` (1.5) and `multi_view_min_dis` are in scene units. Rescale them once the model is metric, because the lodge spans tens of metres.
- PGSR accepts only `PINHOLE`/`SIMPLE_PINHOLE`. Feed it the `colmap image_undistorter` output of the fisheye model (C05), and set `--max_abs_split_points 0` for low-texture plaster walls (README advice).

---

### Stage 6 — LiDAR registration and geometry evaluation

#### N16 — Sample an aligned mesh and get nearest distances to a LiDAR cloud (GOFish)
- **Source:** tuallen/GOFish @ 1a33e7a9ff73, `gofish/eval/fiord/observed_gt.py` lines 177–200. CC BY-NC 4.0.
- **Stage:** 6 (check registration of the phone LiDAR PLY against our mesh), and 7

```python
def nearest_distances(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    from scipy.spatial import cKDTree

    distances, _ = cKDTree(np.asarray(target, np.float64)).query(np.asarray(source, np.float64), k=1, workers=-1)
    return np.asarray(distances, dtype=np.float64)


def sample_mesh(mesh_path: str | Path, transform: np.ndarray, count: int = NUM_MESH_SAMPLES,
                seed: int = SEED) -> np.ndarray:
    """Uniform area samples of the mesh after alignment to the GT frame."""
    import open3d as o3d

    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    transformed = o3d.geometry.TriangleMesh(mesh)
    transformed.transform(transform)
    try:
        cloud = transformed.sample_points_uniformly(number_of_points=count, seed=seed)
    except TypeError:
        # Open3D 0.19 has no ``seed`` argument here; seed its global generator instead.
        o3d.utility.random.seed(seed)
        cloud = transformed.sample_points_uniformly(number_of_points=count)
    return np.asarray(cloud.points, dtype=np.float64)
```

**Notice to keep:** `# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.` / `# SPDX-License-Identifier: CC-BY-NC-4.0` / `# From tuallen/GOFish@1a33e7a gofish/eval/fiord/observed_gt.py`

**Adaptation notes**
- `transform` is the 4×4 mesh→LiDAR matrix. GOFish stores it as `{"transform_mesh_to_gt": [[...]]}` per scene (`gofish/eval/fiord/alignments/*.json`), and we can store ours the same way. Our ICP (written from Open3D's docs, as in the earlier gap note) produces the matrix; this cell scores it.
- Our LiDAR is PLY, so load it with `load_points` (same file, lines 126–137), which reads `.npy`/`.npz` and otherwise uses Open3D. Constants: `NUM_MESH_SAMPLES = 400_000`, `SEED = 0`.

#### N17 — Precision / recall / F-score at fixed metric thresholds (GOFish)
- **Source:** tuallen/GOFish @ 1a33e7a9ff73, `gofish/eval/fiord/observed_gt.py` lines 27 and 203–210, and `gofish/eval/fiord/mesh_metrics.py` lines 50–52. CC BY-NC 4.0.
- **Stage:** 6 and 7 (mesh accuracy against LiDAR, in metres)

```python
THRESHOLDS_M = (0.05, 0.10, 0.25, 0.30)
# [...]
def prf(d_pred_to_gt: np.ndarray, recall: dict[int, float]) -> dict:
    out = {}
    for threshold in THRESHOLDS_M:
        cm = int(round(threshold * 100))
        precision = float(np.mean(d_pred_to_gt < threshold)) if len(d_pred_to_gt) else 0.0
        out[f"P{cm}"], out[f"R{cm}"] = precision, recall[cm]
        out[f"F{cm}"] = 2 * precision * recall[cm] / (precision + recall[cm]) if precision + recall[cm] else 0.0
    return out
# [...]
    d_pred_to_gt = O.nearest_distances(pred, gt)
    d_gt_to_pred = O.nearest_distances(gt, pred)
    recall = {int(round(t * 100)): float(np.mean(d_gt_to_pred < t)) for t in O.THRESHOLDS_M}
```

**Notice to keep:** `# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.` / `# SPDX-License-Identifier: CC-BY-NC-4.0` / `# From tuallen/GOFish@1a33e7a gofish/eval/fiord/{observed_gt,mesh_metrics}.py`

**Adaptation notes**
- The thresholds are metres (5, 10, 25 and 30 cm). They mean something only after the mesh is in the LiDAR's metric frame, so report "n/a" for unconstrained (non-metric) parts.
- Phone LiDAR covers only part of the lodge. Restrict precision to samples inside the LiDAR cloud's bounding box, as GOFish's `C` crop does (`mesh_metrics.py` lines 54–56), and log both numbers to Pixeltable.

---

### Stage 7 — Mesh extraction and export

#### N18 — Build GOF's tetra-triangulation extension against current torch wheels (GOFish)
- **Source:** tuallen/GOFish @ 1a33e7a9ff73, `README.md` lines 49–56. CC BY-NC 4.0.
- **Stage:** 7 (prerequisite for `mesh.py`)

```bash
sudo apt install cmake libgmp-dev libcgal-dev
git clone https://github.com/autonomousvision/gaussian-opacity-fields ../gaussian-opacity-fields
git -C ../gaussian-opacity-fields checkout 5245b20e5d11acd6d1ff5af4b890dc2bedd99693
cd ../gaussian-opacity-fields/submodules/tetra-triangulation
sed -i 's/_GLIBCXX_USE_CXX11_ABI=0/_GLIBCXX_USE_CXX11_ABI=1/' cmake/FindTorch.cmake   # ABI of current torch wheels
export CPATH=/usr/local/cuda/include   # CUDA headers for the extension's C++ sources
cmake -DCMAKE_PREFIX_PATH="$(python -c 'import torch; print(torch.utils.cmake_prefix_path)')" . && make
pip install -e . && cd -
```

**Notice to keep:** `# Build steps from tuallen/GOFish@1a33e7a README.md — CC BY-NC 4.0; gaussian-opacity-fields is under the Gaussian-Splatting License.`

**Adaptation notes**
- molab has no `sudo apt`. Get `cmake`, `gmp` and `cgal-cpp` from pixi (conda-forge), and point `CPATH` at the pixi CUDA toolkit's `include`, not `/usr/local/cuda`.
- The `_GLIBCXX_USE_CXX11_ABI=1` sed is the non-obvious fix: current torch wheels use the new ABI. Run it once per session and cache the built wheel in the HF bucket, so later sessions skip the compile.

#### N19 — MILo train + mesh: quick, dense, and appearance-robust variants (MILo)
- **Source:** Anttwo/MILo @ 0c38aa65f8b7, `README.md` lines 70–74, 81–85, 258 and 263. Inria Gaussian-Splatting License.
- **Stage:** 7 (and 3)

```bash
# Training for an outdoor scene
python train.py -s ./data/Ignatius -m ./output/Ignatius --imp_metric outdoor --rasterizer radegs

# Saves mesh as PLY with vertex colors after training
python mesh_extract_sdf.py -s ./data/Ignatius -m ./output/Ignatius --rasterizer radegs
# Training with dense gaussians and better appearance model
python train.py -s ./data/Ignatius -m ./output/Ignatius --imp_metric outdoor --rasterizer radegs --dense_gaussians --decoupled_appearance

# Saves mesh as PLY with vertex colors after training
python mesh_extract_sdf.py -s ./data/Ignatius -m ./output/Ignatius --rasterizer radegs
# [...]
python train.py -s <PATH TO COLMAP DATASET> -m <OUTPUT_DIR> --imp_metric outdoor --rasterizer radegs --dense_gaussians --mesh_config highres --data_device cpu
python train.py -s <PATH TO COLMAP DATASET> -m <OUTPUT_DIR> --imp_metric indoor --rasterizer radegs --dense_gaussians --mesh_config veryhighres --decoupled_appearance --log_interval 200 --data_device cpu
```

**Notice to keep:** `# MILo commands from Anttwo/MILo@0c38aa6 README.md — Gaussian-Splatting License (Inria/MPII), non-commercial research and evaluation use only.`

**Adaptation notes**
- MILo assumes pinhole input. Run it on the `image_undistorter` output of the fisheye model, use `--imp_metric outdoor` for exterior/courtyard captures and `indoor` for interiors, and keep `--decoupled_appearance` for the exposure swings between rooms.
- `mesh_extract_sdf.py` must use the same mesh config as training (README line 302 WARNING). Training takes it as `--mesh_config <name>`, extraction as `--config <name>`. Carry it as one value through both subprocess calls.
- Environment: torch 2.3.1 on CUDA 11.8 (12.1 untested; `install.py` line 14). This conflicts with the torch 2.8 trainers, so MILo needs its own pixi environment.

#### N20 — MILo differentiable Gaussians-to-mesh API (MILo)
- **Source:** Anttwo/MILo @ 0c38aa65f8b7, `README.md` lines 423–431, 447–452 and 458–465. Inria Gaussian-Splatting License.
- **Stage:** 7 (extracting a mesh from any 3DGS-style Gaussians, for example GOFish's)

```python
surface_gaussians_idx = sample_gaussians_on_surface(
    views=train_cameras,
    means=means,
    scales=scales,
    rotations=rotations,
    opacities=opacities,
    n_max_samples=600_000,
    scene_type='indoor',
)
# [...]
delaunay_tets = compute_delaunay_triangulation(
    means=means,
    scales=scales,
    rotations=rotations,
    gaussian_idx=surface_gaussians_idx,
)
# [...]
mesh = extract_mesh(
    delaunay_tets=delaunay_tets,
    pivots_sdf=initial_pivots_sdf,
    means=means,
    scales=scales,
    rotations=rotations,
    gaussian_idx=surface_gaussians_idx,
)
```

**Notice to keep:** `# From Anttwo/MILo@0c38aa6 README.md (milo.functional) — Gaussian-Splatting License, non-commercial research and evaluation use only.`

**Adaptation notes**
- `initial_pivots_sdf` comes from `compute_initial_sdf_values(...)` (README lines 436–443). It needs a `render_func(view) -> {"render", "depth"}` and 3DGS-style `Camera`s. Those are pinhole, so render perspective crops from the fisheye-trained splat to supply them.
- Delaunay triangulation is slow. Run it once per checkpoint as its own cell, and persist `delaunay_tets` to scratch and HF.

#### N21 — Depth-normal grazing-angle filter + Open3D scalable TSDF fusion (PGSR) [SA]
- **Source:** zju3dv/PGSR @ de24f1a38b35, `render.py` lines 105–112, 125–135 and 149–152. PGSR license, with the Inria header.
- **Stage:** 7

```python
        if use_depth_filter:
            view_dir = torch.nn.functional.normalize(view.get_rays(), p=2, dim=-1)
            depth_normal = out["depth_normal"].permute(1,2,0)
            depth_normal = torch.nn.functional.normalize(depth_normal, p=2, dim=-1)
            dot = torch.sum(view_dir*depth_normal, dim=-1).abs()
            angle = torch.acos(dot)
            mask = angle > (80.0 / 180 * 3.14159)
            depth_tsdf[mask] = 0
# [...]
            pose = np.identity(4)
            pose[:3,:3] = view.R.transpose(-1,-2)
            pose[:3, 3] = view.T
            color = o3d.io.read_image(os.path.join(render_path, view.image_name + ".jpg"))
            depth = o3d.geometry.Image((ref_depth*1000).astype(np.uint16))
            rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
                color, depth, depth_scale=1000.0, depth_trunc=max_depth, convert_rgb_to_intensity=False)
            volume.integrate(
                rgbd,
                o3d.camera.PinholeCameraIntrinsic(W, H, view.Fx, view.Fy, view.Cx, view.Cy),
                pose)
# [...]
        volume = o3d.pipelines.integration.ScalableTSDFVolume(
            voxel_length=voxel_size,
            sdf_trunc=4.0*voxel_size,
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
```

**Notice to keep:** `// Copyright 2023-2024 3D Vision Group at the State Key Lab of CAD&CG, Zhejiang University. All Rights Reserved. Educational, research and non-profit use only; modifications must be open-source and non-commercial. (zju3dv/PGSR@de24f1a render.py)` / `# Copyright (C) 2023, Inria, GRAPHDECO research group — Gaussian-Splatting License.`

**Adaptation notes**
- The 80° grazing-angle cull removes depth that is unreliable on walls seen edge-on. That case is common in narrow lodge corridors, so keep it.
- `PinholeCameraIntrinsic` takes pinhole depth only. Fuse perspective re-renders, never raw fisheye depth. Set `voxel_size` and `max_depth` in metres after stage 6 (README default `--max_depth 10.0 --voxel_size 0.01`).
- Fold the stage 4 person masks into `view.mask` before fusion (the code zeroes masked depth at lines 120–121), so that walkers do not leave blobs in the mesh.

#### N22 — Keep the largest connected mesh clusters (PGSR) [SA]
- **Source:** zju3dv/PGSR @ de24f1a38b35, `render.py` lines 42–63. PGSR license, with the Inria header.
- **Stage:** 7 (clean-up before export)

```python
def post_process_mesh(mesh, cluster_to_keep=1):
    """
    Post-process a mesh to filter out floaters and disconnected parts
    """
    import copy
    print("post processing the mesh to have {} clusterscluster_to_kep".format(cluster_to_keep))
    mesh_0 = copy.deepcopy(mesh)
    with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Debug) as cm:
            triangle_clusters, cluster_n_triangles, cluster_area = (mesh_0.cluster_connected_triangles())

    triangle_clusters = np.asarray(triangle_clusters)
    cluster_n_triangles = np.asarray(cluster_n_triangles)
    cluster_area = np.asarray(cluster_area)
    n_cluster = np.sort(cluster_n_triangles.copy())[-cluster_to_keep]
    n_cluster = max(n_cluster, 50) # filter meshes smaller than 50
    triangles_to_remove = cluster_n_triangles[triangle_clusters] < n_cluster
    mesh_0.remove_triangles_by_mask(triangles_to_remove)
    mesh_0.remove_unreferenced_vertices()
    mesh_0.remove_degenerate_triangles()
    print("num vertices raw {}".format(len(mesh.vertices)))
    print("num vertices post {}".format(len(mesh_0.vertices)))
    return mesh_0
```

**Notice to keep:** same two notices as N21.

**Adaptation notes**
- Pure Open3D, so it runs in the notebook kernel. For a lodge with separate interior rooms, raise `cluster_to_keep` above 1, or the largest room wins and the others are deleted. Make it a slider value.
- Log `num vertices raw` and `num vertices post` as Pixeltable columns instead of prints.

---

### What is still missing after this pass

- **`.insv` demux and per-lens frame extraction (stage 1):** none of the five repos handles it. This is still our own ffmpeg cell.
- **HF I/O (stage 8):** none of the five repos touches Hugging Face, apart from GOFish and GGPS linking to their own HF dataset pages. Nothing to adopt.
- **Person and transient masks (stage 4):** only GGPS's sky mask (N14). None of the five repos masks people.
- **LiDAR-to-SfM registration fitting (stage 6):** GOFish ships fixed per-scene alignment matrices and only *scores* them (N16, N17). The ICP fit itself is still written from Open3D's documentation.
