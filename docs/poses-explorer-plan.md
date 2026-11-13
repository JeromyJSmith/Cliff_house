# Poses explorer: 16 uses of the poses we already have, as one reactive marimo notebook

Status: **plan**, 2026-11-13. Nothing here is built yet.

Input: the poses stage output, `stages/poses/9d611bc6c9a3d5f7/` in the HF bucket. It holds the sparse model of the 8 360 clips of 2026-11-10 (global mapper, main `9c0587c`):

- 3,836 of 4,352 images registered, 548,933 points, 1.14 px.
- Clips 039 and 040 are their own models, not part of the main one.

Every use case below works from that output plus data already in the bucket. None needs a trained model (no splats, no NeRF).

## Library check (versions installed and inspected 2026-11-13, not assumed)

| Library | Version | What we use from it |
|---|---|---|
| marimo | (kernel) | `mo.ui.slider/range_slider/dropdown/multiselect/switch/radio/tabs/table/dataframe/data_explorer/altair_chart/plotly/anywidget`, `mo.ui.refresh`, `mo.stat`, `mo.hstack/vstack/accordion`, `mo.download` |
| wigglystuff | 0.5.40 | `ChartPuck`, `ChartSelect`, `ChartMultiSelect`, `HeatmapSelect`, `Slider2D`, `PlaySlider`, `FramePlayer`, `HoverZoom`, `Paint`, `AnnotationWidget`, `SortableList`, `ParallelCoordinates`, `ScatterWidget`, `ThreeWidget`, `CircularRangeSlider`, `Knob`, `CopyToClipboard`, `CellTour` |
| maplibre (py-maplibregl) | 0.3.6 | `maplibre.ipywidget.MapWidget` (anywidget, so reactive in marimo), open basemaps, terrain, sky, 3D extrusions |
| lonboard | 0.17.0 | `PointCloudLayer`, `HeatmapLayer`, `H3HexagonLayer`, `PathLayer`, `TripsLayer`, `ScatterplotLayer`, `ColumnLayer` (deck.gl via anywidget; GeoArrow from Polars/DuckDB) |
| altair, plotly, polars, polars-st, duckdb (spatial) | in the project env | charts, frames, spatial SQL, GeoParquet |

Base maps: open tiles only (OpenFreeMap / OSM vector styles, MapLibre demo terrain). No Google tiles. Aerial imagery from an open source (e.g. a state or USGS orthophoto WMTS) is chosen and verified when built.

## Architecture (so the explorer stays smooth)

- **Its own notebook,** `notebooks/poses_explorer.py`. It reads stage outputs from the bucket and never writes source data. `workbench.py` stays the pipeline.
- **One loader cell:** `pycolmap.Reconstruction` becomes four Polars frames, and every visualization reads only these:
  - `cams` (image, clip, lens, frame, t_ms, centre xyz, view direction, reproj error, n_obs);
  - `pts` (point id, xyz, rgb, error, track length);
  - `obs` (point id, image: the track table);
  - `gps` (from `stages/telemetry/*/*/gps.parquet`).
- **One coordinate source of truth:** the model frame (metres, hint scale). Geographic views go through **one** versioned transform: `stages/georef/<fp>/transform.json`, built in use case 9. No view invents its own alignment. Every table carries `coordinate_frame_id`.
- **Heavy compute is a pipeline stage, not explorer code.** Dense MVS, depth and LiDAR alignment write fingerprinted stages through `workbench.py` on molab. The explorer only displays them.
- **Reactivity pattern used everywhere:** one or two controls (clip multiselect, time range, threshold) feed derived Polars frames. Every chart reads those frames, and a selection in any chart (`altair_chart`/`plotly` selection, `ChartSelect`, lasso) is itself a value that filters the others.

## Shared controls (top of the notebook)

- `clips`: `mo.ui.multiselect` (default: all registered clips).
- `time`: `mo.ui.range_slider` over each clip's seconds. `PlaySlider` animates it.
- `lens`: `mo.ui.radio` (lens0, lens1, both).
- `decimate`: `mo.ui.slider` for the point-cloud sample size, so the browser stays fast.
- A `CellTour` (wigglystuff) walks a first-time viewer through the sections.

---

## The 16 use cases

Each entry gives: what it is → the data it uses → at least two visualizations → interactive pieces → a machine-checkable "done".

### 1. Camera paths (the capture trajectory)

The rig's path through the property, per clip, in metres and with time.

- **Data:** `cams` (frame centres), `t_ms` from the frames stage.
- **Visualizations:**
  - lonboard `PathLayer` per clip, coloured by clip, with a `TripsLayer` animated by `PlaySlider`;
  - an altair speed-vs-time line (finite differences of centres);
  - a plotly 3D path with view-direction cones.
- **Interactive:** brush a time window on the speed chart, and the 3D path and map highlight that segment. `FramePlayer` shows the frame at the cursor.
- **Done:** path length and median speed per clip are in a `mo.ui.table`. The table matches `cams` row counts, and every registered frame appears exactly once.

### 2. Point cloud viewer and export

549k coloured points, viewable and downloadable.

- **Data:** `pts`.
- **Visualizations:**
  - lonboard `PointCloudLayer` (RGB);
  - the same layer coloured by error or track length (toggle);
  - a histogram of reprojection error;
  - a histogram of track length.
- **Interactive:**
  - `range_slider` on error and on min track length filters the cloud live;
  - `mo.download` exports the filtered cloud as PLY, LAS or GeoParquet;
  - `CopyToClipboard` gives the bucket path.
- **Done:** an exported PLY re-reads with the same point count and bounds as the filtered frame.

### 3. Lens calibration report

The X5's two fisheye models and their rig transform, as a reusable calibration.

- **Data:** `cameras.bin`, `rigs.bin`, the factory `lens.json`.
- **Visualizations:**
  - a distortion-curve plot (radius in → radius out) for each lens;
  - a calibration vs factory delta table;
  - a residual heatmap over the image circle (`HeatmapSelect`: click a cell to list its worst observations);
  - a vector field of mean residual direction.
- **Interactive:** a lens toggle, and a `Knob` for the residual-bin size.
- **Done:** the calibration JSON is written and versioned. The baseline equals 71.3 mm, ±0.1 mm.

### 4. Measurements

Pick a point in two or more frames, triangulate it, and measure distances.

- **Data:** `cams` poses + intrinsics; triangulation via pycolmap.
- **Visualizations:**
  - two `HoverZoom` frames side by side, with the selected pixel's epipolar curve drawn on the second;
  - a plotly 3D scene with measured segments;
  - a running `mo.ui.table` of measurements.
- **Interactive:**
  - `AnnotationWidget` or `Paint` to click points;
  - `mo.ui.dropdown` to pick frames from `cams` filtered by what can see the first point;
  - a "snap to sparse point" `switch`.
- **Done:** a known factory length (the 71.3 mm lens baseline, or a LiDAR-measured edge once use case 8 exists) re-measures within a stated tolerance. Every result is labelled "scale hint" until LiDAR confirms it.

### 5. Coverage report and reshoot planner

Hot and cold spots: which places have too few views, or views from only one direction.

- **Data:** `pts` + `obs` (views per point, angular spread of viewing rays), `cams`.
- **Visualizations:**
  - lonboard `H3HexagonLayer` or `HeatmapLayer` on the MapLibre basemap (after use case 9), coloured by view count or angular spread;
  - the same grid in model space as a top-down altair heatmap;
  - per-clip contribution bars;
  - a 3D extruded view (`ColumnLayer` heights = deficit).
- **Interactive:**
  - a `ChartSelect` lasso on the top-down grid lists the cold cells and the frames that nearly see them;
  - `Slider2D` sets the target (min views × min angle);
  - a `SortableList` orders cold cells into a reshoot shot list, exportable as GeoJSON or KML.
- **Done:** cell counts sum to the filtered point count. The reshoot list round-trips through GeoJSON.

### 6. Frame quality

Which frames are weak (blur, few features, high error), so they can be dropped from training.

- **Data:** `cams` (n_obs, reproj error) + frames-stage `sharpness` + masks `ignored_fraction`.
- **Visualizations:**
  - `ParallelCoordinates` across sharpness, n_obs, error and ignored fraction;
  - a scatter (`ScatterWidget`) of sharpness vs n_obs;
  - a per-clip ridgeline (`RidgelineChart`) of error.
- **Interactive:**
  - brushing any axis filters a `mo.ui.table` of frames, with thumbnails in `FramePlayer`;
  - a "write exclusion list" button saves `stages/frame_quality/<fp>/exclude.parquet`.
- **Done:** the exclusion list is keyed by frame id. Its count equals the brushed selection.

### 7. Dense reconstruction (classic photogrammetry)

A dense cloud, then a mesh, then a textured mesh, with no training.

- **Data:** poses + undistorted perspective images.
- **Pipeline stage** (molab GPU): COLMAP `image_undistorter` (fisheye → pinhole), then COLMAP patch-match or OpenMVS `DensifyPointCloud`, then `ReconstructMesh`, then `TextureMesh`. Output: `stages/dense/<fp>/`.
- **Visualizations:**
  - the dense cloud in lonboard;
  - the mesh in `ThreeWidget`;
  - a sparse vs dense point-density comparison by area;
  - stage progress bars.
- **Interactive:** a decimation slider, and wireframe and texture toggles.
- **Done:** the mesh is watertight-or-reported. Its area and bounds are within the sparse cloud's bounds.

### 8. LiDAR registration

Align the photo model to the LiDAR scan (`source/lidar`) to confirm scale and pick up the scan's frame.

- **Data:** `pts`; the LiDAR cloud via PDAL.
- **Pipeline stage:** coarse alignment (GPS from use case 9, or picked correspondences), then ICP with scale (PDAL or Open3D). Output: `stages/lidar_align/<fp>/transform.json` + residuals.
- **Visualizations:**
  - an overlay of both clouds, coloured by source;
  - a residual-distance heatmap on the photo cloud;
  - an ICP convergence chart;
  - the scale factor with its uncertainty.
- **Interactive:** manual correspondence picking (`AnnotationWidget` on two views) seeds the alignment. A `switch` shows before and after.
- **Done:** residual RMS and scale are recorded. The registration stays a hypothesis with its residuals, not "survey truth".

### 9. Levelling and georeferencing

Find "up" from the IMU and put the model on the map from GPS.

- **Data:** telemetry `gravity.parquet` and `gps.parquet` (every clip has fixes: 8–145 each; consumer GPS drifts indoors), `cams` centres at matching times.
- **Computation:** a robust (RANSAC) similarity transform from camera centres to GPS east-north-up, outdoor fixes weighted higher. The levelling rotation comes from gravity. The one georef transform is written to `stages/georef/<fp>/`.
- **Visualizations:**
  - a MapLibre map with the GPS fixes and the transformed camera path;
  - a residual-per-fix bar chart (indoor fixes visibly worse);
  - a before/after tilt indicator.
- **Interactive:** a `switch` per clip to include or exclude its fixes, and a `range_slider` on fix accuracy. The transform refits live.
- **Done:** fit residual is reported per fix. The transform is versioned. Property coordinates stay out of the public repo (bucket only).

### 10. Metric depth for every frame

Dense depth maps scaled to metres by the sparse points.

- **Data:** frames + `obs` (sparse depth per frame).
- **Pipeline stage:** a monocular depth model (e.g. Depth Anything V2) per frame, then a per-frame scale and shift fit to the sparse depths. Output: `stages/depth/<fp>/`.
- **Visualizations:**
  - frame / depth / error side by side (`HoverZoom`);
  - a scatter of fitted vs sparse depth with R²;
  - a per-clip scale-stability chart.
- **Interactive:** a frame picker driven by `FramePlayer`, and a colormap and range `range_slider`.
- **Done:** per-frame fit error stays under a threshold. Frames failing it are listed.

### 11. Perspective views

Flat views at any direction from the fisheye images.

- **Data:** calibrated fisheye + pose. `cliff_house.equirect` exists for remapping.
- **Visualizations:**
  - a live perspective render;
  - a fisheye frame with the view's footprint overlaid;
  - a "look at this 3D point" render.
- **Interactive:** a `Slider2D` for yaw and pitch, a `Knob` for field of view, a clip/frame `PlaySlider`, and a "point at sparse point" picker.
- **Done:** rendering a view straight at a sparse point puts its projection at the image centre within 1 px.

### 12. Labelled 3D points (SAM 3 masks in 3D)

Carry the 2D mask classes (people, gear, pictures, …) onto the 3D points, then query in 3D.

- **Data:** `obs` + the masks and training-masks stages.
- **Visualizations:**
  - the point cloud coloured by majority label;
  - a label-agreement histogram;
  - for a picked 3D point, every frame that sees it in a `FramePlayer` with its mask overlaid.
- **Interactive:**
  - `multiselect` of labels;
  - an agreement `slider`;
  - "mark something in one frame (`Paint`) → find it in every other frame" through the track table.
- **Done:** label counts reconcile with the mask stage. A marked region resolves to a set of points and frames.

### 13. Placing new photos

Localise any new photo (phone, inspection, future capture) inside the model.

- **Data:** the model + a new image (`mo.ui.file`).
- **Computation:** SIFT on the new photo, matched to the nearest registered frames (image retrieval), then pycolmap absolute pose (PnP + RANSAC).
- **Visualizations:**
  - the photo's camera placed in the 3D scene and on the map;
  - matched features drawn between the photo and its nearest frame;
  - an inlier-count gauge.
- **Interactive:** upload, then the result. A `TangleSlider` sets the RANSAC threshold.
- **Done:** a held-out registered frame, re-localised as if new, lands within a stated distance and angle of its solved pose.

### 14. Camera tracking for video and VFX

Cameras as USD for DaVinci Resolve or Blender: overlay CG, labels or plans on the real footage.

- **Data:** poses → `cliff_house.resolve.usd_scene` (exists, with `tests/test_usd_scene.py`).
- **Visualizations:**
  - a USD camera list with timing;
  - a reprojection check (sparse points drawn over the frame through the exported camera);
  - a shot timeline (altair).
- **Interactive:** pick a clip and range, then `mo.download` the USD.
- **Done:** a sparse point reprojected through the exported USD camera lands within 1 px of its COLMAP projection (the property `usd_check` already guards).

### 15. Stabilised or reframed video

Smooth flythroughs and 360 reframes from known poses.

- **Data:** `cams` path + frames.
- **Visualizations:**
  - raw vs smoothed path (plotly 3D);
  - angular jitter before and after (altair);
  - a reframed preview strip.
- **Interactive:**
  - a smoothing `Knob`;
  - a `BezierCurve` or `CurveEditor` for a custom look-direction curve over time;
  - `PlaySlider` playback;
  - export of a frame list.
- **Done:** jitter (deg/s RMS) drops by the reported factor. The output frame count equals the selected range.

### 16. Plan geometry

Floor-plan outlines from height slices, and planes for walls, floors and roof. These are the architecture's "geometry hypotheses".

- **Data:** `pts`, levelled by use case 9.
- **Computation:**
  - height slices to 2D polylines (DuckDB spatial: `ST_ConcaveHull` per slice);
  - RANSAC plane fitting to labelled planes, with area and normal.
- **Visualizations:**
  - a slice viewer (top-down);
  - a plane list with an extruded 3D view;
  - a MapLibre footprint overlay (after use case 9);
  - wall-length annotations.
- **Interactive:**
  - a slice height `slider` + thickness `Knob`;
  - a `SortableList` to accept or reject plane hypotheses;
  - `EdgeDraw` to correct an outline by hand.
- **Done:** accepted geometry is written as a **proposal** (`agent_edit` with `expected_revision`), never straight to authoritative state. Its outline closes, and its area is reported.

---

## Build order (by dependency)

1. **Loader + shared controls,** then 1, 2, 3, 6: pure reads of the poses we have.
2. **9 (georef):** unlocks every map view (5, 13, 16).
3. 5, 11, 12, 14, 15: local compute on existing data.
4. **Pipeline stages on molab:** 7 (dense), 10 (depth), 8 (LiDAR). Then their explorer views.
5. 4, 13, 16: these benefit from 8 (confirmed scale) and 9 (map).

Prerequisite worth doing first for 5 and 9: join **039** (dining room) and **040** (gravel courtyard) into the main model with retrieval-based cross-clip matching. Until then their coverage shows up as cold.

## Verification for the notebook as a whole

- `marimo check notebooks/poses_explorer.py` is clean.
- `python notebooks/poses_explorer.py` runs headless against the bucket and exits 0.
- Each section asserts its "done" criterion in code, so a regression fails loudly instead of drawing a wrong chart.
