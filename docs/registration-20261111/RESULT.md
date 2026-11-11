> **Source correction, November 11:** the ten October 10 PLYs discussed below belong to the 401 Pearl capture inventory, not Cliff House. They were removed to Trash at the owner’s request. All derived alignments are excluded from Cliff House. Use November 9–10 captures only; see `docs/source-correction-20261111/CORRECTION.md`.

# Ten-scan registration: merge withheld after quality checks

Owner requested all ten PLY scans aligned in CloudCompare, overlap checks, merge only once alignment looks right, then Pascal. Present-day capture; no Spirula. This run is **partial**, not an accepted registered master.

## Work performed

- Preserved originals; all registration inputs are deterministic derivatives in the durable evidence folder below. Full SHA-256 preservation check re-read all ten originals.
- Ran 18 native CloudCompare rigid fits (nine to scan 6 and nine reciprocal), 150,000 training points each, 60 iterations, 80% estimated overlap, fixed scale. Reserved 50,000 source records per scan for checks.
- Compared all 45 unordered pairs in both directions before and after registration.
- Reverse-fit checks exposed unstable matches, so ran 26 additional native CloudCompare fits over 13 overlapping graph edges at 50% estimated overlap, using 50,000 training points. No new installations.
- Solved a rigid pose graph; then rejected the two most inconsistent edge pairs and reused the better 80% scan 1–6 fit for a second graph solve. All intermediate results remain preserved.
- Inspected common-frame XY, XZ and ZY comparison images. Broad wall/floor features line up better in several areas, but conflicting offsets remain. Neither result passed the merge gate. Do not treat any candidate transform as approved for final modeling.

## Findings

The fraction of sampled pairwise distances below 0.25 source units, averaged over 45 pairs, was 0.530 initially, 0.632 for the direct scan-6 fits, and 0.599 for the second graph candidate. This threshold is a diagnostic in captured units, not a physical accuracy specification or a surface-area overlap measurement.

Direct-fit reciprocal median cycle displacement ranged from 0.028 to 1.226 source units. The 50% retry reduced many local inconsistencies but produced two especially poor edges (2–3: 2.504; 1–6: 0.538); those edges were excluded from the second graph. Remaining constraints still disagree: scan 1→2 median 0.224, 6→5 median 0.251, 9→4 median 0.218 source units. A graph with a lower aggregate objective is not proof that repeated wall surfaces are correctly matched. The second graph worsened several pairwise fits involving scan 2.

No full-resolution transformed clouds or merged master were produced. Scaling remained unchanged. CloudCompare's measurement tool measures coordinates at the captured scale; it cannot independently establish their physical calibration. Owner requests proceeding with captured scale without supplying an external check dimension; do not repeatedly ask for that dimension.

## Pascal

The connected MCP scene store and the installed local editor expose different project inventories. No existing project was changed through that connector. Started the existing, preservation-aware local Pascal 1.0.6 launcher using its configured home `/Volumes/MARPA/_New_APP/var/pascal-host` on port 3004. Created and named one new project in the actual editor:

- Cliff House — present-day scan reference
- Project ID `e23412a87765`
- Observed editor URL: http://127.0.0.1:3004/project/e23412a87765
- Status: empty project scaffold; **no scan imported, no architectural elements modeled**.
- UI offers GLB/GLTF scan references and image guides, not raw PLY. Its file input advertises a 200 MB limit. A lighter derivative is required after alignment acceptance; original/full-resolution PLY evidence remains separate.
- Screenshot `pascal-project-prepared.png` records the new project. No hosted account, paid generation, publication, or Spirula workflow was used.

## Durable evidence and reproduction

`/Users/jero/Desktop/frasier/Cliff House/Mapping Evidence/2026-11-11/ten-scan-registration-v001/`

- `registration.json`: source fingerprints, nine direct transforms, 18 native commands and held-out results, all pair checks and reciprocal cycles.
- `fit-*/`: derived training PLYs, native logs, native registration matrices, JSON receipts.
- `scan-*-aligned-sample.ply`: direct-fit **candidate** samples, not accepted output.
- `overlap-graph-refinement/`: 26 edge fits, first graph and comparisons.
- `qualified-graph-v002/`: second candidate graph; despite the directory name, acceptance remains pending and failed this review. Graph constraints, comparison JSON and image retained.
- `original-preservation-check.json`: all ten original hashes checked against prior audit.

Source scripts in this commit reproduce the native fits, graph solves and review. Output directories deliberately refuse reuse for registration runs. Use new persistent version names for changed runs. Review calculations are diagnostic, not survey certification. The second comparison run wrote complete JSON and image outputs then hit a summary-print KeyError because its graph lacks the first graph's reciprocal-check field; the optional summary print was fixed. Numerical outputs preceded that print and were read and visually inspected independently; no claim that the original invocation exited successfully.

## Remaining work

Resolve conflicting overlaps by reviewing shared doorway/corner landmarks and registering cropped common surfaces, particularly the 1/2/5/6 loop, rather than unconstrained whole-cloud ICP against repeated planes. Recheck loops and sections, apply only accepted transforms to the full-resolution sources, then merge and produce a lighter Pascal scan reference. No final merge or successful Pascal scan import is claimed.
