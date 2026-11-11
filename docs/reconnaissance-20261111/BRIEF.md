> **Source correction, November 11:** the ten October 10 PLYs discussed below belong to the 401 Pearl capture inventory, not Cliff House. They were removed to Trash at the owner’s request. All derived alignments are excluded from Cliff House. Use November 9–10 captures only; see `docs/source-correction-20261111/CORRECTION.md`.

# Cliff House, Morrison — present-day mapping baseline

2026-11-11. Owner selected **present-day building first**. Source root: `/Users/jero/Desktop/frasier/Cliff House`. Reuse the existing repository and reconstruction work; preserve all originals, checkpoints, failed attempts and logs. No model generation, training or source edits were performed during this reconnaissance.

## Historical identity and architectural cues

This is Cliff House Lodge at **115 Stone Street, Morrison, Colorado**, rather than the separately named Cliff House at Pikes Peak in Manitou Springs.

[Morrison History](https://morrisonhistory.org/places/cliff-house/) identifies the original residence as George P. Morrison's 1873 home, an east wing added in 1889, alternating red/buff sandstone in the original section and red sandstone with buff corner quoins in the addition. Its page includes dated 1976, 2000 and 2025 photographs. Those distinctions are candidates for historical component tags, not permission to assign every observed wall a construction date without comparison.

The [Morrison Historic District National Register nomination](https://npgallery.nps.gov/GetAsset/ab09b525-37bc-4e38-a065-acaeb5883810), PDF page 8 (zero-based page 7), describes the 1873 residence, local sandstone, three stories and French casement windows. It records conversion to a rooming house after Morrison's death in 1895, and a former garden bandstand. This is historical documentary evidence; the record's period descriptions do not substitute for present-day measurements.

The [lodge's own history](https://www.cliffhouselodge.net/about-us) describes later boarding-house use and cottages built by the 1940s. Treat operator history as a useful source to corroborate through archival photographs, records and physical fabric. [SAH Archipedia](https://sah-archipedia.org/buildings/CO-01-JF36) was located but its page could not be fetched successfully during this pass; no additional architectural claims rely on it.

A [Morrison haunted-history tour listing](https://www.haunted.tours/coloradohauntedhistory) explicitly includes Cliff House ghost stories. This establishes a local folklore tradition, not evidence of paranormal phenomena. If the presentation includes those stories, keep them in an optional interpretation layer with attribution. No ghost identities, locations or events are asserted by this survey.

## Actual local material read

Durable audit: `/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/initial-survey-v001/source-audit.json`.

- **1,180 files inventoried** by relative path, byte count and modification time, excluding `.git`, symlinks and this output directory. Original files remain in place.
- **10 SiteScape PLY exports**, totaling **239,347,625 stored point records**. Each header and payload length agree exactly: little-endian float XYZ plus RGB, 15 bytes/point. This does not establish 239 million distinct observations; overlap and duplicated/cumulative exports remain untested.
- Approximately 20,000 evenly indexed records sampled per cloud for finite coordinates and provisional bounds. These are not full extents, building dimensions, proven units or scan registrations. Source headers were SHA-256 hashed; full raw-file hashing remains unperformed.
- **11 video artifacts probed**: eight top-level INSV captures, an additional INSV in the repository, the edited `pttfffffthrt.mp4`, and `source.mp4` inside the prepared dataset. The latter is a candidate alias/copy, not independently counted capture coverage.
- All eight top-level INSV files expose **two 3840×3840 video streams at 30000/1001 fps**. They must be interpreted through the appropriate dual-lens camera model or a calibrated stitch; they are not ordinary equirectangular frames. Container metadata alone does not establish lens calibration or spatial scale.
- `processed/model.obj`: **1,465,271 vertex records, 8,625,399 UV records and 2,875,133 face records**, with an MTL and JPG. Object units, orientation, provenance and registration remain unqualified. It was counted, not opened or accepted visually as accurate geometry.
- Existing repository result `results/clip_032_cuda`: a saved 30,000-step checkpoint and training log. A second local run `Spirula Runs/clip_041_20261110/training/high-360` reports completion at 50,000 steps. Existing cleanup-pass artifacts also remain in place. Training metrics are not geometric accuracy evidence.
- `clip_041_20261110/sfm.log` reports two components; `pttfffffthrt_run/sfm.log` also reports two. Their summary percentages describe principal reconstruction registration and cannot be read as one complete registered property. Inspect actual camera/component membership and overlaps before choosing a merge strategy.
- Visually inspected the existing `Spirula Runs/pttfffffthrt_review/sequence-review.jpg`: cottages, courtyard, paving, fences/gates, trees/rocks and partial stone-lodge coverage are visible. This sheet alone does not establish coverage of all elevations, roof or interiors.

No PDF/DXF/Vectorworks plan, RoomPlan JSON, E57 or LAS/LAZ file was found in this initial recursive filename inventory. Plans or other captures elsewhere may still exist. SiteScape files are actual point-cloud inputs; their application tag does not establish a particular device or certified survey accuracy.

## Mapping approach

1. Map capture coverage first: building/cottage/room labels, video timestamps, scan IDs and camera components. Keep unknown locations unknown until visual landmarks resolve them.
2. Audit all ten clouds for full bounds, overlaps, outliers, units, up axis and available transforms. Do not merge repeated exports or assume common origins from similar filenames.
3. Select the strongest overlapping exterior baseline and register the other evidence with explicit transforms and residuals. Establish scale from a trustworthy measured distance/control source, and reserve independent check distances. A visually convincing splat is not a dimensional reference by itself.
4. Preserve three coordinated representations: captured point/mesh evidence, editable architectural elements, and a photoreal appearance layer. Keep source IDs, transforms and uncertainty with every reconstructed element.
5. Start with the main lodge shell, its addition junction, floors, roof, openings, masonry and primary circulation. Add cottages and landscape as separate named components. Do not flatten nonparallel or irregular historic walls into ideal geometry without recording the deviation.
6. Compare the editable model with orthographic scan sections and posed image views. Report check residuals and missing/occluded areas. Assign accuracy targets only after scale and control are available.
7. After present-day geometry is accepted, compare archival photographs to add historical phases. Keep conjectural past states distinct from measured current fabric.

Immediate next output: a capture/coverage map and a registered measured baseline. A finished reconstruction, complete point-cloud registration, photoreal acceptance, historical period reconstruction and survey-grade dimensional accuracy are **not yet delivered**.

## Reproduce the source audit

Use the existing host Python and ffprobe; install nothing:

```sh
python3 scripts/audit_sources.py --source-root '/Users/jero/Desktop/frasier/Cliff House' --output '/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/<new-named-survey>'
```

The script refuses an existing output directory. It reads raw sources without conversion/training and records only header hashes, source stats and sample bounds. Recovered or newly generated evidence must always use named persistent locations.
