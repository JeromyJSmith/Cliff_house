# Paper survey: video → Gaussian splats and measured geometry (2026-11-12)

Found through alphaXiv; arXiv IDs checked against the arXiv API; repositories checked with the GitHub API
(existence, license, last push) on 2026-11-12. Spot-checked again independently: MapAnything (Apache-2.0),
SpotLessSplats (Apache-2.0), PlanarGS (MIT), WildGaussians (MIT, from its LICENSE file), GOFish (CC BY-NC 4.0),
gsplat's `docs/3dgut.md` and `examples/benchmarks/fisheye/`, and the arXiv titles of 2610.37818, 2509.13414,
2508.20080 and 2611.10699. "Unverified" means no official repository could be confirmed.

**License key for reuse (non-commercial project):** MIT / Apache-2.0 / BSD and non-commercial licenses
(CC BY-NC, CC BY-NC-SA, Inria GS) → cells may be adopted, keeping the license notice and attribution (BY-NC-SA
adaptations stay BY-NC-SA). No license → ideas only, reimplement. VGGT-family code uses Meta's custom VGGT
license — review its terms before adopting. "Fit" values below were assessed before the project was confirmed
non-commercial; non-commercial rows marked "reference" are now adoptable.

## Papers

| Angle | Title | arXiv | Date | Key idea | Code | License | Last push | Fit |
|---|---|---|---|---|---|---|---|---|
| Poses from video | VGGT | [2503.11651](https://arxiv.org/abs/2503.11651) | 2025-03 | Feed-forward transformer predicts cameras, depth, point maps, tracks | [facebookresearch/vggt](https://github.com/facebookresearch/vggt) | VGGT License (custom) | 2026-05-19 | reference — base model; chunk for long video |
| Poses from video | VGGT-Long | [2507.16443](https://arxiv.org/abs/2507.16443) | 2025-07 | Chunk, loop-close and align VGGT over very long sequences | [DengKaiCQ/VGGT-Long](https://github.com/DengKaiCQ/VGGT-Long) | VGGT License | 2026-03-20 | adopt (license review) — long walkthrough poses without COLMAP |
| Poses from video | MapAnything | [2509.13414](https://arxiv.org/abs/2509.13414) | 2025-09 | Feed-forward metric reconstruction; optional intrinsics/depth/pose inputs | [facebookresearch/map-anything](https://github.com/facebookresearch/map-anything) | Apache-2.0 | 2026-08-07 | adopt — accepts known intrinsics and LiDAR depth |
| Poses from video | LingBot-Map | [2604.14141](https://arxiv.org/abs/2604.14141) | 2026-04 | Streaming geometric-context transformer for video poses and points | [Robbyant/lingbot-map](https://github.com/Robbyant/lingbot-map) | Apache-2.0 | 2026-10-14 | reference — permissive streaming alternative |
| Poses from video | AnySplat | [2505.23716](https://arxiv.org/abs/2505.23716) | 2025-05 | Feed-forward 3DGS from uncalibrated images | [InternRobotics/AnySplat](https://github.com/InternRobotics/AnySplat) | MIT | 2025-12-22 | reference — fast preview splat |
| Fisheye / 360 | 3DGUT (2024 foundation) | [2412.12507](https://arxiv.org/abs/2412.12507) | 2024-12 | Unscented transform splats through distorted/fisheye cameras | [nv-tlabs/3dgrut](https://github.com/nv-tlabs/3dgrut) | Apache-2.0 | 2026-11-06 | adopt — trains directly on raw fisheye frames |
| Fisheye / 360 | gsplat (2024 foundation) | [2409.06765](https://arxiv.org/abs/2409.06765) | 2024-09 | Open 3DGS library; ships 3DGUT and fisheye examples | [nerfstudio-project/gsplat](https://github.com/nerfstudio-project/gsplat) | Apache-2.0 | 2026-09-19 | adopt — the trainer for the pipeline |
| Fisheye / 360 | Fisheye 3DGS FoV analysis | [2508.06968](https://arxiv.org/abs/2508.06968) | 2025-08 | Evaluates >180° fisheye 3DGS; depth-based init | unverified | — | — | reference — matches our >180° lenses |
| Fisheye / 360 | Seam360GS | [2508.20080](https://arxiv.org/abs/2508.20080) | 2025-08 | Models dual-fisheye seam and lens misalignment in 3DGS | unverified | — | — | reference — consumer dual-fisheye artifacts |
| Fisheye / 360 | DirectFisheye-GS | [2604.00648](https://arxiv.org/abs/2604.00648) | 2026-04 | Native fisheye input, joint cross-view optimization | [Metaverse-AI-Lab-THU/DirectFisheye-GS](https://github.com/Metaverse-AI-Lab-THU/DirectFisheye-GS) | Inria GS (non-commercial) | 2026-08-15 | reference only |
| Fisheye / 360 | GOFish | [2610.37818](https://arxiv.org/abs/2610.37818) | 2026-10 | Full-FoV fisheye splatting plus mesh extraction for digital twins | [tuallen/GOFish](https://github.com/tuallen/GOFish) | CC BY-NC 4.0 | 2026-10-31 | reference — closest to our goal; non-commercial |
| Fisheye / 360 | PFGS360 | [2603.23324](https://arxiv.org/abs/2603.23324) | 2026-03 | SfM-free omnidirectional GS with consistent depth priors | [zcq15/PFGS360](https://github.com/zcq15/PFGS360) | none | 2026-04-09 | reference only |
| Fisheye / 360 | ODGS (2024) | [2410.20686](https://arxiv.org/abs/2410.20686) | 2024-10 | Equirectangular rasterizer for 3DGS | [esw0116/ODGS](https://github.com/esw0116/ODGS) | MIT | 2025-05-30 | reference — fallback for equirectangular training |
| Large scale | GGPS (Insta360 Research) | [2607.08769](https://arxiv.org/abs/2607.08769) | 2026-07 | Partitioning for large panoramic outdoor 3DGS | [Insta360-Research-Team/GGPS](https://github.com/Insta360-Research-Team/GGPS) | CC BY-NC-SA 4.0 | 2026-10-21 | reference — same camera family |
| Large scale | LODGE | [2505.23158](https://arxiv.org/abs/2505.23158) | 2025-05 | Level-of-detail 3DGS for memory-limited rendering | unverified | — | — | reference — LOD for viewing |
| Transients | SpotLessSplats (2024) | [2406.20055](https://arxiv.org/abs/2406.20055) | 2024-06 | Feature-clustered robust masks drop distractors | [lilygoli/SpotLessSplats](https://github.com/lilygoli/SpotLessSplats) | Apache-2.0 | 2025-11-07 | adopt — people walking through |
| Transients | WildGaussians (2024) | [2407.08447](https://arxiv.org/abs/2407.08447) | 2024-07 | DINO uncertainty plus per-image appearance embeddings | [jkulhanek/wild-gaussians](https://github.com/jkulhanek/wild-gaussians) | MIT | 2025-09-19 | adopt — indoor/outdoor exposure changes |
| Transients | RobustSplat++ | [2512.04815](https://arxiv.org/abs/2512.04815) | 2025-12 | Separates densification, dynamics and illumination | unverified | — | — | reference — ideas only |
| Geometry / metric | DN-Splatter (2024) | [2403.17822](https://arxiv.org/abs/2403.17822) | 2024-03 | Depth and normal priors (sensor or mono) for splats and meshing | [maturk/dn-splatter](https://github.com/maturk/dn-splatter) | Apache-2.0 | 2025-07-05 | adopt — LiDAR depth supervision |
| Geometry / metric | PlanarGS | [2510.23930](https://arxiv.org/abs/2510.23930) | 2025-10 | Vision-language planar priors for indoor geometry | [SJTU-ViSYS-team/PlanarGS](https://github.com/SJTU-ViSYS-team/PlanarGS) | MIT | 2026-04-25 | adopt — walls/floors for later IFC |
| Geometry / metric | MILo | [2506.24096](https://arxiv.org/abs/2506.24096) | 2025-06 | Mesh extraction inside training | [Anttwo/MILo](https://github.com/Anttwo/MILo) | Inria GS (non-commercial) | 2026-04-03 | reference — best meshes; license limits use |
| Geometry / metric | PGSR (2024) | [2406.06521](https://arxiv.org/abs/2406.06521) | 2024-06 | Planar Gaussians with multi-view consistency | [zju3dv/PGSR](https://github.com/zju3dv/PGSR) | custom non-commercial | 2024-12-25 | reference only |
| Geometry / metric | PLS-GS | [2611.10699](https://arxiv.org/abs/2611.10699) | 2026-11 | Probabilistic LiDAR scaffolds for surface-aligned Gaussians | [k-harikumar/PLS-GS](https://github.com/k-harikumar/PLS-GS) | none | 2026-11-10 | reference — LiDAR-fusion idea |
| Frame selection | Adaptive Keyframe Selection | [2510.23928](https://arxiv.org/abs/2510.23928) | 2025-10 | Error-based plus momentum keyframe selection with dynamics | unverified | — | — | reference — selection logic |
| Frame selection | ClearGS | [2609.31509](https://arxiv.org/abs/2609.31509) | 2026-09 | Weights frames by reliability instead of keep/drop | unverified | — | — | reference — reliability as a Pixeltable column |

Also checked, omitted for length: VGGT-SLAM 2.0 ([2601.19887](https://arxiv.org/abs/2601.19887),
[MIT-SPARK/VGGT-SLAM](https://github.com/MIT-SPARK/VGGT-SLAM), BSD-2-Clause) and CityGS-X
([2503.23044](https://arxiv.org/abs/2503.23044), no license).

## Recommended stack

- **Frames:** write our own per-lens selection (sharpness, overlap) and keep a reliability *weight* per frame
  rather than a keep/drop flag (ClearGS, Adaptive Keyframe Selection).
- **Poses:** COLMAP/GLOMAP with `OPENCV_FISHEYE` as the baseline; VGGT-Long or MapAnything on pinhole crops of the
  fisheye as the fast path (MapAnything can take known intrinsics and LiDAR depth); a fixed rig transform ties the
  two lenses together. Validate the learned path against COLMAP on a short clip before trusting it.
- **Splat training:** gsplat with 3DGUT on raw fisheye frames — no stitching to equirectangular. Seam and
  vignetting ideas from Seam360GS, GOFish and the FoV study.
- **People and exposure:** SpotLessSplats-style robust masking plus WildGaussians appearance embeddings; person
  masks as a Pixeltable computed column.
- **Geometry and scale:** DN-Splatter-style depth/normal supervision using LiDAR depth where it covers the scene,
  PlanarGS planar priors; scale fixed only by a similarity transform to LiDAR or control measurements.
- **Meshes:** ship from a permissive path (DN-Splatter / gsplat depth fusion); MILo, PGSR, GOFish for comparison.
- **Export:** splat PLY and meshes to the bucket after every checkpoint; LODGE/GGPS ideas if the site must be
  partitioned.

## Open risks

- Many of the strongest repos are non-commercial or unlicensed; VGGT-family licenses need review.
- Learned pose models are trained mostly on pinhole images; our lenses exceed 180°, so crops and the rig
  constraint must be validated against COLMAP.
- Metric accuracy hinges on registering the phone LiDAR to the video reconstruction.
- 12-hour molab sessions require checkpoint/resume through Hugging Face; large scenes may need partitioning.
- `.insv` decoding, rolling shutter and exposure metadata are not covered by these papers.
