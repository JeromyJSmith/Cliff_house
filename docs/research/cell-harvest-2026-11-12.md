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
