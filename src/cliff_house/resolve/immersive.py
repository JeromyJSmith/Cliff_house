"""Put the stitched 360 masters on one site timeline in Resolve, in capture order, at their own 2:1 size.

    pixi run python -m cliff_house.resolve.immersive configs/resolve/<project>.toml

Imports every current `stages/equirect/<fp>/<clip>/equirect.mov` into the media-pool bin `equirect-360` and builds
the timeline `site-360` (7680×3840, the masters' size) with the clips in capture order (telemetry GPS start time:
clip 035's file name is an hour off, and it was shot first).

Two steps have no scripting call in Resolve 21.2 (measured 2026-11-12: `SetClipProperty("Projection", …)` refused
25 spellings, and no timeline setting selects an immersive timeline), so they are done once by hand, in seconds:
1. Media pool → bin `equirect-360` → select all → right-click → Clip Attributes → Immersive (or Video) → Projection
   "Equirectangular", Monoscopic → OK.
2. Timeline `site-360` → right-click → Timelines → Timeline Settings → Immersive: "Standard Immersive" (VR360).
Then the viewer's immersive mode lets you look around and scrub the whole site.
"""
from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

import polars as pl

from .connect import resolve_app
from .passes import _folder


def masters(stage_root: Path) -> list[Path]:
    """One equirect.mov per clip: the newest fingerprint whose pass.json accepted it."""
    best: dict[str, tuple[float, Path]] = {}
    for pj in stage_root.glob("equirect/*/*/pass.json"):
        meta = json.loads(pj.read_text())
        if not meta["acceptance"]["ok"]:
            continue
        mtime = pj.stat().st_mtime
        if meta["clip"] not in best or mtime > best[meta["clip"]][0]:
            best[meta["clip"]] = (mtime, pj.parent / "equirect.mov")
    return [p for _, p in best.values()]


def run(config_path: Path) -> dict:
    raw = tomllib.loads(config_path.read_text())
    root = Path(raw["stages"]["local_root"])
    order = pl.read_parquet(root / "telemetry" / "manifest.parquet").sort("gps_first_utc")["clip"].to_list()
    movs = {m.parent.name: m for m in masters(root)}
    ordered = [movs[c] for c in order if c in movs]
    resolve = resolve_app()
    project = resolve.GetProjectManager().GetCurrentProject()
    mp = project.GetMediaPool()
    folder = _folder(mp, mp.GetRootFolder(), "equirect-360")
    have = {c.GetClipProperty("File Path"): c for c in folder.GetClipList() or []}
    mp.SetCurrentFolder(folder)
    missing = [str(p) for p in ordered if str(p) not in have]
    for item in mp.ImportMedia(missing) if missing else []:
        have[item.GetClipProperty("File Path")] = item
    items = [have[str(p)] for p in ordered]
    for i in range(1, project.GetTimelineCount() + 1):
        if project.GetTimelineByIndex(i).GetName() == "site-360":
            return {"timeline": "site-360", "clips": len(items), "existing": True}
    tl = mp.CreateTimelineFromClips("site-360", items)
    for key, value in (("useCustomSettings", "1"), ("timelineResolutionWidth", "7680"),
                       ("timelineResolutionHeight", "3840"), ("timelineOutputResMatchTimelineRes", "1")):
        tl.SetSetting(key, value)
    resolve.GetProjectManager().SaveProject()
    return {"timeline": "site-360", "clips": [p.parent.name for p in ordered],
            "frames": tl.GetEndFrame() - tl.GetStartFrame()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    print(json.dumps(run(parser.parse_args(argv).config), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
