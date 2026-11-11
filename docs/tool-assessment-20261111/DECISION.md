# Cliff House: selected toolchain and registration pilot

2026-11-11. Owner requests maximum practical accuracy and speed, present-day Cliff House, with point clouds and images extracted from video. **Spirula is excluded from the new workflow. Use Blender 5.3 if Blender is used.** Existing work remains preserved.

## Decision

**CloudCompare → Pascal for editable architectural elements → Blender 5.3 for fine historic geometry, materials and final renders.** Keep Three.js as the optional interactive delivery layer, reusing Pascal's existing presentation capabilities before building another viewer.

The authoritative measurement evidence is the original captures plus explicit registration transforms, scale qualification and error reports. Pascal is the authority for authored architectural intent; it does not replace the measured evidence. Blender holds detailed render geometry that can retain historic irregularity. Keep stable component IDs and explicit coordinate adapters between them.

| Tool / supplied skill | Chosen role and qualification |
|---|---|
| CloudCompare native CLI | First-stage overlapping-scan registration, distance checks, sections and controlled merge. Existing installation works. |
| CloudComPy | Optional Python wrapper for CloudCompare. Not required for the native CLI pilot; no extra installation performed. |
| Pascal / `pascal-3d` | Main editable building model: measured walls, floors, rooms, doors, windows, roofs and component identity. User has had good results with it. Read connected agent guide and tool inventory; no scene edited or uploaded in this assessment. |
| Pascal `architect` | Generating designs from briefs is its documented purpose. Defer it for faithful as-built reconstruction; do not ask it to invent the existing building from a description. No Architect turn or paid generation started. |
| Blender `blender-geometry-nodes` | In Blender 5.3, source-driven repeated masonry/trim and other detailed systems after registration. Preserve nonuniform walls and measured boundaries; do not snap historic fabric into an idealized design without recording deviations. Probe actual 5.3 node sockets before using recipes written for 5.2. |
| `blender-skill-harmonizer` | Coordinate source authority, stage order and artifact handoffs. Architectural multi-view evidence governs; mascot-style front-view precedence and `/tmp` examples do not apply. |
| Three.js fundamentals / WebGL | Interactive measured-model review, layers and final presentation. Use explicit transforms, suitable LOD and bounded point/mesh budgets. A browser renderer does not supply scan registration accuracy. |
| `img2threejs` | Optional reference-led procedural reconstruction of a discrete decorative element when it adds value. Its own contract is code-authored interpretation, not photogrammetry or scan extraction. Keep inferred shape separate from measured fabric. Its reconstruction state gates apply if a future object build is started; no object reconstruction was started here. |

## Verified installation and primary documentation

- `/Applications/CloudCompare.app`: bundle version **2.14.0**. Existing `/Users/jero/.local/bin/CloudCompare` launches its native CLI and uses the already-configured shared Python 3.12 environment under `/Volumes/MARPA/_New_APP/tools/cloudcompare-python/.venv`. `-SILENT -AUTO_SAVE OFF -HELP` succeeded. No install, environment replacement or source build was needed.
- CloudComPy was not importable in that shared Python environment (`find_spec('cloudComPy')` returned None). The app's Python plugin is a different integration; plugin discovery does not prove an externally importable CloudComPy or pycc module.
- `/Applications/Blender 5.3 Beta.app/Contents/MacOS/Blender --version`: **5.3.0 Beta**, build `873fa9640966`, build date 2026-10-21. This verifies the executable, not current scene/add-on/render compatibility. No Blender scene was mutated.
- [CloudCompare command line](https://www.cloudcompare.org/doc/wiki/index.php/Command_line_mode): commands execute sequentially; autosave defaults can write near inputs. Our pilot disables autosave, uses only persistent derived PLY inputs and sets a persistent working directory. The registration matrix written beside those inputs is retained.
- [CloudCompare ICP](https://www.cloudcompare.org/doc/wiki/index.php/ICP): fine registration assumes roughly aligned, overlapping geometry. Merge concatenates data; it does not establish alignment. Fixed-scale rigid ICP is the first choice for these related scans. A scale change needs evidence rather than an automatic fit option.
- [CloudComPy source](https://github.com/CloudCompare/CloudComPy) describes a Python wrapper. The [official downloads page](https://www.cloudcompare.org/release/) distinguishes the app from its Python integrations. Adding the wrapper now would add setup work without improving this pilot's geometry.

## Actual capture checks

Evidence root: `/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/cloudcompare-assessment-v001/`.

1. SHA-256 fingerprinted all ten original SiteScape PLYs; each was unchanged in size and modification time across its read. Extracted a deterministic 200,000-record sample per cloud into `point-cloud-audit/`, preserving RGB. Confirmed sample coordinates are finite. Original files were not written.
2. Compared each ordered pair in original source coordinates: 50,000 queries against the other cloud's 200,000 samples. This reports sampled nearest-neighbor distances, not proven physical overlap or independent survey accuracy. Units remain unverified.
3. Generated and visually inspected `source-projections.jpg` with unchanged source XZ, XY and ZY axes and common framing. The PLYs contain strongly overlapping interior-like wall/opening geometry. Full-property, roof and exterior coverage are not established by this set alone. No individual room identity is assigned yet.
4. Chose scan **7 → 6** as one promising pair. Starting from their existing coordinates, held out every fourth sample record from both clouds: **150,000 training + 50,000 held-out records each**. Ran native CloudCompare ICP, 40 iterations, estimated 80% final overlap, sampling limit 200,000, **no scale adjustment**.
5. CLI return code 0. Runtime **4.565 seconds** including startup; native log reports registration computation **3.283 seconds**. Saved transform has positive unit determinant within floating-point tolerance and passes the orthogonality check.
6. Independently applied the saved matrix to held-out scan 7 records. Data-to-reference held-out median distance **0.046504 → 0.033806** (about **27.3% improvement**); p95 **0.147720 → 0.100030**. Values are in **unverified source units**, not claimed metres or centimetres. The reference-to-data median is essentially unchanged because scan 6 has substantial unmatched coverage. Shared sensor drift and dense neighboring records remain correlated; these are not survey control checks.
7. Visually inspected `registration-holdout-overlay.jpg`. The fit improves, but residual wall thickness/mismatch remains. This proves the CLI can run a useful local rigid-fit pilot. It does not qualify a final merge, all ten transforms, room dimensions or a completed building.

Full receipts: `point-cloud-audit/overlap.json`, `icp-pilot-scan7-to6/execution.json`, `cloudcompare.log`, registration-matrix text and `verification.json`. Intermediate samples and visual evidence remain outside Git in the owner-visible evidence root. Small source fingerprints, command and result summaries are committed here.

## Next stage and accuracy gates

- Determine which clouds represent the same area, repeated passes or disconnected spaces. Build an overlap graph and establish scan identities from image landmarks.
- Register overlapping groups on lightweight copies. Check reciprocal fits, residual sections and loop closure so chained pairwise fits do not accumulate unnoticed drift. Coarse landmark alignment is needed where rough alignment is absent; ICP is not a universal global stitch.
- Preserve source scale initially. Confirm units with a trustworthy real-world check distance and reserve independent check dimensions before claiming physical accuracy.
- Review outliers, moving people and reflective/occluded surfaces. Retain originals and distinguish a cleaned modeling derivative from measurement evidence.
- Apply only accepted transforms to full-resolution clouds, keeping a separate cloud identity per scan and a transform manifest. Produce a merged derivative after acceptance. Retain reversible transformations and source provenance.
- Select sharp video frames with actual capture coverage. Dual-lens INSV streams require the proper camera model/stitching; square video streams must not be treated as ordinary equirectangular panoramas. Solve/check image poses against the scan rather than using monocular estimates as scale authority.
- Use measured sections/openings to author Pascal elements. Preserve irregular fabric in detailed meshes. Keep Pascal's metre/Y-up plan XZ and Blender's Z-up frames connected by explicit, tested transforms after the source frame is qualified; never silently rotate raw data.
- Add material/photo detail and render in Blender 5.3 after geometric checks. Browser presentation comes after those checks.

No full-resolution merge, new Pascal project, image-pose solve, mesh reconstruction, photoreal render or Spirula execution was performed during this assessment.

## Reproduction

Use the existing shared MARPA Python with NumPy/SciPy/Pillow. Every new run needs a new named persistent output directory:

```text
scripts/assess_cloud_overlap.py --source-root <Cliff House> --output <new-point-audit>
scripts/run_cloudcompare_pilot.py --overlap <audit/overlap.json> --data 7 --reference 6 --output <new-pilot>
scripts/verify_cloudcompare_pilot.py <pilot>
```

The native command and all actual paths are in `execution.json`. Re-running is unnecessary without new evidence or changed parameters.
