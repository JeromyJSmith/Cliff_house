"""Contract: the workbench notebook runs end to end against the real Hugging Face storage.

Needs a Hugging Face login with read access to the dataset repo and write access to the bucket. Pixeltable gets a
throwaway home so the run never touches a persistent catalog.
"""
import os
import re
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parents[1]
NOTEBOOK = REPO / "notebooks" / "cliff_house.py"


def _header_requirements() -> list[Requirement]:
    block = re.search(r"^# /// script\n(.*?)^# ///$", NOTEBOOK.read_text(), re.S | re.M).group(1)
    toml = "\n".join(line.removeprefix("# ").removeprefix("#") for line in block.splitlines())
    return [Requirement(r) for r in tomllib.loads(toml)["dependencies"]]


def test_notebook_header_only_names_project_dependencies():
    project = {Requirement(r).name for r in tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["dependencies"]}
    assert {r.name for r in _header_requirements()} <= project


def _working_tree_archive(dest: Path) -> Path:
    # Tracked and new files as they are on disk, minus Git LFS data, so the notebook provisions the toolchain from
    # the code under test.
    git = lambda *a: subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True, check=True).stdout
    lfs = set(git("lfs", "ls-files", "-n").splitlines())
    files = [f for f in git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
             if f not in lfs and (REPO / f).is_file()]
    with tarfile.open(dest, "w:gz") as tar:
        for f in files:
            tar.add(REPO / f, arcname=f"Cliff_house-test/{f}")
    return dest


def test_notebook_runs_against_hugging_face(tmp_path):
    env = os.environ | {
        "PIXELTABLE_HOME": str(tmp_path / "pxt"),
        "CLIFF_HOUSE_REPO_ARCHIVE": _working_tree_archive(tmp_path / "repo.tar.gz").as_uri(),
    }
    result = subprocess.run([sys.executable, str(NOTEBOOK)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert result.returncode == 0, result.stderr[-4000:]
