# Poses explorer: 22 uses of the data we already have, as one reactive marimo notebook

Status: **plan**, 2026-11-13. Nothing here is built yet.

Input: the poses stage output, `stages/poses/9d611bc6c9a3d5f7/` in the HF bucket. It holds the sparse model of the 8 360 clips of 2026-11-10 (global mapper, main `9c0587c`):

- 3,836 of 4,352 images registered, 548,933 points, 1.14 px.
- Clips 039 and 040 are their own models, not part of the main one.

Every use case below works from that output plus data already in the bucket or the dataset (the SiteScape LiDAR scans included). None needs a trained model (no splats, no NeRF).

## Library check (versions installed and inspected 2026-11-13, not assumed)

| Library | Version | What we use from it |
|---|---|---|
| marimo | (kernel) | `mo.ui.slider/range_slider/dropdown/multiselect/switch/radio/tabs/table/dataframe/data_explorer/altair_chart/plotly/anywidget`, `mo.ui.refresh`, `mo.stat`, `mo.hstack/vstack/accordion`, `mo.download` |
| wigglystuff | 0.5.40 | `ChartPuck`, `ChartSelect`, `ChartMultiSelect`, `HeatmapSelect`, `Slider2D`, `PlaySlider`, `FramePlayer`, `HoverZoom`, `Paint`, `AnnotationWidget`, `SortableList`, `ParallelCoordinates`, `ScatterWidget`, `ThreeWidget`, `CircularRangeSlider`, `Knob`, `CopyToClipboard`, `CellTour` |
| maplibre (py-maplibregl) | 0.3.6 | `maplibre.ipywidget.MapWidget` (anywidget, so reactive in marimo), open basemaps, terrain, sky, 3D extrusions |
| lonboard | 0.17.0 | `PointCloudLayer`, `HeatmapLayer`, `H3HexagonLayer`, `PathLayer`, `TripsLayer`, `ScatterplotLayer`, `ColumnLayer` (deck.gl via anywidget; GeoArrow from Polars/DuckDB) |
| altair, plotly, polars, polars-st, duckdb (spatial) | in the project env | charts, frames, spatial SQL, GeoParquet |
| open3d, pdal, shapely | in the project env (conda-forge) | Cloud2BIM's 3D/2D geometry; LiDAR reading and merging |
| Cloud2BIM | upstream `VaclavNezerka/Cloud2BIM` (MIT); fork `jacobm85/Cloud2BIM` (MIT, adds LAS/LAZ and a web UI) | scan-to-BIM: point cloud → IFC (use case 17). Not vendored: pinned by commit, licence notice kept |
| ifcopenshell, scikit-image | **not in the env yet** (fork pins ifcopenshell 0.8.1, scikit-image 0.25) | IFC writing, reading and validation; morphological masks. Added through pixi when use case 17 is built |

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

## The 22 use cases

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

### 17. Scan-to-BIM: point cloud → IFC with Cloud2BIM

Turn a building point cloud into an IFC model (slabs, walls, openings, rooms) automatically, then review and correct it in the notebook. References: Cloud2BIM, [arXiv 2503.11498v2](https://arxiv.org/abs/2503.11498v2); code at [jacobm85/Cloud2BIM](https://github.com/jacobm85/Cloud2BIM), a fork of [VaclavNezerka/Cloud2BIM](https://github.com/VaclavNezerka/Cloud2BIM), both MIT.

What it does (paper §2, checked against the fork's README):

1. Thin the cloud to a minimum spacing (`dilution_factor`; the paper pre-thins in CloudCompare to *d*<sub>min</sub> = 1–2.5 cm).
2. Detect slabs from the z-height histogram: bins ≥ 50 % of the peak (`max_n_points_array` = 0.5, `z_step` = 0.05 m). Floor and ceiling surfaces are paired into slabs. 2D hulls come from a density histogram with dilation and erosion (`dilation_meters`, `erosion_meters` = 1 m), Suzuki–Abe contours and Douglas–Peucker simplification.
3. Split the cloud into storeys between slabs, with 10 cm clearance.
4. Segment walls from a horizontal section at 90–100 % of storey height (`z_section_boundaries`):
   - build a density mask, take contours and merge collinear segments (`angle_tolerance` = 3°);
   - pair opposite faces (adding a virtual face if one is missing), compute the wall axis, and snap endpoints (`snapping_distance`);
   - PCA rotation handles buildings that aren't axis-aligned.
5. Detect openings: each wall is rotated into the xz-plane, and low-density gaps in the x and z histograms are classed as doors or windows by sill height, aspect ratio and width.
6. Build zones (`IfcSpace`) as closed polygons from the actual wall faces.
7. Write IFC with IfcOpenShell. The paper writes IFC4 ADD2 TC1; the fork's README says IFC 2x3. Verify against the pinned commit.

**Inputs we have, and the gap each one has:**

| Candidate input | What it is | Fit for Cloud2BIM |
|---|---|---|
| SiteScape LiDAR (`source/lidar/2026-11-09/*.ply`, 24 scans, ~24 M coloured points each) | phone LiDAR, one local frame per scan | **Best first input.** It needs the scans merged into one frame first (the LiDAR pair alignment already on the MacBook brief), then converted PLY → XYZ or LAS (PDAL), levelled (use case 9's gravity), and thinned. Phone-LiDAR noise is above the paper's terrestrial scanners, so expect missed openings |
| Dense photogrammetry cloud (use case 7) | millions of points from our poses | Usable once levelled and scale-confirmed (use cases 8 + 9). Untested by the paper, which uses terrestrial laser scans only |
| Sparse cloud (`points3D.bin`, 549 k points, whole property inside and out) | what exists today | Too sparse for wall-face pairing; useful only to smoke-test the pipeline end to end |

**Known limits that apply to the Cliff House** (paper §3.4):
- straight walls only (curves are approximated);
- rectangular openings only;
- one ceiling height per storey (no mezzanines or steps);
- furniture occlusion causes false or missed openings;
- stairs are not reproduced.

Outdoor areas are out of scope. Clip them to the building footprint (use case 16) first.

**Pipeline stage** (molab, CPU): `stages/bim/<fp>/`.
- The fingerprint is the input cloud's fingerprint + the Cloud2BIM commit + the full parameter set (Tables 5–6) + module code.
- Outputs: `model.ifc`, element tables (walls, slabs, openings, zones) as GeoParquet in the property frame, and the intermediate z-histogram and 2D masks for review.
- The IFC is a **projection / proposal**, never authoritative state (architecture rule). Corrections flow back as `agent_edit` proposals with `expected_revision`.

**Visualizations:**
- the z-histogram with detected floor and ceiling bins (altair; the 50 % threshold drawn as a rule);
- the 2D density mask before and after dilation/erosion, with contours overlaid;
- detected wall segments over the section mask, coloured by thickness and pairing status;
- per-wall elevation (xz) histograms with detected openings boxed;
- zone polygons on the MapLibre basemap (after use case 9) with area labels;
- the IFC model itself in 3D (`ThreeWidget` fed by IfcOpenShell geometry: walls, slabs, openings and spaces as separate toggleable groups);
- a comparison against use case 16's plane hypotheses and against LiDAR (per-wall deviation).

**Interactive:**
- a parameter panel (`mo.ui.form` or `mo.ui.dictionary`) for the Tables 5–6 parameters, with sensible bounds; submitting it reruns the stage under a new fingerprint;
- a `Knob` for `angle_tolerance`, and `Slider2D` for (`dilation_meters`, `erosion_meters`) on a cheap in-notebook preview of the mask before the full run;
- a `HeatmapSelect` on the density mask to inspect a cell's points;
- a `ChartSelect` on the wall list to highlight walls in 3D and on the map;
- a `SortableList` to accept or reject detected openings, and `EdgeDraw` to correct a wall axis; corrections are saved as proposals;
- a `mo.ui.table` of elements (type, length, thickness, height, openings), plus `mo.download` for the IFC.

**Done (machine-checkable):**
- the IFC opens in IfcOpenShell and passes `ifcopenshell.validate` with no schema errors;
- entity counts (`IfcWall`, `IfcSlab`, `IfcOpening`, `IfcSpace`) match the element tables;
- every `IfcSpace` is a closed polygon;
- wall lengths are compared with LiDAR measurements (use case 8), and the deviation is reported per wall, not assumed.

### 18. Gaussian splats (Spirula)

Spirula's clip-033 splat exists: step 16 k is done, and 50 k is training on the MacBook.

- **View:** the real render in SuperSplat, and a Gaussian-centre preview in the explorer.
- **Next:** an 8-clip splat trained on molab.

### 19. Site terrain model (DTM)

The ground around the house as a terrain surface, for site analysis: grading, drainage, slope, and access to the hillside.

- **Method:** Poux `lidar-ground-to-dtm`. Ground classified with a cloth filter, thinned and indexed, graded against survey points, written as a DTM raster.
- **Input:** outdoor parts of the dense cloud or the SiteScape scans, georeferenced (use case 9).
- **Visualizations:** hillshade and slope maps on MapLibre; a profile line tool (`EdgeDraw`) giving an elevation chart.
- **Done:** a DTM raster plus its residuals against any surveyed points, reported.

### 20. Accessibility audit

Clear width, turning space and reach through the building, as a numbered issue list on the plan.

- **Method:** Poux `wheelchair-accessibility-audit` (distance transform, morphological opening, connected components).
- **Input:** floor-level slice of the levelled interior cloud (use cases 9 and 16).
- **Visualizations:** issue markers on the floor plan; a width heat map; a `SortableList` triage of issues.
- **Done:** every issue has a location, a measured value and the rule it fails.

### 21. Egress / walking-distance map

Walking distance to the nearest exit from every floor point, dead-end corridors, and what-if blocked doors.

- **Method:** Poux `evacuation-distance-map` (multi-source Dijkstra over a 16-neighbour grid).
- **Input:** a floor occupancy grid from use case 16, and exits from use case 17's openings.
- **Visualizations:** a distance field on the plan; routes; a `multiselect` to block doors and re-solve live.
- **Done:** distances are monotone along routes. A blocked door changes only the cells routed through it.

### 22. Splat → textured mesh

Convert a trained splat into a solid textured mesh for Blender, Resolve and BIM context.

- **Method:** Poux `gaussian-splat-to-mesh`: filter by opacity and scale, densify, Poisson-mesh, bake the texture. A prior adaptation on a basement splat kept 370,781 of 751,619 Gaussians by opacity.
- **Input:** Spirula's clip-033 splat now; ours later.
- **Visualizations:** splat vs mesh side by side (`ThreeWidget`); opacity and scale filter sliders with a kept-count chart.
- **Done:** the mesh's bounds fall within the splat's. Kept counts are reported per filter.

## Methods source: Florent Poux's published code

For use cases 5, 7, 12, 16 and 17–22, the methods come from Florent Poux's open code:

- **[`3d-data-materials`](https://github.com/florentPoux/3d-data-materials):** MIT code. Its kit **datasets are not MIT**, so we don't vendor them and use only our own scans.
- **[`point-cloud-processing`](https://github.com/florentPoux/point-cloud-processing), [`3d-reconstruction-depth-anything`](https://github.com/florentPoux/3d-reconstruction-depth-anything):** MIT.
- **[`3D-Data-Science`](https://github.com/florentPoux/3D-Data-Science):** the book code, dual-licensed: book owners, otherwise CC BY-NC 4.0. This project is non-commercial.

Code reused from these keeps its licence notice and attribution. The book's prose and the video transcripts are read locally and never copied into this public repository.

| Need | Poux method | Use case |
|---|---|---|
| thresholds from the data | nearest-neighbour spacing: RANSAC distance = min + std of mean k-NN distance; normal radius = 3 × mean spacing | all |
| level and local origin | `wall-thickness-to-ifc` `level_scan` (floor/ceiling plane bisector; SVD refit) | 9, 16, 17 |
| per-point shape features | PCA eigen-features: planarity, linearity, verticality | 12, 16, 17 |
| planes kept apart | multi-RANSAC + keep the largest DBSCAN cluster per plane | 16, 17 |
| rectangular patches | Open3D `detect_planar_patches` (treads, risers, wall faces as oriented boxes) | 16, 17 (stairs) |
| wall thickness | density-peak faces → pairing → 25 cm cells, Theil-Sen per face, bootstrap interval → `IfcWall`, read back | 17 (complements Cloud2BIM's fixed thickness parameters) |
| floor plan and openings | wall raster → skeleton → vector lines → DXF; openings as unseen stretches | 16, 17 |
| footprint | DBSCAN → alpha shape → polygon | 16, 19 |
| terrain | cloth ground filter → DTM | 19 |
| accessibility, egress | distance transform, morphology; multi-source Dijkstra | 20, 21 |
| labels in 3D | lift, fuse and vote 2D labels across cameras | 12 |
| splat → mesh | opacity and scale filter → Poisson → baked texture | 22 |

Known gaps:
- **Avoid the book's numpy `ransac_plane`:** it computes `d` from the un-normalised normal. Use Open3D's or the depth-anything SVD-refit version.
- **No cylinder or line RANSAC exists in his code.** Balusters and handrails need an explicit line or circle fit, documented as not Poux.

---

## Build order (by dependency)

1. **Loader + shared controls,** then 1, 2, 3, 6: pure reads of the poses we have.
2. **9 (georef):** unlocks every map view (5, 13, 16).
3. 5, 11, 12, 14, 15: local compute on existing data.
4. **Pipeline stages on molab:** 7 (dense), 10 (depth), 8 (LiDAR). Then their explorer views.
5. 4, 13, 16: these benefit from 8 (confirmed scale) and 9 (map).
6. **17 (Cloud2BIM) with Poux wall thickness (T8), then 20–21** on its plan: after the LiDAR scans are merged into one frame and levelled (8, 9), with 16's footprint used to clip outdoor points. Smoke-test it first on the sparse cloud so the stage and the views exist before the real input is ready.
7. **19 (terrain)** once outdoor points are georeferenced; **22 (splat → mesh)** can start now on Spirula's 033 splat.

Prerequisite worth doing first for 5 and 9: join **039** (dining room) and **040** (gravel courtyard) into the main model with retrieval-based cross-clip matching. Until then their coverage shows up as cold.

## Verification for the notebook as a whole

- `marimo check notebooks/poses_explorer.py` is clean.
- `python notebooks/poses_explorer.py` runs headless against the bucket and exits 0.
- Each section asserts its "done" criterion in code, so a regression fails loudly instead of drawing a wrong chart.
