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
| F4 | `cliff-house-site-v2.site-plan.json`, building 5, edge 8 (v2.1; edge 6 in v2) | front width 10.11 m ±0.3 (SAM 3 trace of the 2024 aerial, EPSG:32613) |

## Numbers and confidence

| Quantity | Value | Source | Confidence |
|---|---|---|---|
| Front width | 10.11 m (v2.1; was 9.30 m from edge 6) | site-v2 building 5 edge 8. The ODM point cloud shows the tall 2-storey block inside edges 8–9 (points 8.4–9.4 m) and only ~6.0 m inside edge 6; edge 8 also faces the patio with building 7 to its right, as in F1 | ±0.3 m; MEDIUM-HIGH |
| Wall top (cornice) | 7.1 m above the patio | M1: ODM 030 georeferenced point cloud, 95th percentile of points within 1 m of edge 8 minus the 5th percentile 1–4 m outside | ±0.5 m (sparse SfM cloud, GPS-only scale, tree contamination) |
| Front top | flat bracketed mint cornice, 7.20–7.70 m | F1 t124 | ±10 % |
| Central pediment | span ≈6.5 m (≈2.1 × the 3.15 m bay spacing), pitch ≈20°, rise ≈1.18 m, apex ≈8.78 m; lilac tympanum with dentils, framed in white and mint | F1 t124; rake slopes 0.58 (left) and 0.17 (right) of run because the camera is turned, mean 0.37 → 20° | ±3°, MEDIUM |
| Main roof | shingled HIP, ridge running front to back, ridge 10.8 m above the patio; side facets ≈25° (cross-section), rear facet ≈22° down to ≈8.8 m at 15.5 m depth, then a lower rear section ≈5.6 m | M2 + orthophoto | ridge ±0.5 m; HIGH that it is a hip with a front-to-back ridge |
| Left wing | front = edge 6 (9.30 m), set back 5.58 m (edge 7) behind the main front; 2 storeys of rusticated red sandstone (F1), wall top 5.5 m; low roof with the sunroom's glazed timber roof monitor parallel to the front, top ≈7.8 m | footprint + orthophoto (setback, monitor), M2 (heights), F1 (stone, openings), drone 06182 (monitor glazing) | setback ±0.3 m; heights ±0.5 m; opening positions LOW |
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

## M1: metric heights from the ODM 030 solve (added v2.1)

`/Volumes/MARPA/_New_APP/data/projects/cliff-house/02_reality_capture/drone-2026-11-09/ortho/odm_030/odm_georeferencing/odm_georeferenced_model.laz`
(358,805 points, EPSG:32613, GPS-only, no GCPs; 1158/1158 nadir frames registered). Scripts and full outputs:
`/Volumes/MARPA/_New_APP/data/projects/cliff-house/05_presentation/sunlit-elevation-2026-11-20/measure/`
(`pc_edges.py` → `pc_edges.output.txt`; `dsm_edges.py` → `dsm_edges.output.txt`). The DSM (`odm_dem/dsm.tif`) is
heavily interpolated, so it under-reads wall tops; the point-cloud numbers are the ones used. Heights are relative
to the ground next to each wall, because the drone's GPS altitude datum differs from the 1 m DEM's.
The 030 Gaussian splat (in progress, nixos-msi-51) should replace these.

### M1 check: horizontal registration and vertical scale (2026-11-20, after review)

**Registration.** `register.py` fits the GPS-only cloud to the site-v2 footprints of buildings 1, 4, 9 and 10. It
compares a height map (0.2 m cells, roof = more than 2.2 m above local ground) with the footprint polygons,
grid-searching ±3 m in steps of 0.25 then 0.1 m, and ±3° in steps of 0.5 then 0.25°. Best fit:
**dx 0.00 m, dy −0.25 m, rotation 1.5°**. IoU goes from 0.328 to 0.333, so the optimum is flat and the rotation
is weakly determined. Re-measured with that transform (`pc_edges_reg.py`, outputs `*.unshifted.output.txt` and
`*.registered.output.txt`):

| Quantity | Unshifted | Registered | Change |
|---|---|---|---|
| Lodge edge 8 wall band p95 | 7.11 m | 7.02 m | −0.09 m |
| Lodge edge 6 wall band p95 | 5.92 m | 5.22 m | edge 8 still clearly the 2-storey front |
| Cottage edge 2 (street) wall band p95 | 4.61 m | 4.58 m | −0.03 m |

Both changes are under 0.3 m, so the edge-8 call and the heights stand. The figures on the pages are unchanged.

**Vertical scale.** On the cottage's west side (edge 0, the passage, whose grade is at about the cottage floor),
the parapet reads **3.41 m** unshifted and **3.19 m** registered, and the roof interior p95 reads 3.70 / 3.69 m.
The interior scan gives 3.53 m. That agrees within about ±0.3 m. Edge 0 includes the north porch and trees
(its max is 16.8 m), which adds noise.

Note: the fitted 1.5° rotation is close to the 1.9° offset found between the Stone Street model axes and the
real roof edges in the splat plan (stone-street HANDOFF §4). That points to a small systematic rotation in the
site-v2 footprint regularisation rather than in ODM. Unresolved; the georeferenced 030 splat should settle it.

## M2: roof cross-sections (2026-11-20)

`roof_profile.py` (registered cloud). It takes height bands along and across the front, in a frame on edge 8
(s along the front, t into the building). Outputs: `roof_profile.out` (main block) and `roof_profile_left.out`
(left wing), both in `/Volumes/MARPA/_New_APP/data/projects/cliff-house/05_presentation/sunlit-elevation-2026-11-20/measure/`.
The orthophoto crop with the building-5 footprint is `…/evidence/ortho-lodge-front.png`. It shows the hip with
a front-to-back ridge on the stone block, the 5.58 m set-back of the left wing, and the long roof monitor on it.
The v2.1 left wing (1.4 m set-back, 6.7 m eave) was wrong and has been replaced.
