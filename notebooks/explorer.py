# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo[recommended]>=0.25",
#     "polars>=1.30",
#     "numpy>=2.0",
#     "huggingface-hub>=1.0",
#     "plotly>=6.0",
#     "altair>=5.4",
# ]
# ///
# [LAW:one-source-of-truth] exception: molab installs only from this PEP 723 header, so it repeats a subset of
# pyproject.toml's dependencies.

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import json

    import altair as alt
    import marimo as mo
    import numpy as np
    import plotly.graph_objects as go
    import polars as pl
    from huggingface_hub import HfFileSystem, get_token
    return HfFileSystem, alt, get_token, go, json, mo, np, pl


@app.cell
def _(mo):
    mo.md("""
    # Cliff House — where we are, what we have, where we're going

    An explorer over what the pipeline and the MacBook have already produced, with **no model training**: the 360
    COLMAP solve of 2026-11-10 (8 clips), and Spirula's clip-033 work from 2026-11-09 (sparse model, dense clouds,
    splats). Every chart reads stage outputs from the private Hugging Face bucket; nothing here writes data.
    Plan for the full set of views: `docs/poses-explorer-plan.md`.
    """)
    return


@app.cell
def _(HfFileSystem, get_token, json, pl):
    BUCKET = "ojeromyo/frasier-cliff-house"
    POSES_FP = "9d611bc6c9a3d5f7"
    SPIRULA = "external/macbook-spirula/VID_20261109_174521_033_dataset"
    fs = HfFileSystem(token=get_token())

    def read_parquet(path):
        with fs.open(f"buckets/{BUCKET}/{path}", "rb") as f:
            return pl.read_parquet(f)

    cameras = read_parquet(f"stages/explore/{POSES_FP}/cameras.parquet")
    points = read_parquet(f"stages/explore/{POSES_FP}/points.parquet")
    pose_summary = json.loads(fs.read_text(f"buckets/{BUCKET}/stages/poses/{POSES_FP}/summary.json"))
    preview_manifest = json.loads(fs.read_text(f"buckets/{BUCKET}/{SPIRULA}/previews/manifest.json"))
    spirula_gauge = fs.read_text(f"buckets/{BUCKET}/{SPIRULA}/sparse/0/gauge.txt")
    spirula_rigs = fs.read_text(f"buckets/{BUCKET}/{SPIRULA}/sparse/0/rigs.txt")
    return (BUCKET, POSES_FP, SPIRULA, cameras, fs, points, pose_summary, preview_manifest, read_parquet,
            spirula_gauge, spirula_rigs)


@app.cell
def _(BUCKET, cameras, fs, pl, read_parquet):
    # Frame times come from the frames stage. A clip can have frames under more than one fingerprint (an older run),
    # so the table used is the one that holds every registered (lens, frame) of the clip — exactly one must.
    def _frames_for(clip):
        needed = cameras.filter(pl.col("clip") == clip).select(camera="lens", frame="frame")
        fits = []
        for path in fs.glob(f"buckets/{BUCKET}/stages/frames/*/{clip}/frames.parquet"):
            table = read_parquet(path.split(f"buckets/{BUCKET}/", 1)[1])
            if needed.join(table, on=["camera", "frame"], how="anti").is_empty():
                fits.append(table.with_columns(clip=pl.lit(clip)))
        if len(fits) != 1:
            raise ValueError(f"{clip}: {len(fits)} frames tables hold every registered frame; expected exactly one")
        return fits[0]

    all_frames = pl.concat([_frames_for(c) for c in sorted(cameras["clip"].unique())])
    clip_frames = all_frames.group_by("clip").agg(frames=pl.len())
    return all_frames, clip_frames


@app.cell
def _(mo):
    mo.md("""
    ## 1 · Assessment: where we are
    """)
    return


@app.cell
def _(cameras, clip_frames, mo, pl, pose_summary):
    _all_clips = ["VID_20261110_131538_036", "VID_20261110_131644_037", "VID_20261110_131804_038",
                  "VID_20261110_132141_039", "VID_20261110_132300_040", "VID_20261110_132328_041",
                  "VID_20261110_134257_042", "VID_20261110_141132_035"]
    status = (pl.DataFrame({"clip": _all_clips})
              .join(clip_frames, on="clip", how="left")
              .join(cameras.group_by("clip").agg(registered=pl.len()), on="clip", how="left")
              .with_columns(pl.col("registered").fill_null(0), short=pl.col("clip").str.slice(-3))
              .with_columns(in_main_model=pl.col("registered") > 0)
              .sort("short"))
    mo.vstack([
        mo.hstack([
            mo.stat(value=f"{pose_summary['registered_images']:,} / {pose_summary['total_images']:,}",
                    label="images placed in 3D", caption="8 clips of 2026-11-10, 360 only"),
            mo.stat(value=f"{pose_summary['points3D']:,}", label="3D points"),
            mo.stat(value=f"{pose_summary['mean_reprojection_error_px']} px", label="mean reprojection error"),
            mo.stat(value=f"{status['in_main_model'].sum()} / {status.height}", label="clips in the main model",
                    caption="039, 040 not joined yet"),
            mo.stat(value=f"{pose_summary['rig_baselines_m'][0] * 1000:.1f} mm", label="lens baseline (factory)",
                    caption="Spirula solved 63.7 mm on 033"),
        ], widths="equal"),
        mo.ui.table(status.select("short", "clip", "frames", "registered", "in_main_model"), selection=None,
                    label="Pipeline status per clip (frames, masks and training masks are done for all 8)"),
    ])
    return (status,)


@app.cell
def _(alt, mo, pl, status):
    _bars = (status.select("short", registered="registered", missing=pl.col("frames") - pl.col("registered"))
             .unpivot(index="short", variable_name="state", value_name="images"))
    mo.ui.altair_chart(
        alt.Chart(_bars).mark_bar().encode(
            x=alt.X("short:N", title="clip"), y=alt.Y("images:Q", title="images (both lenses)"),
            color=alt.Color("state:N", scale=alt.Scale(domain=["registered", "missing"],
                                                       range=["#2e7d32", "#c62828"])),
            tooltip=["short", "state", "images"]).properties(height=260, title="Images placed in 3D, per clip"))
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2 · What we can do with it — the use cases

    Status is today's honest state. Pick rows to read what each needs.
    """)
    return


@app.cell
def _(pl):
    use_cases = pl.DataFrame([
        (1, "Camera paths", "have", "poses", "Trajectory per clip in metres, speed over time — shown below."),
        (2, "Point cloud viewer / export", "have", "poses", "549 k coloured points; filter by error and track length — below."),
        (3, "Lens calibration report", "partial", "poses + Spirula", "Our fisheye models + rig; Spirula's rig disagrees on baseline (71.3 vs 63.7 mm)."),
        (4, "Measurements", "next", "poses + LiDAR", "Triangulate picked pixels; metric once LiDAR confirms scale."),
        (5, "Coverage / reshoot planner", "partial", "poses", "Top-down coverage heat map below (approximate level); map overlay needs #9."),
        (6, "Frame quality", "partial", "poses + frames", "Points seen per frame, sharpness — below; exclusion list next."),
        (7, "Dense reconstruction", "partial", "Spirula (033)", "Spirula's RoMa dense cloud for 033 exists (32 M points) — preview below; ours not run."),
        (8, "LiDAR registration", "next", "LiDAR scans", "24 SiteScape scans (~24 M points each) to align; confirms scale."),
        (9, "Levelling + georeferencing", "partial", "Spirula (033), GPS", "Spirula's 033 model is GPS-scaled and east/north-up; ours not yet."),
        (10, "Metric depth per frame", "next", "poses + depth model", "Monocular depth scaled by sparse points."),
        (11, "Perspective views", "next", "poses + frames", "Flat views from the fisheyes at any direction."),
        (12, "Labelled 3D points", "next", "poses + masks", "SAM 3 classes carried onto 3D points."),
        (13, "Placing new photos", "next", "poses", "Localise any new photo inside the model."),
        (14, "Camera tracking (USD)", "partial", "poses", "resolve/usd_scene.py exists; export from these poses next."),
        (15, "Stabilised / reframed video", "next", "poses + frames", "Smooth paths and reframes from known poses."),
        (16, "Plan geometry", "next", "levelled cloud", "Slices to floor outlines, planes to walls/floors/roof."),
        (17, "Scan-to-BIM (Cloud2BIM → IFC)", "next", "merged LiDAR / dense", "Slabs, walls, openings, spaces as an IFC proposal."),
        (18, "Gaussian splats", "partial", "Spirula (033)", "Spirula splat of 033: step 16 k done, 28 k of 50 k training on the MacBook — preview below."),
    ], orient="row", schema=["id", "use_case", "status", "uses", "what"])
    return (use_cases,)


@app.cell
def _(alt, mo, use_cases):
    _order = ["have", "partial", "next"]
    status_chart = mo.ui.altair_chart(
        alt.Chart(use_cases).mark_bar().encode(
            x=alt.X("count():Q", title="use cases"), y=alt.Y("status:N", sort=_order, title=None),
            color=alt.Color("status:N", scale=alt.Scale(domain=_order, range=["#2e7d32", "#f9a825", "#90a4ae"]),
                            legend=None),
            tooltip=["status", "count()"]).properties(height=120, title="Use cases by status (click a bar to filter)"))
    status_chart
    return (status_chart,)


@app.cell
def _(mo, pl, status_chart, use_cases):
    _picked = status_chart.value
    _shown = use_cases if _picked.is_empty() else use_cases.filter(
        pl.col("status").is_in(_picked["status"].unique().to_list()))
    use_case_table = mo.ui.table(_shown, selection="multi", page_size=18, label="Use cases")
    use_case_table
    return (use_case_table,)


@app.cell
def _(mo, use_case_table):
    _rows = use_case_table.value
    mo.md("\n".join(f"- **{r['id']}. {r['use_case']}** ({r['status']}, uses {r['uses']}): {r['what']}"
                    for r in _rows.iter_rows(named=True))
          if not _rows.is_empty() else "_Select use cases above to see what each needs._")
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3 · Our COLMAP model (8 clips of 2026-11-10)

    The solve's own frame, in metres via the factory lens baseline. **"Up" here is a hypothesis**: the axis of least
    spread of the camera centres (the walkthrough is roughly level), until gravity from telemetry levels it (use case 9).
    """)
    return


@app.cell
def _(cameras, np, pl, points):
    # Approximate levelling: principal axes of the camera centres; the least-spread axis is taken as up, signed so
    # most points sit below the cameras (ground and floors outnumber what is overhead).
    _c = cameras.select("x", "y", "z").to_numpy()
    _mean = _c.mean(0)
    _, _, _vt = np.linalg.svd(_c - _mean, full_matrices=False)
    _axes = _vt.copy()
    _p = points.select("x", "y", "z").to_numpy()
    if np.median((_p - _mean) @ _axes[2]) > np.median((_c - _mean) @ _axes[2]):
        _axes[2] = -_axes[2]
    _axes[1] = np.cross(_axes[2], _axes[0])

    def level(frame):
        xyz = (frame.select("x", "y", "z").to_numpy() - _mean) @ _axes.T
        return frame.with_columns(e=pl.Series(xyz[:, 0]), n=pl.Series(xyz[:, 1]), h=pl.Series(xyz[:, 2]))

    cams_l = level(cameras)
    pts_l = level(points)
    return cams_l, pts_l


@app.cell
def _(cams_l, mo, pts_l):
    clip_pick = mo.ui.multiselect(sorted(cams_l["clip"].unique()), value=sorted(cams_l["clip"].unique()),
                                  label="clips")
    error_range = mo.ui.range_slider(0.0, float(pts_l["error_px"].quantile(0.99)), step=0.05,
                                     value=[0.0, float(pts_l["error_px"].quantile(0.99))], label="point error (px)",
                                     show_value=True)
    min_track = mo.ui.slider(2, 20, value=3, label="min track length (images)", show_value=True)
    sample = mo.ui.slider(20_000, 300_000, step=20_000, value=120_000, label="points drawn", show_value=True)
    color_by = mo.ui.radio(["photo colour", "height", "error", "track length"], value="photo colour",
                           label="colour points by", inline=True)
    mo.vstack([mo.hstack([clip_pick, color_by], justify="start"), mo.hstack([error_range, min_track, sample])])
    return clip_pick, color_by, error_range, min_track, sample


@app.cell
def _(error_range, min_track, pl, pts_l, sample):
    pts_f = pts_l.filter(pl.col("error_px").is_between(*error_range.value), pl.col("track_length") >= min_track.value)
    pts_draw = pts_f.gather_every(max(1, -(-pts_f.height // sample.value)))
    return pts_draw, pts_f


@app.cell
def _(cams_l, clip_pick, color_by, go, mo, pl, pts_draw, pts_f):
    _colour = {"photo colour": [f"rgb({r},{g},{b})" for r, g, b in pts_draw.select("r", "g", "b").iter_rows()],
               "height": pts_draw["h"].to_list(), "error": pts_draw["error_px"].to_list(),
               "track length": pts_draw["track_length"].to_list()}[color_by.value]
    _fig = go.Figure([go.Scatter3d(
        x=pts_draw["e"], y=pts_draw["n"], z=pts_draw["h"], mode="markers", name="points",
        marker={"size": 1.2, "color": _colour, "colorscale": "Viridis", "opacity": 0.8,
                "showscale": color_by.value != "photo colour"})])
    for (_clip,), _path in (cams_l.filter(pl.col("clip").is_in(clip_pick.value), pl.col("lens") == "lens0")
                            .sort("frame").group_by("clip", maintain_order=True)):
        _fig.add_trace(go.Scatter3d(x=_path["e"], y=_path["n"], z=_path["h"], mode="lines", name=_clip[-3:],
                                    line={"width": 5}, text=[f"{_clip[-3:]} frame {f}" for f in _path["frame"]]))
    _fig.update_layout(height=760, scene={"aspectmode": "data"}, legend={"itemsizing": "constant"},
                       title=f"{pts_draw.height:,} of {pts_f.height:,} filtered points, camera paths (lens 0)")
    mo.ui.plotly(_fig)
    return


@app.cell
def _(alt, mo, pts_f):
    _sample = pts_f.select("error_px", "track_length").gather_every(max(1, pts_f.height // 50_000))
    _err = alt.Chart(_sample).mark_bar().encode(
        x=alt.X("error_px:Q", bin=alt.Bin(maxbins=60), title="reprojection error (px)"), y="count():Q"
    ).properties(height=200, width=420, title="Point error")
    _trk = alt.Chart(_sample).mark_bar(color="#6a1b9a").encode(
        x=alt.X("track_length:Q", bin=alt.Bin(maxbins=40), title="track length (images seeing the point)"),
        y="count():Q").properties(height=200, width=420, title="Track length")
    mo.hstack([mo.ui.altair_chart(_err), mo.ui.altair_chart(_trk)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4 · Coverage — hot and cold spots (use case 5, model frame)

    Top-down grid on the approximate level. Colour = how many images see the points in a cell (mean track length) or
    how many points it holds. Drag a box to list cells; low values are what a reshoot should cover. The map overlay
    comes once the model is georeferenced (use case 9).
    """)
    return


@app.cell
def _(mo):
    cell_m = mo.ui.slider(0.25, 4.0, step=0.25, value=1.0, label="cell size (m)", show_value=True)
    coverage_metric = mo.ui.radio(["mean track length", "points"], value="mean track length", label="colour by",
                                  inline=True)
    mo.hstack([cell_m, coverage_metric], justify="start")
    return cell_m, coverage_metric


@app.cell
def _(alt, cell_m, coverage_metric, mo, pl, pts_f):
    coverage = (pts_f.with_columns(ce=(pl.col("e") / cell_m.value).floor() * cell_m.value,
                                   cn=(pl.col("n") / cell_m.value).floor() * cell_m.value)
                .group_by("ce", "cn").agg(points=pl.len(), mean_track=pl.col("track_length").mean().round(2)))
    _field = "mean_track" if coverage_metric.value == "mean track length" else "points"
    coverage_chart = mo.ui.altair_chart(
        alt.Chart(coverage).mark_rect().encode(
            x=alt.X("ce:Q", bin=alt.Bin(step=cell_m.value), title="east-ish (m)"),
            y=alt.Y("cn:Q", bin=alt.Bin(step=cell_m.value), title="north-ish (m)"),
            color=alt.Color(f"{_field}:Q", scale=alt.Scale(scheme="turbo"), title=coverage_metric.value),
            tooltip=["ce", "cn", "points", "mean_track"])
        .properties(height=620, width=620, title=f"{coverage.height:,} cells of {cell_m.value} m"))
    coverage_chart
    return coverage, coverage_chart


@app.cell
def _(coverage, coverage_chart, mo, pl):
    _sel = coverage_chart.value
    _cells = (coverage.join(_sel.select("ce", "cn").unique(), on=["ce", "cn"], how="semi")
              if not _sel.is_empty() else coverage)
    mo.vstack([
        mo.hstack([mo.stat(value=f"{_cells.height:,}", label="cells selected"),
                   mo.stat(value=f"{(_cells['mean_track'] < 3).sum():,}", label="cells seen by < 3 images on average"),
                   mo.stat(value=f"{_cells['points'].sum():,}", label="points")], widths="equal"),
        mo.ui.table(_cells.sort("mean_track").head(200), selection=None, label="Coldest cells first (up to 200)"),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5 · Camera paths over time and frame quality (use cases 1 and 6)
    """)
    return


@app.cell
def _(all_frames, cams_l, np, pl):
    paths = (cams_l.filter(pl.col("lens") == "lens0")
             .join(all_frames.filter(pl.col("camera") == "lens0").select("clip", "frame", "t_ms", "sharpness"),
                   on=["clip", "frame"], how="inner")
             .sort("clip", "t_ms")
             .with_columns(step_m=np.sqrt(pl.col("e").diff() ** 2 + pl.col("n").diff() ** 2 + pl.col("h").diff() ** 2)
                           .over("clip"),
                           dt_s=(pl.col("t_ms").diff() / 1000).over("clip"))
             .with_columns(speed_ms=(pl.col("step_m") / pl.col("dt_s")).round(3), seconds=pl.col("t_ms") / 1000))
    return (paths,)


@app.cell
def _(alt, mo, paths, pl):
    _per_clip = paths.group_by("clip").agg(path_m=pl.col("step_m").sum().round(1),
                                           median_speed_ms=pl.col("speed_ms").median().round(2),
                                           duration_s=pl.col("seconds").max().round(0)).sort("clip")
    _brush = alt.selection_interval(encodings=["x"])
    speed_chart = mo.ui.altair_chart(
        alt.Chart(paths.drop_nulls("speed_ms")).mark_line(point=False).encode(
            x=alt.X("seconds:Q", title="seconds into clip"), y=alt.Y("speed_ms:Q", title="speed (m/s)"),
            color=alt.Color("clip:N", legend=alt.Legend(labelExpr="slice(datum.label, -3)")),
            tooltip=["clip", "frame", "seconds", "speed_ms"]).add_params(_brush)
        .properties(height=260, title="Rig speed over time — drag to select a window"))
    mo.vstack([mo.ui.table(_per_clip, selection=None, label="Path length and speed per clip"), speed_chart])
    return (speed_chart,)


@app.cell
def _(alt, mo, paths, speed_chart):
    _sel = speed_chart.value
    _frames = paths.join(_sel.select("clip", "frame"), on=["clip", "frame"], how="semi") if not _sel.is_empty() else paths
    mo.vstack([
        mo.ui.altair_chart(alt.Chart(_frames).mark_circle(size=18, opacity=0.6).encode(
            x=alt.X("sharpness:Q", title="frame sharpness (Laplacian variance)", scale=alt.Scale(type="log")),
            y=alt.Y("n_points:Q", title="3D points seen in the frame"),
            color=alt.Color("clip:N", legend=None), tooltip=["clip", "frame", "seconds", "sharpness", "n_points"])
            .properties(height=320, title=f"Frame quality — {_frames.height:,} frames (follows the time selection)")),
        mo.ui.table(_frames.sort("n_points").select("clip", "frame", "seconds", "sharpness", "n_points").head(100),
                    selection=None, label="Weakest frames first"),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 6 · The MacBook's Spirula work on clip 033 (2026-11-09)

    Copied as previews from `/Volumes/DoubleAught/Cliff House` (the sources stay on the MacBook; each preview is an
    even sample, ≤ 400 k points). Splat previews show Gaussian centres with opacity ≥ 0.1 in their base colour —
    a stand-in for a real splat render, not one.
    """)
    return


@app.cell
def _(mo, preview_manifest):
    preview_pick = mo.ui.dropdown({f"{k} — {v['rows']:,} pts sampled": k for k, v in preview_manifest.items()},
                                  value=next(f"{k} — {v['rows']:,} pts sampled" for k, v in preview_manifest.items()
                                             if k == "splat_step28000"), label="cloud")
    preview_points = mo.ui.slider(20_000, 400_000, step=20_000, value=150_000, label="points drawn", show_value=True)
    mo.hstack([preview_pick, preview_points], justify="start")
    return preview_pick, preview_points


@app.cell
def _(SPIRULA, go, mo, preview_manifest, preview_pick, preview_points, read_parquet):
    _cloud = read_parquet(f"{SPIRULA}/previews/{preview_pick.value}.parquet")
    _draw = _cloud.gather_every(max(1, -(-_cloud.height // preview_points.value)))
    _src = preview_manifest[preview_pick.value]
    _fig = go.Figure([go.Scatter3d(
        x=_draw["x"], y=_draw["y"], z=_draw["z"], mode="markers",
        marker={"size": 1.2, "opacity": 0.85,
                "color": [f"rgb({r},{g},{b})" for r, g, b in _draw.select("r", "g", "b").iter_rows()]})])
    _fig.update_layout(height=760, scene={"aspectmode": "data"},
                       title=f"{preview_pick.value}: {_draw.height:,} drawn — source {_src['source_bytes'] / 1e9:.2f} GB")
    mo.vstack([mo.md(f"Source: `{_src['source']}`"), mo.ui.plotly(_fig)])
    return


@app.cell
def _(mo, np, pose_summary, spirula_gauge, spirula_rigs):
    _ours = pose_summary["rig_baselines_m"][0] * 1000
    _gauge = {l.split()[0]: l.split()[1] for l in spirula_gauge.splitlines()
              if l and not l.startswith("#") and len(l.split()) == 2}
    # rigs.txt: "rig <member> <reference> qw qx qy qz tx ty tz frames spread_deg"
    _cam1 = next(l.split() for l in spirula_rigs.splitlines() if l.startswith("rig cam1"))
    _spirula_mm = float(np.linalg.norm([float(v) for v in _cam1[7:10]])) * 1000
    mo.vstack([
        mo.md("### Our solve vs Spirula's"),
        mo.ui.table([
            {"": "clips", "ours (2026-11-10)": "8 (035–042)", "Spirula (033)": "1 (033, 2026-11-09)"},
            {"": "images registered", "ours (2026-11-10)": f"{pose_summary['registered_images']:,} / {pose_summary['total_images']:,}",
             "Spirula (033)": "3,308 / 3,428 (its prep log: 120 unregistered)"},
            {"": "lens baseline", "ours (2026-11-10)": f"{_ours:.1f} mm (factory, held fixed)",
             "Spirula (033)": f"{_spirula_mm:.1f} mm (solved)"},
            {"": "levelled / georeferenced", "ours (2026-11-10)": "no (approximate level above)",
             "Spirula (033)": f"oriented={_gauge.get('oriented')}, metric={_gauge.get('metric')}, "
                              f"up={_gauge.get('up')}, scale={_gauge.get('scale')}"},
            {"": "dense / splat", "ours (2026-11-10)": "not run", "Spirula (033)": "RoMa dense; splat 16 k done, 50 k training"},
        ], selection=None),
        mo.callout(mo.md(f"The baselines disagree by **{abs(_ours - _spirula_mm) / _ours:.0%}**. One of them is wrong; "
                         "LiDAR (use case 8) settles which, and with it the scale of every measurement."), kind="warn"),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 7 · Where we're going

    1. **Join 039 (dining room) and 040 (gravel courtyard)** with retrieval-based cross-clip matching, then re-map.
    2. **Level and georeference our model** (use case 9) from telemetry gravity + GPS — check against Spirula's
       GPS-scaled 033 frame. Unlocks the map overlay of the coverage view.
    3. **Settle scale with LiDAR** (use case 8): 71.3 mm factory vs 63.7 mm Spirula.
    4. **Dense + mesh** (use case 7) on molab, then **plan geometry** (16) and **Cloud2BIM → IFC** (17).
    5. **Splats**: compare Spirula's 033 splat when its 50 k run finishes; train the 8-clip model on molab.
    """)
    return


if __name__ == "__main__":
    app.run()
