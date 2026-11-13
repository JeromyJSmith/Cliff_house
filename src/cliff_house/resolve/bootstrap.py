"""Stage R0 — bootstrap: open (or create) the project a config names, apply its settings before any media exists,
read every setting back, and write a record of what Resolve actually reported.

    pixi run python -m cliff_house.resolve.bootstrap configs/resolve/<project>.toml

Idempotent: re-running on a configured project changes nothing and writes the same record (apart from its time).
It never deletes a project, a library or media. If a setting cannot be applied (for example a frame rate on a
project whose timelines already hold media) it stops and says which, rather than continuing on a wrong project.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from .config import ProjectConfig, load, settings_match
from .connect import resolve_app

CODE_VERSION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]


def project_media_dir(cfg: ProjectConfig) -> Path:
    return cfg.storage_root / "ProjectMedia"


def preflight(resolve, cfg: ProjectConfig) -> dict:
    """Facts that must hold before anything is created. Returns them for the record; raises on a failed check."""
    product, version = resolve.GetProductName(), resolve.GetVersionString()
    if "Studio" not in product:
        raise RuntimeError(f"{product}: the analysis passes (Magic Mask, Depth Map, external scripting) need Studio")
    volumes = resolve.GetMediaStorage().GetMountedVolumeList() or []
    if not volumes or Path(volumes[0]) != cfg.storage_root:
        raise RuntimeError(f"Media Storage's first location is {volumes[:1]}, expected {cfg.storage_root}. "
                           "Set it in Preferences → System → Media Storage (no scripting call sets it).")
    if not cfg.storage_root.is_dir():
        raise RuntimeError(f"{cfg.storage_root} is not mounted")
    return {"product": product, "version": version, "media_storage": volumes,
            "fusion_version": resolve.Fusion().GetAttrs().get("FUSIONS_Version")}


def open_library(pm, cfg: ProjectConfig) -> dict:
    if cfg.library:
        libraries = pm.GetDatabaseList() or []
        match = [db for db in libraries if db.get("DbName") == cfg.library]
        if not match:
            raise RuntimeError(f"Project library {cfg.library!r} is not in Resolve ({libraries}). Add it once in "
                               "Project Manager → Project Libraries → Add; scripting can switch libraries but "
                               "cannot create one.")
        if pm.GetCurrentDatabase() != match[0] and not pm.SetCurrentDatabase(match[0]):
            raise RuntimeError(f"could not switch to library {match[0]}")
    return pm.GetCurrentDatabase()


def open_project(pm, cfg: ProjectConfig):
    """Load the project, or create it with its media location on the storage root. Returns (project, created)."""
    current = pm.GetCurrentProject()
    if current and current.GetName() == cfg.name:
        return current, False
    if cfg.name in (pm.GetProjectListInCurrentFolder() or []):
        project = pm.LoadProject(cfg.name)
        if project is None:
            raise RuntimeError(f"project {cfg.name!r} exists but did not load")
        return project, False
    project_media_dir(cfg).mkdir(parents=True, exist_ok=True)
    project = pm.CreateProject(cfg.name, str(project_media_dir(cfg)))
    if project is None:
        raise RuntimeError(f"CreateProject({cfg.name!r}) failed")
    return project, True


def apply_settings(project, cfg: ProjectConfig) -> dict:
    for key, value in cfg.settings.items():
        if key.endswith("Location"):
            Path(value).mkdir(parents=True, exist_ok=True)
    before = project.GetSetting() or {}
    pending = settings_match(cfg.settings, before)
    if pending and project.GetTimelineCount() > 0 and "timelineFrameRate" in pending:
        raise RuntimeError(f"frame rate differs {pending['timelineFrameRate']} but the project already has "
                           "timelines; Resolve cannot change it now. Use a new project name.")
    for key in pending:  # one at a time: SetSettings stops at the first failure and hides which one
        if not project.SetSetting(key, cfg.settings[key]):
            raise RuntimeError(f"SetSetting({key!r}, {cfg.settings[key]!r}) returned False")
    after = project.GetSetting() or {}
    still = settings_match(cfg.settings, after)
    if still:
        raise RuntimeError(f"settings did not read back: {still}")
    return {"changed": sorted(pending), "readback": {k: after.get(k) for k in sorted(cfg.settings)},
            "project_media_location": after.get("projectMediaLocation")}


def record_path(cfg: ProjectConfig, config_path: Path) -> Path:
    fp = hashlib.sha256(config_path.read_bytes() + CODE_VERSION.encode()).hexdigest()[:16]
    return cfg.local_stage_root / "resolve" / "bootstrap" / fp / "record.json"


def run(config_path: Path) -> dict:
    cfg = load(config_path)
    resolve = resolve_app()
    facts = preflight(resolve, cfg)
    pm = resolve.GetProjectManager()
    library = open_library(pm, cfg)
    project, created = open_project(pm, cfg)
    settings = apply_settings(project, cfg)
    if not pm.SaveProject():
        raise RuntimeError("SaveProject failed")
    record = {"config": str(config_path), "code_version": CODE_VERSION, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              **facts, "library": library, "project": cfg.name, "created": created, **settings}
    out = record_path(cfg, config_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True))
    record["record_path"] = str(out)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args.config), indent=2, sort_keys=True))
    except RuntimeError as exc:
        print(f"bootstrap stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
