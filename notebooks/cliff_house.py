# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo[recommended,lsp,mcp,otel]>=0.25",
#     "pixeltable>=0.7",
#     "polars>=1.30",
#     "duckdb>=1.3",
#     "pyarrow>=20",
#     "huggingface-hub>=1.0",
#     "fsspec>=2024.6",
#     "requests>=2.32",
# ]
# ///
# [LAW:one-source-of-truth] exception: molab installs only from this PEP 723 header, so it repeats a subset of
# pyproject.toml's dependencies; tests/test_notebook.py fails if a name here is missing from pyproject.toml.

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md("""
    # Cliff House workbench — Frasier

    Hugging Face is the only durable store. Sources live in the versioned dataset repo; everything this notebook
    produces goes to the bucket. Pixeltable is rebuilt from them in session scratch every time the notebook runs,
    so a fresh molab session is just *open and run*. Requires the `HF_TOKEN` secret (molab sidebar → Secrets).
    Design and rationale: `docs/SPEC.md` in the repository.
    """)
    return


@app.cell
def _():
    import datetime as dt

    CLIENT, PROPERTY = "frasier", "cliff-house"
    HF_REPO = f"ojeromyo/{CLIENT}-{PROPERTY}"
    SOURCES_URI = f"hf://datasets/{HF_REPO}"
    BUCKET = HF_REPO
    PXT_DIR = f"{CLIENT}/{PROPERTY.replace('-', '_')}"
    SESSION_ID = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return BUCKET, PXT_DIR, SESSION_ID, SOURCES_URI


@app.cell
def _():
    from huggingface_hub import HfApi

    # Raises on a missing or invalid token, so nothing below runs against anonymous access.
    identity = HfApi().whoami()["name"]
    return (identity,)


@app.cell
def _(SOURCES_URI, identity, mo):
    import polars as pl

    manifest = pl.read_parquet(f"{SOURCES_URI}/_manifest/sources.parquet")
    mo.md(f"Signed in as **{identity}** · manifest: **{manifest.height:,}** files, "
          f"**{manifest['bytes'].sum() / 1e9:.1f} GB**")
    return manifest, pl


@app.cell
def _(PXT_DIR, manifest):
    import pixeltable as pxt

    pxt.create_dir(PXT_DIR, parents=True, if_exists="ignore")
    # Derived from the manifest every session, so replacing is the correct semantics, not a reset of real state.
    sources = pxt.create_table(
        f"{PXT_DIR}/sources",
        {
            "path": pxt.String,
            "bytes": pxt.Int,
            "sha256": pxt.String,
            "mtime_ns": pxt.Int,
            "link_target": pxt.String | None,
            "capture_time_utc": pxt.Timestamp | None,
        },
        primary_key="path",
        if_exists="replace",
    )
    sources.insert(manifest.to_dicts())
    return (sources,)


@app.cell
def _(manifest, mo, pl, sources):
    import duckdb

    loaded = pl.from_pandas(sources.select(sources.path, sources.bytes).collect().to_pandas())
    by_kind = duckdb.sql("""
        -- client data is <client>/<property>/<kind>/…; shared and manifest data is _<scope>/<kind>/…
        SELECT split_part(path, '/', 1) AS scope,
               split_part(path, '/', if(starts_with(path, '_'), 2, 3)) AS kind,
               count(*)                 AS files,
               round(sum(bytes) / 1e9, 2) AS gb
        FROM loaded GROUP BY ALL ORDER BY gb DESC
    """).pl()
    assert loaded.height == manifest.height, (loaded.height, manifest.height)
    mo.ui.table(by_kind)
    return (by_kind,)


@app.cell
def _(mo):
    mo.md("""
    ## Stage 1 — toolchain

    Native tools come from the repository's `pixi.lock`, installed into session scratch by a pinned, checksummed pixi.
    Spirula is a single pinned, checksummed binary. A probe records what the host provides (glibc, NVIDIA driver,
    Vulkan ICDs) and whether Spirula starts; the report is written to the bucket so it can be read from anywhere.
    """)
    return


@app.cell
def _():
    import hashlib
    import os
    import platform
    import posixpath
    import shutil
    import subprocess
    import urllib.request
    import zipfile
    from pathlib import Path

    import fsspec

    HOST = (platform.system(), platform.machine())
    WORK = Path.home() / ".cache" / "cliff-house"

    PIXI_VERSION = "0.84.1"
    PIXI_BUILDS = {  # release asset name, SHA-256 published by GitHub for that asset
        ("Linux", "x86_64"): ("pixi-x86_64-unknown-linux-musl", "dea64d690020095e70a7194f48a520fb31cf70daef76d8ba38bbcf874b8c84a2"),
        ("Linux", "aarch64"): ("pixi-aarch64-unknown-linux-musl", "45f1d18c9aed7defc4b864b83561dd421dfe460c428e81f446f0e7dd9e3ff09a"),
        ("Darwin", "x86_64"): ("pixi-x86_64-apple-darwin", "775d02cea3c68b41846ca85c1dee2485a45dd8e57416ac0cc906a93114629432"),
        ("Darwin", "arm64"): ("pixi-aarch64-apple-darwin", "3616ba024b78ab48d8f091903f1b2b1a6ac789afd0c6570e84dd86de547741b4"),
    }
    SPIRULA_VERSION = "2026.11.12"
    # Only the headless Linux build is provisioned; the macOS build is a GUI .dmg for the Apple-silicon MacBook.
    SPIRULA_BUILDS = {
        ("Linux", "x86_64"): (f"spirula-{SPIRULA_VERSION}-ubuntu-vulkan-x86_64.zip", "07afb39882f336555633a17023a18c52502dcf0a18b23fe62fa5dd1c24b19a93"),
    }
    # The repository as an fsspec data source (also browsable in molab's storage panel). Its pixi.lock defines the
    # toolchain. Tests point this at file:// on the working tree so they exercise the code under test, not main.
    repo_fs, REPO_ROOT = fsspec.core.url_to_fs(
        os.environ.get("CLIFF_HOUSE_REPO", "github://JeromyJSmith:Cliff_house@main/"))
    TOOLCHAIN_FILES = ("pyproject.toml", "pixi.lock", "src")

    def fetch_verified(url: str, sha256: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        actual = hashlib.sha256(dest.read_bytes()).hexdigest()
        if actual != sha256:
            dest.unlink()
            raise RuntimeError(f"checksum mismatch for {url}: expected {sha256}, got {actual}")
        return dest

    def capture(cmd: list[str], **kwargs) -> dict:
        # The host is a trust boundary: a missing program is a fact to record, not an error.
        exe = shutil.which(cmd[0], path=kwargs.get("env", os.environ).get("PATH"))
        if exe is None:
            return {"cmd": cmd, "found": False}
        result = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=300, **kwargs)
        return {"cmd": cmd, "found": True, "returncode": result.returncode,
                "output": (result.stdout + result.stderr)[-4000:]}
    return (HOST, PIXI_BUILDS, PIXI_VERSION, REPO_ROOT, SPIRULA_BUILDS, SPIRULA_VERSION, TOOLCHAIN_FILES, WORK,
            capture, fetch_verified, os, posixpath, repo_fs, shutil, subprocess, zipfile)


@app.cell
def _(HOST, PIXI_BUILDS, PIXI_VERSION, REPO_ROOT, TOOLCHAIN_FILES, WORK, fetch_verified, mo, posixpath, repo_fs,
      shutil, subprocess):
    _asset, _sha = PIXI_BUILDS[HOST]
    pixi = fetch_verified(
        f"https://github.com/prefix-dev/pixi/releases/download/v{PIXI_VERSION}/{_asset}", _sha, WORK / "bin" / "pixi")
    pixi.chmod(0o755)

    # A fresh copy every session: the lock just fetched, not anything left on disk, defines the environment.
    repo_dir = WORK / "repo"
    shutil.rmtree(repo_dir, ignore_errors=True)
    repo_dir.mkdir(parents=True)
    for _name in TOOLCHAIN_FILES:
        repo_fs.get(posixpath.join(REPO_ROOT, _name), str(repo_dir / _name), recursive=True)

    subprocess.run([str(pixi), "install", "--frozen", "--manifest-path", str(repo_dir / "pyproject.toml")], check=True)
    native_prefix = repo_dir / ".pixi" / "envs" / "default"
    mo.md(f"pixi {PIXI_VERSION} installed the locked toolchain into `{native_prefix}`")
    return (native_prefix,)


@app.cell
def _(HOST, SPIRULA_BUILDS, SPIRULA_VERSION, WORK, capture, fetch_verified, mo, native_prefix, os, zipfile):
    import glob

    _native_env = os.environ | {
        "PATH": f"{native_prefix / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
        "LD_LIBRARY_PATH": f"{native_prefix / 'lib'}{os.pathsep}{os.environ.get('LD_LIBRARY_PATH', '')}",
    }
    _build = SPIRULA_BUILDS.get(HOST)
    if _build:
        _zip = fetch_verified(
            f"https://github.com/harry7557558/spirula-studio/releases/download/v{SPIRULA_VERSION}/{_build[0]}",
            _build[1], WORK / "spirula" / _build[0])
        with zipfile.ZipFile(_zip) as _z:
            _z.extractall(WORK / "spirula" / SPIRULA_VERSION)
        spirula = WORK / "spirula" / SPIRULA_VERSION / "spirula"
        spirula.chmod(0o755)
        spirula_run = capture([str(spirula), "--help"], env=_native_env)
    else:
        spirula = None
        spirula_run = {"found": False, "reason": f"no headless Spirula build for {HOST[0]} {HOST[1]}"}

    probe = {
        "host": {"system": HOST[0], "machine": HOST[1],
                 "glibc": os.confstr("CS_GNU_LIBC_VERSION") if HOST[0] == "Linux" else None},
        "nvidia_smi": capture(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
        "vulkan_icds": sorted(glob.glob("/usr/share/vulkan/icd.d/*.json") + glob.glob("/etc/vulkan/icd.d/*.json")),
        "vulkaninfo": capture(["vulkaninfo", "--summary"], env=_native_env),
        "colmap": capture(["colmap", "-h"], env=_native_env),
        "ffmpeg": capture(["ffmpeg", "-version"], env=_native_env),
        "spirula": {"version": SPIRULA_VERSION, **spirula_run},
    }
    mo.ui.table([{"check": k, "result": str(v)[:300]} for k, v in probe.items()])
    return (probe, spirula)


@app.cell
def _(BUCKET, SESSION_ID, by_kind, mo, probe):
    import json
    import tempfile

    from huggingface_hub import batch_bucket_files

    _prefix = f"sessions/{SESSION_ID}"
    with tempfile.TemporaryDirectory() as _tmp:
        _summary = f"{_tmp}/sources_by_kind.parquet"
        _probe = f"{_tmp}/toolchain_probe.json"
        by_kind.write_parquet(_summary)
        with open(_probe, "w") as _f:
            json.dump(probe, _f, indent=1)
        batch_bucket_files(BUCKET, add=[(_summary, f"{_prefix}/sources_by_kind.parquet"),
                                        (_probe, f"{_prefix}/toolchain_probe.json")])
    mo.md(f"Session outputs written to `hf://buckets/{BUCKET}/{_prefix}/`")
    return


if __name__ == "__main__":
    app.run()
