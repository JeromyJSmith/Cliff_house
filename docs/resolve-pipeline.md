# DaVinci Resolve pipeline — per-project plan (draft for owner review)

Status: **plan + one-clip proof**. Nothing in §6 runs on the full footage until the owner approves this document.

This is the Resolve side of the digital-twin pipeline in [`SPEC.md`](SPEC.md). It is written the same way: stages
with inputs, outputs, fingerprints and an acceptance check that blocks what depends on them. It is
**project-agnostic**: the code (`src/cliff_house/resolve/`) never names a project, a path or a clip. Everything
project-specific is in one TOML file per project under [`configs/resolve/`](../configs/resolve/). A new project is
a new config file, run through the same commands in the same order.

## 1. Division of labour and the one rule

| Machine | Owns |
|---|---|
| This MacBook (Resolve Studio 21.2, licensed) | telemetry, remux, **everything Resolve** (this document) |
| molab (cloud GPU) | frames, SfM masks (SAM 3), poses, splats, meshes — `stages/frames/` onward |

The bucket is the interface. Resolve reads the remux stage's lossless per-lens MP4s (`stages/remux/<fp>/<clip>/cam0.mp4`,
`cam1.mp4`; Resolve does not read `.insv`) and writes `stages/resolve/<pass>/<fingerprint>/<clip>/<lens>/…`.

**The rule:** every pass is tagged `use = reconstruction` or `use = analysis` (`PASSES` in
[`passes.py`](../src/cliff_house/resolve/passes.py), enforced by a test).

- `reconstruction`: **masks only** (person/operator/drone-part mattes). These may be handed to SfM and splat
  training as ignore-masks.
- `analysis`: depth, edges, normals, vegetation index, false colour, stills. These are layers for CAD tracing and
  quality review. They **never** go into reconstruction. A monocular network's depth on a fisheye frame is a
  picture of what the network guessed, not a measurement, and feeding it to SfM or a splat would put an
  unmeasured prior into geometry that SPEC §1 says must be evidence-constrained.

## 2. Contracts shared by every stage

- **Fingerprint** = SHA-256 of (input file SHA-256, pass code version, pass parameters), first 16 hex. The code
  version hashes `passes.py` (read once per run) and, for Magic Mask, the click author and its template grade.
  Changing anything gives a new fingerprint, so new outputs land beside old ones. Nothing is overwritten, and a
  fingerprint whose `pass.json` exists is skipped (idempotent restart).
- **Layout** (identical on the 2TB mirror `/Volumes/2TB/CliffHouse/stages/` and in the bucket `stages/`):

  ```
  resolve/<pass>/<fingerprint>/<clip>/<lens>/
      000000.png … 000364.png   one file per SOURCE frame, 0-based (frame i is at t_ms = i·1001/30 for 29.97 fps)
      frames.parquet            frame, t_ms, file, dtype, mean, coverage
      pass.json                 pass, use, fingerprint, source path+sha256+frames, params, code version,
                                Resolve version, timeline name, render dir, seconds, acceptance
  resolve/_render/<pass>/<fingerprint>/<clip>/<lens>/…   Resolve's own renders (intermediates, see §8)
  resolve/bootstrap/<fp>/record.json                       settings as Resolve read them back
  ```

- **Formats**: mattes are 8-bit single-channel PNG, 255 = subject (person/operator). Continuous analysis layers
  (depth) are 16-bit single-channel PNG. All are full source resolution (3840×3840 fisheye, unrectified), so pixel
  (x, y) of an output is pixel (x, y) of the source frame.
- **One timeline per (pass, fingerprint, lens)**, named `<pass>-<fingerprint>-<lens>`, holding exactly one clip.
  Grades and Fusion comps live on timeline items, so passes cannot contaminate each other. Inputs are imported
  once into the media-pool bin `inputs/<clip>` and Resolve's frame count is checked against the remux manifest's
  packet count before anything renders.
- **Acceptance** is computed by the code and written into `pass.json`. A failed check exits non-zero, and nothing
  downstream may read that fingerprint.
- **Upload** (after acceptance): `hf` upload of the fingerprint directory to the bucket path above. Never
  `hf sync --delete`. Outputs are additive.

## 3. Machine setup (once per Mac) — verified 2026-11-12

| Setting | Required | How verified | Result |
|---|---|---|---|
| Product / version | Resolve **Studio** 21.2 | `resolve.GetProductName()`, `GetVersionString()` | DaVinci Resolve Studio 21.2.0.6; Fusion 21.2.0.0006 |
| External scripting | **Local** | external Python connects via `127.0.0.1` and is **refused** via the Mac's LAN address (Network mode would accept it) | Local ✓ |
| Media Storage, first location | the project's `storage_root` | `config.dat` `Site.1.FS.1.Root`; `MediaStorage.GetMountedVolumeList()[0]` | `/Volumes/2TB/CliffHouse/DaVinci` ✓ |
| MCP servers | `davinci-resolve` (Blackmagic ResolveMCP, 18 tools) and `davinci-resolve-tools` (samuelgursky v5.2.7, 37 tools) | both answered `get_resolve_status` / `get_version` | both connected ✓ |
| AI IntelliSearch Faster | installed (Extras) | `README.md` §Studio and AI Scripting APIs | installed per owner; not exercised yet |

No scripting call sets Preferences (only whole preference presets can be saved and loaded), so these two
preferences are a GUI step the bootstrap **checks** and refuses to run without. The Media Storage check is in
`bootstrap.preflight`. External scripting is checked implicitly, because the bootstrap cannot connect otherwise.

## 4. Stage R0 — project bootstrap (per project)

`pixi run python -m cliff_house.resolve.bootstrap configs/resolve/<project>.toml`
([`bootstrap.py`](../src/cliff_house/resolve/bootstrap.py))

1. Preflight: Studio edition; Media Storage's first location is `storage_root`; the drive is mounted.
2. Library: switch to `project.library` if the config names one. A library cannot be created by script (GUI gap
   G1). An empty value uses the open library.
3. Project: load it, or `CreateProject(name, <storage_root>/ProjectMedia)` so Resolve-generated media (proxies, AI
   outputs) lands on the project drive.
4. Settings: create every `*Location` directory, apply each setting that differs **one at a time**
   (`SetSettings` stops at the first failure and hides which), then read all of them back. Any mismatch stops the
   run. If the project already holds timelines and the frame rate differs, it stops: Resolve cannot change a frame
   rate once media is on a timeline, and the remedy is a new project name, never mutating this one.
5. Save; write `resolve/bootstrap/<fp>/record.json`.

**Acceptance:** every configured setting reads back equal, and a second run reports `changed: []`.

**Proof (2026-11-12):** created `frasier-cliff-house`; read back 3840×3840 square pixels, 29.97 fps, output =
timeline resolution, cache `…/DaVinci/CacheClip`, gallery `…/DaVinci/.gallery`, project media
`…/DaVinci/ProjectMedia`, render cache off, proxy/optimized media off, `davinciYRGB`. Second run: `changed: []`.
Record: `/Volumes/2TB/CliffHouse/stages/resolve/bootstrap/1c30acf114159b79/record.json`.
Observed after the proof: Magic Mask's tracking cache (`AlgoCache`) and project backups also land under
`storage_root`. Nothing was written to the internal disk except the project library entry (G1).

## 5. What 21.2 can drive by script — research summary

Sources: Resolve's own 21.2 stubs and docs through the `davinci-resolve` MCP (`get_scripting_api`,
`get_scripting_docs` README / FusionTools / FusionToolReference / DCTLReadme, `get_whats_new`), plus live calls.
"Live" means it was run in this session.

| Capability | Script surface (21.2) | Parameters scriptable? | Verdict |
|---|---|---|---|
| Project create, settings, timelines from clips, import | `ProjectManager.CreateProject(name, mediaLocation)`, `Project.SetSetting`, `MediaPool.ImportMedia`, `CreateTimelineFromClips` | yes | **live ✓** |
| Render image sequences | `SetCurrentRenderFormatAndCodec` (PNG 8/16, TIFF 8/16, EXR half/float with PIZ/ZIP/DWAA…, DPX), `SetRenderSettings`, `AddRenderJob`, `StartRendering`, `GetRenderJobStatus` | yes | **live ✓** |
| **Magic Mask (Color page)** | `TimelineItem.CreateMagicMask('F'\|'B'\|'BI')`, `RegenerateMagicMask()` | tracking only. The **click** that says *what* to mask has no API | Fresh item: `CreateMagicMask` → **False** (live). With a click authored into a grade (`.drx`) and applied by `Graph.ApplyGradeFromDRX`: **tracks all frames** (live) |
| Magic Mask (Fusion `MagicMask` tool) | tool inputs (Mode, matte finesse, track buttons) | points live in `Strokes` (`MagicMaskStrokes`), which has no script form; `SaveSettings` shows an empty `MagicMaskStrokes {}` | points UI-only |
| **Depth Map** | Fusion `DepthMap` tool (all controls by ID: Mode Faster/Better, preview, levels, isolation, post-filter) | **yes** | **live ✓** (§6.2) |
| Depth Map / Relight / Edge Detect / False Color / PanoMap / Lens Distortion as ResolveFX | `TimelineItem.AddEffect('ofx', id)` with ids from `Resolve.GetEffectsList()` (all present on 21.2) | **no**. `Effect` only has enable/index/Fusion-comp accessors; OFX parameters cannot be set or read | defaults only. Use the Fusion tool or a DCTL instead |
| Relight normals | Fusion `Relight` with `OutputSurfaceMap = 1` (surface/normal map) or `OutputToAuxiliaryNormals` | yes | documented; not run |
| Edges | Fusion `Filter` tool (Sobel / Laplacian), or a DCTL (`transform(... __TEXTURE__ p_TexR …)` + `_tex2D` gives neighbour access) | yes | documented; not run |
| VARI / ExG vegetation, Sobel magnitude, false colour | DCTL written with `write_dctl`, applied with `Graph.SetLUT(1, "MCP/<name>.dctl")` | yes. Parameters are baked into the file (`DEFINE_UI_PARAMS` defaults), which also suits fingerprinting | documented; not run |
| Stills | `Timeline/TimelineItem/MediaPoolItem.ExportFrame(frameOffset, {outputType:'file', filePath, maxDimension, roi…})`, `GrabStill`, `GalleryStillAlbum.ExportStills(…, 'drx'\|'png'…)` | yes | `ExportFrame` used through MCP `get_image` ✓ |
| AI IntelliSearch | `MediaPoolItem/Folder.AnalyzeForIntellisearch(identifyFaces, isBetterMode)`, `Project.ResetIntellisearchAnalysis()` | analysis yes; **searching** the index has no API | partial |
| Background tasks | `Resolve.DisableBackgroundTasksForCurrentResolveSession()` | yes | use before long renders |
| Headless | `Resolve -nogui`: scripting APIs work, no UI dialogs can block a script | yes | candidate for unattended runs |

What 21.x added that matters here (`get_whats_new`): Depth Map up to 6× faster (21.0), Relight 2× faster, "Render
Magic Mask in place as an external matte" (21.0, a GUI action; `MediaPool.GetClipMatteList` can read the result),
Insta360 I-Log colour management, VR180/360 immersive timelines, scripted IntelliSearch analysis.

## 6. Passes

All passes run per (clip, lens) with
`pixi run python -m cliff_house.resolve.passes configs/resolve/<project>.toml <pass> <clip> <lens> [--click f,u,v]`.

### 6.1 `magic_mask` — person/operator matte (`use = reconstruction`)

- **Input:** remux lens MP4 + one **click** `(source frame, u, v)` on the subject (`u, v` from the top-left, 0–1).
- **Recipe:** author a Magic Mask 2 grade holding that click from a captured template (MIT `magic-mask-author.js`,
  samuelgursky/davinci-resolve-mcp `resolve-advanced/vendor/drx-codec`, commit `331f769`) → `ApplyGradeFromDRX`
  (gradeMode 0) → `CreateMagicMask("BI")` tracks the whole clip → render twice: the masked region forced to black
  (CDL slope 0, offset 0) and to white (offset 1). The matte is **m = white − black**, exact for any pixel because
  the node mixes `m·corrected + (1−m)·input`. A unit test proves the recovery, soft edges included.
- **Params in the fingerprint:** click, track direction, render depth, author + template hashes.
- **Output:** `000000.png…` 8-bit L, 255 = subject; `frames.parquet` with per-frame coverage.
- **Acceptance:** frame count = remux packet count; every frame has a non-empty mask; coverage within the
  expected band for the subject (owner sets the band per project after the first review; ~8 % of cam0 for the
  operator on clip 041 per SPEC stage 3).
- **Known limit (live finding):** one click selects the *object under the click*, not the whole person. The proof
  click on the operator's jacket masked the jacket on every frame, but not the trousers, boots, hands, face or the
  yellow strap (§7). A whole-person matte needs several positive clicks. The author handles exactly one, so
  multi-click authoring (decoding more stroke entries in the grade) is the next engineering step. Until then,
  **SAM 3 in molab (SPEC stage 3) stays the primary SfM mask.** Resolve's matte is a second opinion to union with
  or check against it, and the review layer.
- **Where clicks come from:** for now a human picks one frame per clip/lens (it is data in the run's parameters,
  not a code change). Proposed later: take the click from molab's SAM 3 detection (the centroid of the `person` mask
  on the sharpest frame), which removes the human step.

### 6.2 `depth_map` — relative depth (`use = analysis`)

- **Recipe:** Fusion comp on the clip: `MediaIn1 → DepthMap(Mode=Better, DepthMapPreview=1) → MediaOut1`. Render
  PNG RGB16 and keep one channel (the map is grey).
- **Output:** 16-bit L PNG per frame, 1.0 = near, 0.0 = far, normalised **per frame**. It is not metric and not
  consistent across frames or lenses.
- **Acceptance:** frame count = packet count; every frame non-constant; visual spot-check of 3 frames per clip.
- **Known limit:** the network expects rectilinear images. On the 3840² circular fisheye, the black area outside
  the image circle is read as "near", and the up-looking lens (ceiling) gives a soft, low-detail map. A better
  analysis input is a rectilinear view: PanoMap / Lens Distortion on the timeline, or the undistorted views molab
  makes. That becomes a separate pass with its own fingerprint, not a change to this one.

### 6.3 Proposed passes (not yet implemented; all `use = analysis`)

| Pass | Recipe (all scriptable per §5) | Output | Acceptance |
|---|---|---|---|
| `edges_sobel` | DCTL with `_tex2D` 3×3 Sobel on luma → magnitude, applied by `SetLUT(1, …)` | 16-bit L | count; non-constant; spot-check |
| `vegetation_vari` / `vegetation_exg` | DCTL: VARI = (G−R)/(G+R−B), ExG = 2g−r−b on chromaticity, mapped to 16-bit with a fixed offset/scale baked into the file | 16-bit L | count; values span the band on a vegetated clip |
| `normals_relight` | Fusion `Relight`, `OutputSurfaceMap=1` | 16-bit RGB | count; spot-check |
| `false_color` | DCTL or ResolveFX False Color (defaults only) | 8-bit RGB | exposure review only |
| `stills_review` | `ExportFrame` at molab's selected `t_ms` for a contact sheet | JPEG | one per selected frame |
| `intellisearch_index` | `Folder.AnalyzeForIntellisearch(identifyFaces=False, isBetterMode=False)` on `inputs/` | Resolve DB only (no export API) | job completes; owner searches in the GUI |

## 7. Proof on clip 041 (2026-11-12)

Input: `VID_20261110_132328_041`, remux fingerprint `0dbe10ed483a5f74`. `cam0.mp4` (downward lens, sees the
operator) and `cam1.mp4` (upward lens) are 3840×3840 H.264 at 29.97 fps, 365 frames each. Resolve reads both as 365
frames, and both SHA-256 values match the remux manifest. Both lenses were imported. The two proof passes ran on
**cam0**, the lens that carries the operator and the room geometry. A one-frame Depth Map check on cam1 showed the
coarse ceiling map described in §6.2.

PROOF_RESULTS

## 8. Open decisions for the owner

1. **Approve the rule and the layout** in §1–2 (analysis layers never enter reconstruction; per-fingerprint paths).
2. **Magic Mask's role:** keep SAM 3 as the SfM mask and Resolve Magic Mask as a cross-check (recommended until
   multi-click authoring exists), or invest now in multi-click authoring.
3. **Clicks:** a human-picked click per clip/lens, or clicks derived from molab's SAM 3 detections.
4. **Render intermediates** (`resolve/_render/…`, two 8-bit renders per matte pass; ~4–10 GB per lens-clip at
   3840²) are reproducible from the fingerprint. Keep them, or delete them after acceptance?
5. **Project library on the 2TB drive (G1):** add it once in Project Manager, then set `project.library` in the
   config. Today the project lives in the "Local Database" library on the internal disk. Its media, caches,
   stills and backups are already on 2TB.
6. **Full run scope:** all 8 clips × 2 lenses × which passes, and whether depth runs on fisheye or rectilinear
   views.

## 9. GUI-only gaps (no 21.2 scripting call does these)

| # | Step | Frequency | Workaround in this pipeline |
|---|---|---|---|
| G1 | Add a project library (database) | once per drive | the bootstrap switches to it by name once added |
| G2 | Preferences: External scripting = Local; Media Storage order | once per machine | the bootstrap verifies both and stops if they are wrong |
| G3 | Place Magic Mask points (Color palette or Fusion viewer) | per subject | author the click into a grade (`.drx`) and apply it. One click only today |
| G4 | Set ResolveFX (OFX) parameters | per effect | use the Fusion tool (Depth Map, Relight, Filter) or a DCTL |
| G5 | Search an IntelliSearch index | per query | analysis is scriptable; searching is in the GUI |
| G6 | "Render Magic Mask in place as an external matte" | per clip | the two-render matte (§6.1); `GetClipMatteList` reads mattes made in the GUI |
| G7 | Generate proxies or optimized media | per clip | not needed (lossless remux plays; both are disabled in the bootstrap) |
| G8 | Dismiss a modal dialog (e.g. an unsaved project on switch) | rare | run headless (`-nogui`) for unattended jobs; save before switching |
