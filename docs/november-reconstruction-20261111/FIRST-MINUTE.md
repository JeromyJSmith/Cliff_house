# First-minute 360 reconstruction

Source: verified November 10 clip035, first 60 seconds, one timestamp per second and both fisheye streams (120 lens images). The first minute shows an interior walk and moves outside toward the end. Original INSV remains unchanged.

COLMAP produced two separate components. Main component: 66 registered lens images, 9,518 sparse points, 1.149 px mean reprojection error. OpenMVS created a textured surface from that component; Blender 5.3 created an overview and .blend file. Visual review shows substantial holes and fragmented surfaces; this is a provisional partial reconstruction, not an accurate complete room model. Scale is unverified. The second component was not merged without alignment.

Evidence root: `/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/november-capture-reconstruction-v001/`

Inputs: `clip035-first-minute-frames-v001/`; sparse results: `colmap-first-minute-v001/`; textured model, Blender file, logs and review: `first-minute-surface-v001/`.
