"""Contract: the workbench notebook runs end to end against the real Hugging Face storage.

Needs a Hugging Face login with read access to the dataset repo and write access to the bucket.

Pixeltable runs in the machine's ONE home, never a throwaway one (owner rule: "There's a home. The home is the home.").
Isolation is MARPA's qualified persistent QA scope (`marpa_prime_contracts.qa_namespace`): the notebook process gets the
home and database from the shared configuration (`pixeltable.env`), and its sitecustomize rebases every Pixeltable path
under `qa/<suite>/<run>`, so the notebook's `frasier/cliff_house/...` tables cannot reach a real table. One QA writer at a
time; every run is recorded under /Volumes/MARPA/runs/pixeltable-qa/ and its namespace is kept.

torch belongs to the default pixi env (the `ml` feature; owner rule "one torch env"), so the mask stage is never skipped:
an env without torch is out of sync with pixi.lock and fails here with that diagnosis.
"""
import importlib.util
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parents[1]
NOTEBOOK = REPO / "notebooks" / "workbench.py"
# Cliff House is its own project, not a MARPA one: its QA namespace and run records are named for it, even though they
# live in the machine's one Pixeltable home (owner, 2026-11-12). The project's main Pixeltable runs in molab.
PROJECT = "cliff_house"
PIXELTABLE_CONFIG = REPO / "configs" / "pixeltable" / "config.toml"
# The repository that owns the one-home QA scope (and its pixeltable.env).
MARPA_DESK = Path(os.environ.get("MARPA_DESK", "/Volumes/MARPA/apps/marpa-desk"))


def _header_requirements() -> list[Requirement]:
    block = re.search(r"^# /// script\n(.*?)^# ///$", NOTEBOOK.read_text(), re.S | re.M).group(1)
    toml = "\n".join(line.removeprefix("# ").removeprefix("#") for line in block.splitlines())
    return [Requirement(r) for r in tomllib.loads(toml)["dependencies"]]


def test_notebook_header_only_names_project_dependencies():
    meta = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    project = {Requirement(r).name for r in [*meta["dependencies"], *sum(meta.get("optional-dependencies", {}).values(), [])]}
    assert {r.name for r in _header_requirements()} <= project


@pytest.fixture
def qa_scope():
    """MARPA's qualified QA scope module; fails (never skips) when it is not reachable."""
    src = MARPA_DESK / "src"
    assert (src / "marpa_prime_contracts" / "qa_namespace.py").is_file(), (
        f"no qualified Pixeltable QA scope at {MARPA_DESK} (set MARPA_DESK); a throwaway home is not an alternative")
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from marpa_prime_contracts import qa_namespace

    return qa_namespace


def _postgres_pids(fragment: str) -> set[int]:
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=True).stdout
    return {int(line.split(None, 1)[0]) for line in out.splitlines()
            if "bin/postgres" in line and fragment in line}


def test_notebook_runs_against_hugging_face(tmp_path, qa_scope):
    assert importlib.util.find_spec("torch") is not None, (
        f"{sys.executable} has no torch: the default pixi env is out of sync with pixi.lock (torch comes from its `ml` "
        "feature); sync it with `pixi install` rather than skipping the mask stage")

    home, db = qa_scope.canonical_home_and_db()
    pgdata = Path(home) / "pgdata"
    # The one home's postgres must already be up: this env's pixeltable bundles a different postgres major than the one
    # that owns the home, so it may only attach to the running server, never start one.
    pid_file = pgdata / "postmaster.pid"
    assert pid_file.is_file(), f"the one Pixeltable home's server is not running ({pid_file} missing); start it from MARPA"
    server_pid = int(pid_file.read_text().split()[0])
    assert server_pid in _postgres_pids(str(pgdata)), f"postmaster.pid names {server_pid}, which is not running"

    prefix = qa_scope.new_prefix(f"{PROJECT}_test_notebook")
    env = qa_scope.child_env(prefix, base=os.environ | {
        # The working tree, read through fsspec's file filesystem exactly as molab reads GitHub.
        "CLIFF_HOUSE_REPO": REPO.as_uri(),
        # One short clip (12 s, both lenses) keeps the frames stage's real Hugging Face round trip small.
        "CLIFF_HOUSE_FRAME_CLIPS": "VID_20261110_132328_041",
        # Intel Macs report MPS but cannot run it (no unified memory); Apple silicon and CUDA hosts are unaffected.
        "PIXELTABLE_ENABLE_MPS": os.environ.get("PIXELTABLE_ENABLE_MPS", "false"),
        # Cliff House's own Pixeltable settings: the home's config.toml carries an option only MARPA's Pixeltable accepts.
        "PIXELTABLE_CONFIG": str(PIXELTABLE_CONFIG),
    })
    assert (env["PIXELTABLE_HOME"], env["PIXELTABLE_DB"]) == (home, db)

    outcome, result = "error", None
    with qa_scope.writer_lock():
        try:
            result = subprocess.run([sys.executable, str(NOTEBOOK)], capture_output=True, text=True, env=env, cwd=tmp_path)
            outcome = "pass" if result.returncode == 0 else f"exit {result.returncode}"
        finally:
            qa_scope.record_run(prefix, "Cliff_house tests/test_notebook.py::test_notebook_runs_against_hugging_face",
                                outcome, {"project": PROJECT, "repo": str(REPO), "python": sys.executable})

    assert result.returncode == 0, result.stderr[-4000:]
    # Still the one home's server, and no postgres of the run's own (in its working dir or a fallback home) left behind.
    assert server_pid in _postgres_pids(str(pgdata))
    assert not _postgres_pids(str(tmp_path)) and not _postgres_pids(str(Path.home() / ".pixeltable" / "pgdata"))
