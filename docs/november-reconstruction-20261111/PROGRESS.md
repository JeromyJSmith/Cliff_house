# Cliff House — verified November capture reconstruction

This stage resumes the original present-day Cliff House project after the October 401 Pearl source mix-up. The rejected PLYs and all derivatives remain excluded. No Spirula execution or Gaussian splat training is used.

## Verified sources and coverage

All nine native INSV clips have embedded creation timestamps on November 9 or 10, 2026, in America/Denver. The native timestamps are authoritative over filename clock text (clip035 and032 differ by one hour). Read-only video probes and 54 contact frames are recorded in the durable evidence directory below.

Visual coverage: 036/039 sunroom; 037 sunroom/entry/courtyard; 038 courtyard, main sandstone lodge exterior and later cottage interior; 040 exterior courtyard/main lodge; 041 cottage interior; 042 cottage/porch; 035 longer grounds traverse including lodge views; 032 short, mostly stationary courtyard view. This does not establish complete roof/rear/upper-floor coverage.

The unqualified `processed/model.obj` has no capture provenance and remains excluded as building authority. Existing clip041 camera calibration was read from its sparse camera solve; the solve log explicitly names the November10 source video. No earlier Gaussian representation was used.

## Reconstruction input

474 pinhole perspective derivatives from verified November10 clips035/037/038/040. Sources and timestamps are recorded per image. Each lens uses its own OPENCV_FISHEYE calibration estimated in the existing clip041 solve, with camera-ID-to-lens mapping checked against image names. Calibration transfer is an assumption, not an independent lens calibration.

The virtual views use 1280² images, 80° field of view, 60° tilt and three lens azimuths (0/90/180). The operator-facing fourth azimuth is omitted to reduce moving-person contamination; this is not full person segmentation. No panorama stitching or image generation occurs. Recorded intrinsics make the projection reproducible. Quality diagnostics and visual contact sheets are retained.

Apple RealityKit PhotogrammetrySession is installed and reports support on this machine (maximum2000images). The source runner requests medium OBJ geometry from the photos, unordered/high feature sensitivity, object masking off. Input/output/checkpoint/log paths are persistent and explicit. Runtime execution storage is a named persistent folder. Physical scale remains unverified; no arbitrary dimensions are asserted as measurements.

## Durable evidence

`/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/november-capture-reconstruction-v001/`

- `capture-provenance.json`, `contact-frame-provenance.json`, `coverage-1.jpg` through `coverage-3.jpg`
- `calibration-041/`: read-only conversion of the existing camera model
- `exterior-perspective-v001/`: source frames, 474 views, manifest and image-quality report
- `toolchain/`: reviewed Swift runner executable, compile/capability verification and persistent compiler storage
- `object-capture-exterior-v001/`: launch receipt, progress/console logs, checkpoints and requested output directory

## Alignment recovery

The first Apple run failed at image alignment with `processError`, native error -15. The complete logs/checkpoints remain under `object-capture-exterior-v001/`; no mesh was produced. A second run, `object-capture-clip035-v002/`, restricted inputs to the continuous exterior clip035 and recorded known generated-camera focal metadata in new image copies. It failed with the same error. Neither failure justifies treating any output as a successful model.

Independent native COLMAP reconstruction uses the 158 original fisheye frame derivatives, per-lens OPENCV_FISHEYE intrinsics, and geometrically verified candidate matches in `colmap-exterior-v001/`. Its points and camera registration must be inspected before surface reconstruction. No metric baseline has been invented.

OpenMVS v2.4.0 official macOS arm64 binary is installed at `/Users/jero/Developer/tools/openmvs/v2.4.0`, with release metadata and SHA256 verification against the GitHub release asset digest. This provides an independent dense-reconstruction path after a valid camera solve; it is not Spirula or Gaussian training.

No successful reconstructed mesh or new Pascal import is claimed at this checkpoint. The Cliff House Pascal scaffold remains separate from all 401 Pearl projects.


## Targeted lodge registration

The broad four-second sampling produced four fragmented sparse components (the lodge-containing one had only494points). A new run uses90native fisheye frames from clip035 at140–162seconds, every0.5seconds, preserving both lenses and the exact source timestamps. `colmap-lodge-v002/` registered all90images in one component:16,969points,65,809observations, mean track length3.878, mean native reprojection error1.232pixels. This is internal image consistency, not surveyed dimensional accuracy.

`prepare_mvs_virtual_views.py` transfers solved poses into pinhole views without re-solving or rescaling. It retains original observation visibility, requires two original images per retained point, and masks extrapolation outside a monotonic lens projection. QA caught and preserved a folded wide-angle projection attempt; folded images are excluded. Surface generation uses OpenMVS with no automatic hole filling and retains depth maps and all execution logs.
