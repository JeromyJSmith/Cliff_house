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

Status at this checkpoint: image alignment is actively running. No successful reconstructed mesh or new Pascal import is claimed yet. Inspect the run's exit/progress reports and review actual output geometry before export/import.
