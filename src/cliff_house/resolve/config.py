"""Load and validate a Resolve project config. Pure: no Resolve connection needed, so it is unit-tested."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

REQUIRED_SETTINGS = ("timelineResolutionWidth", "timelineResolutionHeight", "timelineFrameRate")


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    storage_root: Path
    library: str
    local_stage_root: Path
    bucket: str
    remux_manifest: Path
    settings: dict[str, str]

    @property
    def fps(self) -> float:
        return float(self.settings["timelineFrameRate"].split()[0])


def load(path: str | Path) -> ProjectConfig:
    raw = tomllib.loads(Path(path).read_text())
    project, stages = raw["project"], raw["stages"]
    storage_root = Path(project["storage_root"])
    if not storage_root.is_absolute():
        raise ValueError(f"storage_root must be absolute, got {storage_root}")
    settings = {k: str(v).format(storage_root=storage_root) for k, v in raw.get("settings", {}).items()}
    missing = [k for k in REQUIRED_SETTINGS if k not in settings]
    if missing:
        raise ValueError(f"settings must set {missing} before media exists")
    return ProjectConfig(name=project["name"], storage_root=storage_root, library=project.get("library", ""),
                         local_stage_root=Path(stages["local_root"]), bucket=stages["bucket"],
                         remux_manifest=Path(stages["remux_manifest"]), settings=settings)


def settings_match(wanted: dict[str, str], actual: dict) -> dict[str, tuple[str, object]]:
    """Return {key: (wanted, actual)} for every setting that did not read back as wanted.

    Resolve returns timelineFrameRate as a number (29.97) although it is set as a string ('29.97' or '29.97 DF');
    numbers are compared numerically, everything else as strings.
    """
    mismatches = {}
    for key, value in wanted.items():
        got = actual.get(key)
        if isinstance(got, (int, float)) and not isinstance(got, bool):
            try:
                if abs(float(value.split()[0]) - float(got)) < 1e-6:
                    continue
            except ValueError:
                pass
        elif str(got) == value:
            continue
        mismatches[key] = (value, got)
    return mismatches
