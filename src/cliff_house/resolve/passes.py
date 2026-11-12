"""Resolve analysis passes: one pass × one clip × one lens per run, rendered to a numbered image sequence.

    pixi run python -m cliff_house.resolve.passes configs/resolve/<project>.toml <pass> <clip> <lens>

Mask passes take their subject clicks from the project config (`[prompts.<pass>]`), never from the command line,
so a run is reproducible from the config and the code alone.

A pass is a fixed recipe — a Fusion comp or a colour grade applied to a timeline holding exactly one source clip —
rendered to files under

    <stage root>/resolve/<pass>/<fingerprint>/<clip>/<lens>/<frame:06d>.png + frames.parquet + pass.json

which is the bucket layout `stages/resolve/<pass>/<fingerprint>/<clip>/<lens>/…`. The fingerprint is the source
file's SHA-256, this module's code and the pass parameters, so a changed recipe lands beside the old output and
never overwrites it. A fingerprint whose pass.json already exists is skipped.

Every pass carries a `use` tag. Only `reconstruction` outputs (masks) may be fed to SfM or splat training;
`analysis` outputs (depth, edges, filters) are layers for CAD tracing and review and must never be.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Literal

import cv2
import numpy as np
import polars as pl

from .config import ProjectConfig, load
from .connect import resolve_app

Use = Literal["reconstruction", "analysis"]

# The Magic Mask click author (MIT, samuelgursky/davinci-resolve-mcp, resolve-advanced/vendor/drx-codec) moves the
# one subject click of a captured Magic Mask 2 grade. Its files are hashed into the fingerprint, so a different
# version of the author or template is a different output.
MCP_HOME = Path.home() / "Developer" / "davinci-resolve-mcp" / "resolve-advanced"
MM_AUTHOR = MCP_HOME / "vendor" / "drx-codec" / "magic-mask-author.js"
MM_TEMPLATE = MCP_HOME / "test" / "fixtures" / "magic-mask2-click.drx"
NODE = shutil.which("node") or str(Path.home() / ".pixi" / "bin" / "node")


@dataclass(frozen=True)
class Click:
    frame: int        # SOURCE frame of the click (0-based)
    u: float          # horizontal position, 0 = left edge, 1 = right edge
    v: float          # vertical position, 0 = top edge, 1 = bottom edge


@dataclass(frozen=True)
class PassSpec:
    name: str
    use: Use
    params: dict = field(default_factory=dict)


MAGIC_MASK = {"method": "magic_mask", "track": "BI", "render": "png8"}

PASSES = {
    # Mask class "people": every person, the operator included. Magic Mask 2 tracks the object under one click
    # through the whole clip (bidirectional); one click selects one object (a jacket, not the person), so each click
    # in the config is tracked on its own timeline and the mattes are unioned. Each matte is recovered from two
    # renders of the same tracked mask, the masked region forced to black and to white (see run_magic_mask).
    "mask_people": PassSpec("mask_people", "reconstruction", MAGIC_MASK),
    # Mask class "landing gear", tracked with Magic Mask: kept only to compare with the static per-lens mask
    # (cliff_house.static_mask), which is the reconstruction mask for rigid parts of the aircraft.
    "mask_landing_gear_tracked": PassSpec("mask_landing_gear_tracked", "analysis", MAGIC_MASK),
    # Fusion Depth Map (DaVinci Neural Engine), Better mode, map output (preview on), everything else default.
    # Relative depth, 1 = near, 0 = far, per frame: not metric, not temporally normalised.
    "depth_map": PassSpec("depth_map", "analysis", {"Mode": "Better", "DepthMapPreview": 1, "render": "png16"}),
}


# Read once at import: a run's fingerprint and its recorded code version must come from the same bytes even if the
# file is edited while a long render is in progress.
_MODULE_BYTES = Path(__file__).read_bytes()


def code_version(spec: PassSpec) -> str:
    parts = [_MODULE_BYTES]
    if spec.params.get("method") == "magic_mask":
        parts += [MM_AUTHOR.read_bytes(), MM_TEMPLATE.read_bytes()]
    return hashlib.sha256(b"".join(hashlib.sha256(p).digest() for p in parts)).hexdigest()[:12]


def fingerprint(source_sha256: str, spec: PassSpec, extra: dict) -> str:
    """Source bytes + pass code (+ the click author and template for Magic Mask) + parameters."""
    digest = hashlib.sha256(code_version(spec).encode())
    for part in (source_sha256, json.dumps({**spec.params, **extra}, sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Source:
    clip: str
    lens: str
    path: Path
    sha256: str
    frames: int


def find_source(cfg: ProjectConfig, clip: str, lens: str) -> Source:
    """Look the lens file up in the remux manifest (clip may be the full name or its 3-digit suffix)."""
    df = pl.read_parquet(cfg.remux_manifest).filter(
        ((pl.col("clip") == clip) | pl.col("clip").str.ends_with(f"_{clip}")) & (pl.col("cam") == lens))
    if df.height != 1:
        raise RuntimeError(f"{clip}/{lens}: {df.height} rows in {cfg.remux_manifest}")
    row = df.row(0, named=True)
    path = cfg.remux_manifest.parent / row["fingerprint"] / row["clip"] / f"{lens}.mp4"
    return Source(clip=row["clip"], lens=lens, path=path, sha256=row["sha256"], frames=row["packets"])


# ---------------------------------------------------------------- Resolve side

def _folder(media_pool, parent, name):
    for sub in parent.GetSubFolderList() or []:
        if sub.GetName() == name:
            return sub
    return media_pool.AddSubFolder(parent, name)


def timeline_for(project, source: Source, name: str):
    """One timeline per (pass, fingerprint, lens), holding only the source clip, so grades and comps never mix."""
    for i in range(1, project.GetTimelineCount() + 1):
        tl = project.GetTimelineByIndex(i)
        if tl.GetName() == name:
            return tl
    mp = project.GetMediaPool()
    folder = _folder(mp, _folder(mp, mp.GetRootFolder(), "inputs"), source.clip)
    clips = {c.GetClipProperty("File Path"): c for c in folder.GetClipList() or []}
    item = clips.get(str(source.path))
    if item is None:
        mp.SetCurrentFolder(folder)
        imported = mp.ImportMedia([str(source.path)]) or []
        if len(imported) != 1:
            raise RuntimeError(f"import of {source.path} returned {imported}")
        item = imported[0]
    frames = int(item.GetClipProperty("Frames"))
    if frames != source.frames:
        raise RuntimeError(f"Resolve reads {frames} frames, the remux manifest says {source.frames}")
    mp.SetCurrentFolder(_folder(mp, mp.GetRootFolder(), "passes"))
    tl = mp.CreateTimelineFromClips(name, [item])
    if tl is None:
        raise RuntimeError(f"CreateTimelineFromClips({name}) failed")
    return tl


def render(project, timeline, target: Path, codec: str, timeout_s: float = 7200) -> list[Path]:
    """Render the whole timeline to a numbered PNG sequence in `target` and return the files in frame order."""
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise RuntimeError(f"{target} is not empty; refusing to mix renders")
    project.SetCurrentTimeline(timeline)
    if not project.SetCurrentRenderFormatAndCodec("png", codec):
        raise RuntimeError(f"png/{codec} not accepted")
    w, h = int(project.GetSetting("timelineResolutionWidth")), int(project.GetSetting("timelineResolutionHeight"))
    ok = project.SetRenderSettings({"SelectAllFrames": True, "TargetDir": str(target), "CustomName": "f",
                                    "ExportVideo": True, "ExportAudio": False, "FormatWidth": w,
                                    "FormatHeight": h, "ExportAlpha": False, "DataBurnIn": "None"})
    if not ok:
        raise RuntimeError("SetRenderSettings failed")
    job = project.AddRenderJob()
    if not job or not project.StartRendering([job], False):
        raise RuntimeError(f"render job {job!r} did not start")
    start = time.time()
    while project.IsRenderingInProgress():
        if time.time() - start > timeout_s:
            project.StopRendering()
            raise RuntimeError("render timed out")
        time.sleep(2)
    status = project.GetRenderJobStatus(job)
    project.DeleteRenderJob(job)  # the queue entry only; the rendered files stay
    if status.get("JobStatus") != "Complete":
        raise RuntimeError(f"render ended {status}")
    return sorted(target.glob("*.png"))


def author_click_drx(click: Click, out: Path) -> Path:
    """Write a .drx holding one Magic Mask 2 subject click at `click` (centred, y-up coordinates in the grade)."""
    js = ("const fs=require('fs');const m=require(process.argv[1]);"
          "const c=JSON.parse(process.argv[4]);"
          "fs.writeFileSync(process.argv[3],m.placeMagicMaskClick(fs.readFileSync(process.argv[2],'utf8'),c));")
    payload = json.dumps({"frame": click.frame, "x": click.u - 0.5, "y": 0.5 - click.v})
    subprocess.run([NODE, "-e", js, str(MM_AUTHOR), str(MM_TEMPLATE), str(out), payload], check=True)
    return out


def track_and_render(project, resolve, timeline, click: Click, work: Path) -> tuple[list[tuple[Path, Path]], float]:
    """Track one click through the clip and render the two matte variants. Returns frame pairs and white level."""
    resolve.OpenPage("color")
    project.SetCurrentTimeline(timeline)
    item = timeline.GetItemListInTrack("video", 1)[0]
    drx = author_click_drx(click, work / "click.drx")
    if not item.GetNodeGraph().ApplyGradeFromDRX(str(drx), 0):
        raise RuntimeError("ApplyGradeFromDRX failed")
    # CreateMagicMask blocks until the track is done (minutes at 3840²); it is the slow step.
    if not item.CreateMagicMask("BI"):
        raise RuntimeError("CreateMagicMask returned False (no click in the grade?)")
    renders = {}
    # Resolve clamps the CDL: slope ≥ 0.0005, and the offset tops out at ~0.5 of full scale (setting 1 or more
    # reads back 0.499753; smaller settings map non-linearly, 0.5 → 0.000999). So "white" is not 1.0. The level
    # it really reached is measured from the renders, where a fully masked pixel gives B − A = level exactly.
    for variant, offset in (("inside_black", "0 0 0"), ("inside_white", "1 1 1")):
        if not item.SetCDL({"NodeIndex": "1", "Slope": "0 0 0", "Offset": offset, "Power": "1 1 1",
                            "Saturation": "1"}):
            raise RuntimeError(f"SetCDL {variant} failed")
        renders[variant] = render(project, timeline, work / variant, "RGB8")
    if len(renders["inside_black"]) != len(renders["inside_white"]):
        raise RuntimeError("the two matte renders differ in frame count")
    pairs = list(zip(renders["inside_black"], renders["inside_white"]))
    level = max(_core_level(a, b) for a, b in pairs[:: max(1, len(pairs) // 24)])
    if level < 0.25:
        raise RuntimeError(f"inside_white reached only {level:.3f} of full scale; the matte would be too coarse")
    return pairs, level


def run_magic_mask(project, resolve, source: Source, spec: PassSpec, fp: str, clicks: list[Click],
                   work: Path) -> tuple[Iterator[np.ndarray], dict]:
    """Track every click on its own timeline (ApplyGradeFromDRX replaces a whole graph) and union the mattes."""
    tracks = []
    for k, click in enumerate(clicks):
        timeline = timeline_for(project, source, f"{spec.name}-{fp}-{source.lens}-k{k}")
        kwork = work / f"k{k}"
        kwork.mkdir(parents=True, exist_ok=True)
        pairs, level = track_and_render(project, resolve, timeline, click, kwork)
        tracks.append({"click": asdict(click), "timeline": timeline.GetName(), "pairs": pairs, "level": level})
    counts = {len(t["pairs"]) for t in tracks}
    if len(counts) != 1:
        raise RuntimeError(f"click renders differ in frame count: {counts}")

    def frames() -> Iterator[np.ndarray]:
        for i in range(counts.pop() if counts else 0):
            yield np.maximum.reduce([_matte(*t["pairs"][i], t["level"]) for t in tracks])

    details = {"clicks": [{k: v for k, v in t.items() if k != "pairs"} for t in tracks]}
    return frames(), details


def _core_level(black: Path, white: Path) -> float:
    """B − A in the fully masked core of one frame (99.9th percentile, so soft edges and noise do not count)."""
    a = cv2.imread(str(black), cv2.IMREAD_UNCHANGED).astype(np.float32)
    b = cv2.imread(str(white), cv2.IMREAD_UNCHANGED).astype(np.float32)
    return float(np.percentile((b - a).mean(axis=2), 99.9)) / 255


def _matte(black: Path, white: Path, level: float = 1.0) -> np.ndarray:
    """Matte from renders with the masked region forced to 0 (black) and to `level` (white), level in 0..1."""
    a = cv2.imread(str(black), cv2.IMREAD_UNCHANGED).astype(np.float32)
    b = cv2.imread(str(white), cv2.IMREAD_UNCHANGED).astype(np.float32)
    return np.clip((b - a).mean(axis=2) / level, 0, 255).round().astype(np.uint8)


def run_depth_map(project, resolve, source: Source, spec: PassSpec, fp: str,
                  work: Path) -> tuple[Iterator[np.ndarray], dict]:
    params = spec.params
    timeline = timeline_for(project, source, f"{spec.name}-{fp}-{source.lens}")
    item = timeline.GetItemListInTrack("video", 1)[0]
    comp = item.GetFusionCompByIndex(1) if item.GetFusionCompCount() else item.AddFusionComp()
    media_in, media_out = comp.FindTool("MediaIn1"), comp.FindTool("MediaOut1")
    depth = comp.FindTool("DepthMap1") or comp.AddTool("DepthMap", -32768, -32768)
    for key in ("Mode", "DepthMapPreview"):
        depth.SetInput(key, params[key])
    depth.ConnectInput("Input", media_in)
    media_out.ConnectInput("Input", depth)
    files = render(project, timeline, work / "map", "RGB16")
    # The map is grey (R = G = B); keep one channel.
    return (cv2.imread(str(f), cv2.IMREAD_UNCHANGED)[:, :, 2] for f in files), {"timeline": timeline.GetName()}


# ---------------------------------------------------------------- outputs and acceptance

def write_outputs(frames: Iterable[np.ndarray], source: Source, spec: PassSpec, fp: str, out: Path,
                  record: dict, bands: dict) -> dict:
    """Write each frame as it comes (a clip at 3840² does not fit in memory as a list) and its statistics."""
    out.mkdir(parents=True, exist_ok=True)
    rows, shape, non_constant = [], None, 0
    for i, img in enumerate(frames):
        name = f"{i:06d}.png"
        cv2.imwrite(str(out / name), img)
        full = float(np.iinfo(img.dtype).max)
        shape = shape or img.shape
        non_constant += int(img.min() != img.max())
        rows.append({"frame": i, "t_ms": round(i * 1001 / 30, 3), "file": name, "dtype": str(img.dtype),
                     "mean": float(img.mean() / full), "coverage": float((img > full / 2).mean())})
    table = pl.DataFrame(rows)
    table.write_parquet(out / "frames.parquet")
    checks = acceptance(table, shape, non_constant, source, spec, bands)
    meta = {"pass": spec.name, "use": spec.use, "fingerprint": fp, "clip": source.clip, "lens": source.lens,
            "source": {"path": str(source.path), "sha256": source.sha256, "frames": source.frames},
            "params": spec.params, "code_version": code_version(spec), **record, "acceptance": checks}
    (out / "pass.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    return meta


def acceptance(table: pl.DataFrame, shape: tuple, non_constant: int, source: Source, spec: PassSpec,
               bands: dict) -> dict:
    """Frame count and size always; for masks, the class's band from the config: `every_frame` (the subject is
    in every frame of this lens) and `coverage = [min, max]` (fraction of the frame, median over frames)."""
    checks = {"frame_count": table.height, "frame_count_ok": table.height == source.frames,
              "size": [shape[1], shape[0]], "single_channel": len(shape) == 2, "non_constant_frames": non_constant}
    if spec.params.get("method") == "magic_mask":
        cov = table["coverage"]
        checks |= {"coverage_min": cov.min(), "coverage_median": cov.median(), "coverage_max": cov.max(),
                   "frames_with_mask": int((cov > 0).sum()), "band": bands}
        ok = checks["frame_count_ok"]
        if bands.get("every_frame", True):
            ok = ok and checks["frames_with_mask"] == table.height
        if "coverage" in bands:
            lo, hi = bands["coverage"]
            checks["coverage_in_band"] = lo <= checks["coverage_median"] <= hi
            ok = ok and checks["coverage_in_band"]
        checks["ok"] = ok
    else:
        checks["ok"] = checks["frame_count_ok"] and non_constant == table.height
    return checks


def run(config_path: Path, pass_name: str, clip: str, lens: str) -> dict:
    cfg = load(config_path)
    spec = PASSES[pass_name]
    source = find_source(cfg, clip, lens)
    extra = {}
    clicks = []
    if spec.params.get("method") == "magic_mask":
        clicks = [Click(int(f), float(u), float(v)) for f, u, v in cfg.clicks(spec.name, source.clip, lens)]
        if not clicks:
            raise RuntimeError(f"no [prompts.{spec.name}] clicks for {source.clip}/{lens} in {config_path}")
        extra = {"clicks": [asdict(c) for c in clicks]}
    fp = fingerprint(source.sha256, spec, extra)
    out = cfg.local_stage_root / "resolve" / spec.name / fp / source.clip / lens
    if (out / "pass.json").exists():
        return json.loads((out / "pass.json").read_text()) | {"skipped": True}
    work = cfg.local_stage_root / "resolve" / "_render" / spec.name / fp / source.clip / lens
    work.mkdir(parents=True, exist_ok=True)
    resolve = resolve_app()
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None or project.GetName() != cfg.name:
        raise RuntimeError(f"open project is {project and project.GetName()!r}; run the bootstrap first")
    started = time.time()
    if clicks:
        frames, details = run_magic_mask(project, resolve, source, spec, fp, clicks, work)
    else:
        frames, details = run_depth_map(project, resolve, source, spec, fp, work)
    record = {"resolve_version": resolve.GetVersionString(), "render_dir": str(work), **details}
    meta = write_outputs(frames, source, spec, fp, out, record, cfg.acceptance.get(spec.name, {}))
    meta["seconds"] = round(time.time() - started, 1)
    (out / "pass.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    resolve.GetProjectManager().SaveProject()
    return meta | {"output_dir": str(out)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    parser.add_argument("pass_name", choices=sorted(PASSES))
    parser.add_argument("clip")
    parser.add_argument("lens")
    args = parser.parse_args(argv)
    try:
        meta = run(args.config, args.pass_name, args.clip, args.lens)
    except RuntimeError as exc:
        print(f"pass stopped: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(meta, indent=2, sort_keys=True))
    return 0 if meta["acceptance"]["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
