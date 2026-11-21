# Cliff House Lodge · Sunlit Elevation (v3, 2026-11-20)

Live: https://jeromyjsmith.github.io/Cliff_house/sunlit-elevation/ · Stone Street Cottage: `../stone-street/`

The lodge's north front (115 Stone Street, Morrison CO) drawn in ink with 45° hatching. The hatching is the real
shadow map, and a sweep turns the drawing into the stone and trim seen in the splat and the photos. Engine (`engine/`,
unchanged): [Flat to 3D · Sunlit Elevation](https://github.com/Sam1983Aing/flat-to-3d) by Samnang Aing, MIT
(`LICENSE-flat-to-3d`). Model: `page.js` + `kit.js`.

## v3: geometry from the property splat (PROVISIONAL)

> **PROVISIONAL (2026-11-20).** The v3 front dimensions come from full-property-original.sog, whose training solve
> is unknown and which matches a SuperSplat-edited step-28000 export. Under the owner's standing rule (never use the
> hand-edited twin or SuperSplat edits as truth), these numbers are not a truth source. The 18.6 m width agrees with
> the county footprint edge to ±2 %, but nothing checks the heights (eave 6.1, cornice 6.5, string course 3.1,
> pediment 5.0 m / apex 7.5, ridge 8.8). The north-front layout stands as a hypothesis. Its evidence is the
> owner's north-front photos (2026-11-20), which shows the same three rusticated plus three rendered bays, pediment
> and hip roof. Everything is to be re-measured from the georeferenced drone-030 splat and checked with
> render_compare against the 030 cameras.


Source: `/Volumes/MARPA/_New_APP/data/projects/cliff-house/02_reality_capture_splats/full-property-original.sog`,
rendered orthographically by the reality viewer with a lodge-aligned frame
(`/Volumes/MARPA/_New_APP/apps/reality-viewer/scripts/render_ortho_lodge.ts`). Renders, specs and exact pixel
mappings: `/Volumes/MARPA/_New_APP/data/projects/cliff-house/05_presentation/sunlit-elevation-2026-11-20/splat-views/`.

| View | Use |
|---|---|
| `overview-top-80m.png` (20 px/m, viewer x/z) | locating the stone block; frame origin and axes traced from its roof corners (`spec-lodge.json`) |
| `lodge-plan-top.png` (50 px/m) | one hip roof over an 18.6 × 10.2 m block, ridge parallel to the north front; patio umbrella in front of it |
| `lodge-east-facade.png` (60 px/m, foreground beyond 0.6 m removed) | **every front dimension** (below) |
| `lodge-front-facade.png`, `lodge-front-elevation.png` | the south-east end: two storeys of rusticated red stone, one window per floor and a door. This is NOT the pediment front, which v1–v2.2 wrongly placed there |

| Quantity | Value (from `lodge-east-facade.png`) |
|---|---|
| Front length | 18.6 m: rusticated red sandstone 0–11.0 m, smooth ashlar 11.0–18.6 m |
| Rusticated eave / ashlar cornice top | 6.1 m / 6.5 m above grade at the wall |
| String course (ashlar part) | 3.1 m |
| Central pediment | 12.4–17.4 m (5.0 m), apex 7.5 m, about 21° |
| Hip ridge | 8.8 m; block depth 10.2 m, so the roof slopes at about 27° |
| Rusticated bays | windows at 2.65–3.45 and 5.7–6.5 m, glazed door 8.75–9.6 m; upper windows 3.75–5.75 m high |
| Ashlar bays | entrance 11.83–12.75 m; windows 14.08–15.08 and 16.28–17.28 m; upper windows 3.75–5.83 m high |

**Scale and accuracy.** The splat's scale is not independently surveyed. Its 18.6 m front agrees with the 18.87 m
county footprint edge to −1.5 %, and the same splat gives Stone Street 9.9 × 6.3 m, matching that cottage's
scale-checked interior scan. Read the figures as ±2 %, plus about ±0.1 m for picking edges in the render. The
georeferenced flight-030 splat will replace this when it is trained.

**Appearance.** IMG_0949 t118–t128 (`…/building-names-evidence/cmp_0949_E.jpg`) shows the white trim, mint sashes,
lilac crests and the plaque. Drone 030 nadir frames 06045–06729 and the owner's viewer screenshots of this splat
(2026-11-20, 19:49–19:50) show the hip roof, brick chimneys, buff corner blocks, the west shingled-gable wing and
sunroom monitor (not on this elevation), and the cream "LODGING" north end.

## Withdrawn

- v1 (history only) and v2–v2.2 (the south-east end modelled as the pediment front, sized from site-v2 footprint
  edges 6/8 and the ODM 030 point cloud). The footprint does not fit the drone roof (owner, 2026-11-20).
- `evidence/ortho-lodge-front.png` and `evidence/ortho-stone-street.png`: the site-v2 footprint drawn on the warped
  2.5D ODM orthophoto without registration. Kept as evidence, not used. See `evidence/REJECTED.md`.
- The ODM scripts and outputs in `measure/` stay as a record. Their lodge numbers are superseded by the splat.

## Dates (conflicting sources, all kept)

| Date | Claim | Source |
|---|---|---|
| 1873 | George P. Morrison's residence of local sandstone; east wing 1889 | Morrison Historic District NRHP nomination (NPS, PDF p. 8) and https://morrisonhistory.org/places/cliff-house/, as summarised in `docs/reconnaissance-20261111/BRIEF.md` (main branch) |
| 1934–1944 (adjusted 1980) | assessor improvement records, "2 Story" | `/Volumes/MARPA/_New_APP/data/projects/cliff-house/00_records/county-2026-11-12/county_parcel/inventoryImprovement.json`, `PARCEL_FINDINGS.md` |
| 1864 | construction-date statement in a county archive catalog | `/Volumes/MARPA/_New_APP/data/projects/cliff-house/00_records/municipal-2026-11-12/NEW_FINDINGS.md` |

## Orientation (owner, 2026-11-20; checked against the county map)

The pediment front is the **north** side. East is its rusticated left end, west is the mountain side (the smooth
right-hand part, the annex and the board fence), and south is the back. On the georeferenced site-v2 footprint
(2024 county aerial, EPSG:32613) this wall's outward normal points at about 64° (NE), which reads as "north" on site.
The splat render files keep their render-frame names (`lodge-east-facade.png` = the view along the frame's +u axis),
which are not compass directions. Earlier text here called it the east front; that was wrong.

## ODM-only check of the north front (2026-11-20)

This failed the visual check; see `measure/ODM-NORTH-FRONT-FAILED.md` in the project folder. The only consistent
figure is the top of the roof cluster (p95–p99 8.7–9.0 m), which agrees with the splat ridge of 8.8 m. The v3.1
values stay on the page, labelled provisional, until the 030 splat lands.
