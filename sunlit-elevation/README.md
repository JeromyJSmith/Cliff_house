# Cliff House Lodge · Sunlit Elevation (v2, 2026-11-20)

Live: https://jeromyjsmith.github.io/Cliff_house/sunlit-elevation/ · Stone Street Cottage: `../stone-street/`

The lodge's stone gable front (115 Stone Street, Morrison CO) drawn in ink with 45° hatching; the hatching is the
real shadow map, and a sweep turns the drawing into the photographed materials. Technique and engine (`engine/`,
unchanged): [Flat to 3D · Sunlit Elevation](https://github.com/Sam1983Aing/flat-to-3d) by Samnang Aing, MIT
(`LICENSE-flat-to-3d`). Model: `page.js` + `kit.js`.

v1 (schematic, from the written history only) is replaced. v2 is modelled from the photos and 3D below.

## Evidence (every element cites one)

| Id | Source (MacBook paths) | What it gives |
|---|---|---|
| F1 | IMG_0949 t118–t128 s, `/Volumes/MARPA/_New_APP/data/projects/cliff-house/03_bim/site-model/building-names-evidence/cmp_0949_E.jpg` | the gable front: 3 bays × 2 storeys; 2-over-2 sashes, mint frames; white eared surrounds with lilac crest panels; white string course and corner pilasters; pediment with white/mint/lilac trim and a vent; entrance with transom and historic-site plaque in the left bay; rock-faced red wing to the left; low dark shingled wing and redwood board fence to the right |
| F2 | drone 030 nadir frames 06045, 06182, 06286, 06615, 06729, `/Volumes/MARPA/_New_APP/data/projects/cliff-house/02_reality_capture/drone-2026-11-09/nadir/frames_2400_100fov/` | stone colour (salmon ashlar with buff blocks, buff quoins), white stone lintels, mint sashes, brown shingle roof, red brick parapet, glazed timber roof monitor (sunroom, not on this elevation) |
| F3 | `/Users/jero/Documents/cliffhouse2.mp4` (27 s dusk aerial orbit, smeared like a splat render) | massing, brick chimneys, low roofs of the side wings |
| F4 | `cliff-house-site-v2.site-plan.json`, building 5, edge 6 | gable width 9.30 m ±0.3 (SAM 3 trace of the 2024 aerial, EPSG:32613) |

## Numbers and confidence

| Quantity | Value | Source | Confidence |
|---|---|---|---|
| Gable width | 9.30 m | F4 edge 6 | ±0.3 m; edge-to-gable assignment MEDIUM |
| Eave | 7.2 m | F1 t124 proportion × 9.30 m | ±10 % (low camera, perspective) |
| Front top | flat bracketed mint cornice, 7.20–7.70 m | F1 t124 | ±10 % |
| Central pediment | span ≈6.0 m (≈2.1 × the 2.9 m bay spacing), pitch ≈20°, rise ≈1.1 m, apex ≈8.8 m; lilac tympanum with dentils, framed in white and mint | F1 t124; rake slopes 0.58 (left) and 0.17 (right) of run because the camera is turned, mean 0.37 → 20° | ±3°, MEDIUM |
| Main roof | shingled hip behind the front; pitch and ridge NOT measured (8.8 m is the pediment apex, not the main ridge) | F3 | LOW |
| Left wing | 2 storeys of rusticated red sandstone in large blocks, mint cornice, door and window on the ground floor; eave ≈6.7 m; roof drawn as a low hip, UNVERIFIED | F1 t122, t124; F3 | eave ±10 %, roof LOW |
| String course | 3.75 m | same | ±10 % |
| Openings | 1.0 × 2.1 m | same | ±10 % |
| Wing set-backs (1.4 m left, 2.2 m right) | estimated | F1, F3 | LOW |

Not measured in 3D: the site IFC heights are assumptions and the published `.sog` is not scaled. Replace the
heights with the metric flight-030 splat (EPSG:32613) when it is trained.

## Dates (conflicting sources, all kept)

| Date | Claim | Source |
|---|---|---|
| 1873 | George P. Morrison's residence, three storeys of local sandstone; east wing 1889 | Morrison Historic District NRHP nomination (NPS, PDF p. 8) and https://morrisonhistory.org/places/cliff-house/, as summarised in `docs/reconnaissance-20261111/BRIEF.md` (main branch) |
| 1934–1944 (adjusted 1980) | assessor improvement records, "2 Story" | `/Volumes/MARPA/_New_APP/data/projects/cliff-house/00_records/county-2026-11-12/county_parcel/inventoryImprovement.json`, `PARCEL_FINDINGS.md` |
| 1864 | construction-date statement in a county archive catalog | `/Volumes/MARPA/_New_APP/data/projects/cliff-house/00_records/municipal-2026-11-12/NEW_FINDINGS.md` |

The page uses 1873 (the register date) and says on screen that the assessor and catalog dates differ. The
assessor years probably describe later improvements, but that hasn't been checked against the assessor cards.
Note the NRHP text says three storeys; the photographed front shows two.
