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
| This MacBook (Resolve Studio 21.2, licensed; Apple M3 Max, 128 GB) | telemetry, remux, **everything Resolve** (this document), and **SAM 3 masks** (owner direction, 2026-11-12) |
| molab (cloud GPU) | frames, poses, splats, meshes — `stages/frames/` onward, reading the masks from the bucket |

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

## 2a. What feeds molab, and how

Only the mask classes (§6.1) cross into molab's reconstruction stages:

- **Paths:** people: `stages/resolve/mask_people/<fp>/<clip>/<lens>/` (per frame, `frames.parquet`, `pass.json`).
  Landing gear: `stages/static_mask/<fp>/<lens>/mask.png` (one image for every frame of that lens, with
  `static_mask.json`). molab reads only fingerprints whose `acceptance.ok` is true. The final ignore-mask for a
  frame is the union of the people mask for that frame and the static mask of its lens.
- **Join:** a molab frame (clip, lens, `t_ms`) maps to the Resolve frame `round(t_ms · 30 / 1001)` at 29.97 fps.
  Both index source frames from 0, and the lens names are the remux's `cam0`/`cam1`.
- **Convention:** 255 = subject, 0 = keep. COLMAP's mask images are the opposite (black = ignored), so molab inverts
  and thresholds (`colmap_mask = 255 if m < 128 else 0`) when it writes COLMAP masks. Unioned with SAM 3's person
  mask, it can only remove more pixels from SfM, never add any.
- Every other pass (`use = analysis`) is for this Mac's CAD-tracing and review tools, and molab must not read it.
  The `use` field in `pass.json` is the machine-readable form of this rule.

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
`pixi run python -m cliff_house.resolve.passes configs/resolve/<project>.toml <pass> <clip> <lens>`. Mask passes
read their clicks from the config's `[prompts.<pass>]`, never from the command line, so every run can be rebuilt
from the config and the code.

### 6.1 Mask classes (`use = reconstruction`)

The owner's targets are two named classes, each with its own prompts, method and acceptance check in the project
config:

| Class | What | Method | Prompts | Acceptance (config `[acceptance.<pass>]`) |
|---|---|---|---|---|
| **people** | every person, the operator included | **primary: SAM 3 with the text prompt `person`, run on this Mac** (owner decisions, 2026-11-12: SAM 3 primary; SAM 3 runs locally, not in molab). Secondary: Resolve `mask_people` (Magic Mask, several clicks unioned, below), a cross-check whose union with SAM 3 can only remove more pixels | `[prompts.mask_people]`: per clip/lens, clicks `[source_frame, u, v]` on each garment or body part | mask on every frame where people are expected (`every_frame`), median coverage within `coverage = [min, max]` (clip 041 cam0: 4–15 %, operator ≈ 8 % per SPEC) |
| **landing gear** (`static_mask landing_gear`) | the aircraft's white landing-gear struts and feet, plus other white rigid rim parts (lens-guard edge) | **one static mask per lens**, derived once from all clips ([`static_mask.py`](../src/cliff_house/static_mask.py)) | `[static_masks.landing_gear]`: the lenses that see it (`cam0`) and those that must not (`cam1`) | the mask is present and whiter than its surroundings in **every** clip's median; per-frame check on 24 frames per clip; empty on the absent lens |

**Recommendation for the landing gear: the static per-lens mask, not tracking.** The gear is bolted to the camera,
so its pixels do not move. Measured on clip 041 cam0 (§7), Magic Mask tracking the two feet was worse on every
count. It recovered a median 13 % of the static mask (IoU 0.13), usually only the feet, never the full struts. It
varied from frame to frame (0.14–1.5 % coverage) and lost the right foot entirely on some frames. At the 95th
percentile, 10 % of its mask spilled onto nearby walls and pictures. The static mask is one 3840² PNG per lens. It
needs no Resolve and no model, costs about 10 minutes per rig, and is checked against all 8 clips. It must be
re-derived only if the rig changes (another drone, camera re-mounted, gear replaced), and its fingerprint covers
every input file, so a new clip set gives a new mask beside the old one. Not covered yet: the aircraft's **dark**
body arc at the top rim of both lenses. It is rigid too, but not white, so it needs the same static method with a
darkness criterion as its own class.

**People: SAM 3 primary, run on this Mac; Magic Mask as cross-check.** Owner decisions, 2026-11-12: a whole person
is masked in one step by a text-prompted segmenter, and it runs here, not in molab. **Not set up yet:** the
project's pixi environment has no PyTorch or SAM 3, and the gated `facebook/sam3` weights are not downloaded (the
project account has access). Following SPEC §7.4, it gets its own pixi environment, not changes to the default
one, and runs on the M3 Max GPU (PyTorch MPS). It writes `stages/masks/<fp>/<clip>/<lens>/…` like every other
stage. SAM 3 with `person` returns the full silhouette (clothes, belt, hands, anything
carried) and picks up anyone else who walks into frame, with no clicks. From a script, Resolve's Magic Mask takes
points only. Each point selects one object, so a person built from clicks has seams at belts, straps, hands and
accessories (measured in §7). The Resolve pass stays as a review layer and an optional union.

**Resolve `mask_people` (Magic Mask).** Recipe per click: author a Magic Mask 2 grade holding the click from a captured template
(MIT `magic-mask-author.js`, samuelgursky/davinci-resolve-mcp `resolve-advanced/vendor/drx-codec`, commit
`331f769`) → `ApplyGradeFromDRX` (gradeMode 0) on that click's own timeline (`<pass>-<fp>-<lens>-k<i>`; applying
a grade replaces the whole node graph, so clicks cannot share an item) → `CreateMagicMask("BI")` tracks the whole
clip → render twice, the masked region forced to black (CDL slope 0, offset 0) and to "white" (offset 1). Resolve
clamps the offset at ~0.5 of full scale, so the white level is **measured** from the renders (B − A in the fully
masked core). Matte = (white − black) / level, which is exact because the node mixes `m·corrected + (1−m)·input`.
The 8-bit renders at level ≈ 0.5 give ~7 bits of precision. Then the union (per-pixel max) is taken over clicks. A
unit test proves the matte recovery, soft edges included.

- **Why several clicks:** one Magic Mask click selects the *object under the click*. The first proof click on the
  operator's jacket masked the jacket on every frame (2.8 % of the frame), but not the trousers, boots, hands, face
  or yellow strap. The click author handles one click per grade, so each click is tracked separately (cost scales
  with the number of clicks). Multi-click authoring inside one grade would cut that cost and is the next
  engineering step.
- **Params in the fingerprint:** the clicks, track direction, render depth, author and template hashes.
- **Output:** `000000.png…` 8-bit L, 255 = subject; `frames.parquet` with per-frame coverage.
- **Where clicks come from:** today a person picks them on one frame per clip/lens; they are config data, not code.
  Proposed: derive them from the SAM 3 `person` masks made on this Mac (one click per connected part on the sharpest
  frame), which removes the human step.
- **Relation to SAM 3:** SAM 3 is the primary person mask (decided). Resolve's matte is a cross-check and can be
  unioned with it; a union only removes more pixels from SfM.

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
| `splat_render_qa` | the cliffhouse "Gaussian Splat" OFX (`ofx.com.cliffhouse.GaussianSplat`, source `~/Developer/resolve-splat-ofx` at `d8c3f3b`, Metal) as a Fusion tool on a comp beside the matching source frame: `plyFile` = molab's splat, camera `positionX/Y/Z` and `rotationX/Y/Z` (yaw/pitch/roll in degrees; +z forward, x right, y down) from the SfM pose of that frame, `fovY`, `output` 0 colour / 1 depth / 2 coverage, plus `shDegree`, `scaleModifier`, `nearClip`; its Output goes to MediaOut1. As a Fusion tool every input is settable by script (`SetInput`), unlike edit-page OFX (G4) | colour, depth and coverage renders per chosen frame (currently 1920×1080 float); side-by-side or difference against the footage | QA/presentation only, `use = analysis`, never fed to reconstruction. Coverage shows holes; colour difference against the frame shows splat error. Limits: **pinhole camera only** today (fisheye is planned), so compare against a rectilinear view of the frame (PanoMap / Lens Distortion) until the fisheye camera exists. Errors are logged to `~/Library/Logs/GaussianSplat.log` (Fusion has no OFX message suite), so the pass must check that log. Waits for molab's splats |
| `intellisearch_index` | `Folder.AnalyzeForIntellisearch(identifyFaces=False, isBetterMode=False)` on `inputs/` | Resolve DB only (no export API) | job completes; owner searches in the GUI |

## 7. Proof on clip 041 (2026-11-12)

Input: `VID_20261110_132328_041`, remux fingerprint `0dbe10ed483a5f74`. `cam0.mp4` (downward lens, sees the
operator) and `cam1.mp4` (upward lens) are 3840×3840 H.264 at 29.97 fps, 365 frames each. Resolve reads both as 365
frames, and both SHA-256 values match the remux manifest. Both lenses were imported. The two proof passes ran on
**cam0**, the lens that carries the operator and the room geometry. A one-frame Depth Map check on cam1 showed the
coarse ceiling map described in §6.2.

| Pass | Fingerprint | Frames out | Acceptance | Time | Output size | Render intermediates |
|---|---|---|---|---|---|---|
| `depth_map` cam0 | `64f681af1176a76e` | **365 / 365**, 3840×3840 16-bit L | ok: every frame non-constant | 160 s | 5.3 GB | 8.3 GB |
| `magic_mask` cam0 (earlier single-click pass, before the mask classes), click on the jacket (frame 165, u 0.488, v 0.124) | `dd36a6b20c25e55a` | **365 / 365**, 3840×3840 8-bit L | ok: mask on 365/365 frames; coverage 2.0–4.0 % (median 2.8 %) | 338 s (track ≈ 90 s + two renders) | 81 MB | 16 GB |
| **landing gear, static** (`static_mask`) cam0 / cam1 | `379006cbe2bfcc41` / `62a3985973ae0d83` | one 3840² mask per lens | ok: cam0 present in 8/8 clips (min contrast 31.6), per-frame 186/192, coverage 4.65 %; cam1 empty as required | ≈ 10 min, both lenses, all 8 clips | < 1 MB | none |
| landing gear, tracked (`mask_landing_gear_tracked`, 2 clicks on the feet) cam0 | `29f3d7580cc357aa` | **365 / 365** | ok by its own check (mask on every frame), but see the comparison below | 729 s | ≈ 70 MB | 32 GB |
| people, Resolve cross-check (`mask_people`, 4 clicks: jacket, trousers, boots, head) cam0 | `17ec183c3b0fb611` | **365 / 365** | ok by its band: mask on every frame, median coverage 4.6 % (3.7–6.7 %), inside 4–15 %, but **visibly incomplete** (below) | 1427 s | ≈ 80 MB | 64 GB |

People, Resolve cross-check, checked by eye on frames 0, 165 and 300. The four tracked clicks give jacket,
trousers and part of the head, but they leave the black tool belt between jacket and trousers, holes for the chest
strap and the device on it, the hands and keys, one boot on frames 0 and 300, and a dark sleeve on frame 300.
Filling enclosed holes plus a 61 px closing fixes the strap and device holes and part of the belt (coverage
4.5 % → 4.8 %), but it cannot add parts no click selected. Its acceptance band passed although the mask is
incomplete, so a coverage band alone is not enough: SAM 3's acceptance must also include the visual check of
those parts. This is why SAM 3 `person` is the primary people mask. Review image:
`_proof/2026-11-12/041-cam0-mask_people-17ec183c3b0fb611-raw-vs-closed.jpg`.

Landing gear, static vs tracked, per frame over all 365 frames of clip 041 cam0 (static mask as reference,
`compare_with_tracked`): IoU median 0.13 (p05 0.03, p95 0.29); recall median 0.13; tracked mask outside the gear
("leak") median 0, p95 0.105; tracked coverage 0.14–1.5 % against a static 4.65 %. On the frames I checked by eye
(0, 120, 165, 250, 364), the static mask covers both struts and feet on every frame. The tracked mask covers mostly
the feet, misses the right foot on frame 364, and on frame 250 sits on a picture on the wall.

Outputs: `/Volumes/2TB/CliffHouse/stages/resolve/{depth_map/64f681af1176a76e,magic_mask/dd36a6b20c25e55a,mask_landing_gear_tracked/29f3d7580cc357aa}/VID_20261110_132328_041/cam0/`
and `/Volumes/2TB/CliffHouse/stages/static_mask/{379006cbe2bfcc41,62a3985973ae0d83}/` (superseded first run:
`c5f1b625916a7a3e`, `989295cbb9a3b548`, same masks but `NaN` in the JSON).
Contact sheets I checked by eye (they show footage, so they stay off the public repo):
`/Volumes/2TB/CliffHouse/stages/resolve/_proof/2026-11-12/`.

What the frames show:

- **Depth** (frames 0, 165, 364): the operator, the nearby sofa and the walls read near (bright), and the floor and
  far room read far. Relative ordering is plausible. The black area outside the fisheye circle reads "near", as
  §6.2 expects, so the area outside the image circle must be ignored by anything that reads this layer.
- **Magic Mask** (frames 0, 120, 165, 250, 364): one click on the operator's jacket gives a tracked matte of the
  jacket and sleeves on every frame, with a soft edge (values 1–254 sit on the ~4 % of pixels around the operator;
  the background is exactly 0). It excludes the yellow strap, the belt pack, the trousers, the boots and the head,
  so it is **not** a whole-operator mask (SPEC expects ~8 % of cam0 for the whole operator). This confirms §6.1's limit.

Two earlier attempts are kept, as the never-overwrite rule requires, and are recorded here so nobody reads them as
results:

- `magic_mask/ced16b9544c8ecb3`: **failed acceptance** (45 empty frames, median coverage 0.002 %). The "white"
  render had reached only ~0.5 of full scale, because Resolve clamps the CDL offset. The fix: the white level is
  now measured from the renders (0.5007 here; read-back 0.499753), and the matte is (B − A) / level.
- `_render/magic_mask/f08e9e89d062e6d9`: stopped by the new guard before producing outputs. An offset of 0.5 reads
  back as 0.000999, because the offset mapping is non-linear below the clamp.

Not done in the proof: cam1 passes (cam1 only had the one-frame depth check), the other clips, upload to the
bucket (waits for approval), and any of the §6.3 passes.

## 8. Open decisions for the owner

1. **Approve the rule and the layout** in §1–2 (analysis layers never enter reconstruction; per-fingerprint paths).
2. **Mask classes:** decided 2026-11-12: "people" = SAM 3 `person` (primary, **run on this Mac**), with Resolve
   Magic Mask as a cross-check. Still open: "landing gear" as the static per-lens mask (recommended over tracking per §6.1/§7),
   and the per-class coverage bands.
3. **Clicks for people:** picked by a person per clip/lens, or derived from the local SAM 3 masks. Also decide
   whether multi-click authoring inside one grade is worth building, since today each click costs one track and
   two renders.
4. **Render intermediates** (`resolve/_render/…`) are reproducible from the fingerprint, but large: 16 GB per
   lens-clip for a matte pass and 8.3 GB for depth, all at 3840² for 365 frames. The proof left **56 GB**
   (including the two kept failed attempts) on the 2TB drive. Keep them, or delete them after acceptance?
5. **Which frames to render.** Measured on clip 041: Magic Mask 0.93 s/frame and Depth Map 0.44 s/frame, per lens.
   All 8 clips are 21,689 frames per lens (12.1 min). At full frame rate, both lenses: Magic Mask ≈ 11 h,
   Depth ≈ 5.3 h, depth outputs ≈ 630 GB, and renders ≈ 2.9 TB. The 2TB drive has 171 GB free. **Recommended:**
   track Magic Mask over the full clip (tracking needs every frame), but render and keep only the frames molab's
   frames stage selected (1 fps ≈ 1,450 lens-frames in total, ≈ 21 GB of depth). Full-rate review layers, if
   wanted, would be half resolution. This needs a `frames` input to the pass (render ranges from
   `frames.parquet` `t_ms`), not built yet.
6. **Project library on the 2TB drive (G1):** add it once in Project Manager, then set `project.library` in the
   config. Today the project lives in the "Local Database" library on the internal disk. Its media, caches,
   stills and backups are already on 2TB.
7. **Full run scope:** all 8 clips × 2 lenses × which passes, and whether depth runs on fisheye or rectilinear
   views.

## 9. GUI-only gaps (no 21.2 scripting call does these)

| # | Step | Frequency | Workaround in this pipeline |
|---|---|---|---|
| G1 | Add a project library (database) | once per drive | the bootstrap switches to it by name once added |
| G2 | Preferences: External scripting = Local; Media Storage order | once per machine | the bootstrap verifies both and stops if they are wrong |
| G3 | Place Magic Mask points (Color palette or Fusion viewer) | per subject | author the click into a grade (`.drx`) and apply it. One click only today |
| G4 | Set ResolveFX (OFX) parameters on the Edit/Color page | per effect | use the Fusion tool (Depth Map, Relight, Filter), a DCTL, or host the OFX as a Fusion tool, where its inputs are scriptable (verified by the other session for the Gaussian Splat plugin; not yet tried for ResolveFX) |
| G5 | Search an IntelliSearch index | per query | analysis is scriptable; searching is in the GUI |
| G6 | "Render Magic Mask in place as an external matte" | per clip | the two-render matte (§6.1); `GetClipMatteList` reads mattes made in the GUI |
| G7 | Generate proxies or optimized media | per clip | not needed (lossless remux plays; both are disabled in the bootstrap) |
| G8 | Dismiss a modal dialog (e.g. an unsaved project on switch) | rare | run headless (`-nogui`) for unattended jobs; save before switching |
