"""Contract: the workbench notebook runs end to end against the real Hugging Face storage.

Needs a Hugging Face login with read access to the dataset repo and write access to the bucket. Pixeltable gets a
throwaway home so the run never touches a persistent catalog.
"""
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parents[1]
NOTEBOOK = REPO / "notebooks" / "workbench.py"


def _header_requirements() -> list[Requirement]:
    block = re.search(r"^# /// script\n(.*?)^# ///$", NOTEBOOK.read_text(), re.S | re.M).group(1)
    toml = "\n".join(line.removeprefix("# ").removeprefix("#") for line in block.splitlines())
    return [Requirement(r) for r in tomllib.loads(toml)["dependencies"]]


def test_notebook_header_only_names_project_dependencies():
    project = {Requirement(r).name for r in tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["dependencies"]}
    assert {r.name for r in _header_requirements()} <= project


def test_notebook_runs_against_hugging_face(tmp_path):
    env = os.environ | {
        "PIXELTABLE_HOME": str(tmp_path / "pxt"),
        # The working tree, read through fsspec's file filesystem exactly as molab reads GitHub.
        "CLIFF_HOUSE_REPO": REPO.as_uri(),
        # One short clip (12 s, both lenses) keeps the frames stage's real Hugging Face round trip small.
        "CLIFF_HOUSE_FRAME_CLIPS": "VID_20261110_132328_041",
    }
    result = subprocess.run([sys.executable, str(NOTEBOOK)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stderr[-4000:]
