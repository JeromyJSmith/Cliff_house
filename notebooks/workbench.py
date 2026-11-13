# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo[recommended,lsp,mcp,otel]>=0.25",
#     "pixeltable>=0.7",
#     "polars>=1.30",
#     "duckdb>=1.3",
#     "pyarrow>=20",
#     "opencv-python-headless>=5.0",
#     "huggingface-hub>=1.0",
#     "fsspec>=2024.6",
#     "requests>=2.32",
#     "torch>=2.8",
#     "torchvision>=0.23",
#     "transformers>=5.0",
#     "scipy>=1.14",
#     "pycolmap-cuda12==4.2.1; sys_platform == 'linux'",
#     "pycolmap==4.2.1; sys_platform == 'darwin'",
#     "pyyaml>=6.0",
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
    return BUCKET, HF_REPO, PXT_DIR, SESSION_ID, SOURCES_URI


@app.cell
def _():
    from huggingface_hub import HfApi, get_token

    # One token for every client: huggingface_hub resolves HF_TOKEN or the login cache; Polars only reads the cache,
    # which molab does not have, so it is handed the same token explicitly.
    HF_STORAGE = {"token": get_token()}
    # Raises on a missing or invalid token, so nothing below runs against anonymous access.
    identity = HfApi(token=HF_STORAGE["token"]).whoami()["name"]
    return HF_STORAGE, identity


@app.cell
def _(HF_STORAGE, SOURCES_URI, identity, mo):
    import polars as pl

    manifest = pl.read_parquet(f"{SOURCES_URI}/_manifest/sources.parquet", storage_options=HF_STORAGE)
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
    return pxt, sources


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
    TOOLCHAIN_FILES = ("pyproject.toml", "pixi.lock", "src", "tools")

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

    # The `native` environment: native tools only; the kernel already has the Python stack (including torch).
    subprocess.run([str(pixi), "install", "--frozen", "-e", "native", "--manifest-path",
                    str(repo_dir / "pyproject.toml")], check=True)
    native_prefix = repo_dir / ".pixi" / "envs" / "native"
    mo.md(f"pixi {PIXI_VERSION} installed the locked toolchain into `{native_prefix}`")
    return native_prefix, pixi, repo_dir


@app.cell
def _(BUCKET, HF_STORAGE, WORK, capture, mo, pixi, repo_dir, subprocess):
    import sys

    from huggingface_hub import HfFileSystem as _HfFileSystem
    from huggingface_hub import batch_bucket_files as _batch_bucket_files

    # Spirula's release builds are Vulkan-only, and molab's NVIDIA Vulkan driver cannot create an instance
    # (llvmpipe only). Its CUDA backend built without the GUI needs no display, GL or Vulkan, so it is compiled here
    # once per (commit, GPU architecture, recipe) and cached in the bucket; later sessions only download it.
    SPIRULA_COMMIT = "667e353bca3941303a4d93e93aa8ae3f2c202712"  # tag v2026.11.12
    _caps = capture(["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"])
    cuda_archs = sorted({line.strip().replace(".", "") for line in _caps.get("output", "").splitlines()
                         if line.strip()} if _caps.get("returncode") == 0 else set())
    _fs = _HfFileSystem(token=HF_STORAGE["token"])
    _manifest = str(repo_dir / "pyproject.toml")

    spirula_cuda = {}
    for _arch in cuda_archs:
        _fp = subprocess.run(
            [sys.executable, str(repo_dir / "tools" / "spirula_fingerprint.py"), str(repo_dir / "pixi.lock"),
             str(repo_dir / "tools" / "build_spirula_cuda.sh"), SPIRULA_COMMIT, _arch],
            capture_output=True, text=True, check=True).stdout.strip()
        _remote = f"toolchain/spirula-cuda/{_fp}"
        _local = WORK / "spirula-cuda" / _fp
        if not _fs.exists(f"buckets/{BUCKET}/{_remote}/spirula"):
            subprocess.run([str(pixi), "run", "--frozen", "-e", "spirula-build", "--manifest-path", _manifest,
                            str(repo_dir / "tools" / "build_spirula_cuda.sh"), SPIRULA_COMMIT, _arch, str(_local)],
                           check=True)
            _batch_bucket_files(BUCKET, add=[(str(_local / n), f"{_remote}/{n}") for n in ("spirula", "BUILD_INFO")])
        _fs.get(f"buckets/{BUCKET}/{_remote}/", str(_local) + "/", recursive=True)
        (_local / "spirula").chmod(0o755)
        spirula_cuda[_arch] = _local / "spirula"

    # The runtime environment is Linux-only, and needed exactly where a CUDA binary exists.
    for _env in ["spirula-run"] if spirula_cuda else []:
        subprocess.run([str(pixi), "install", "--frozen", "-e", _env, "--manifest-path", _manifest], check=True)
    spirula_run_prefix = repo_dir / ".pixi" / "envs" / "spirula-run"
    mo.md(f"Spirula CUDA binaries: {', '.join(f'sm_{a}' for a in spirula_cuda) or 'none (no NVIDIA GPU on this host)'}")
    return spirula_cuda, spirula_run_prefix


@app.cell
def _(HOST, SPIRULA_BUILDS, SPIRULA_VERSION, WORK, capture, fetch_verified, mo, native_prefix, os, spirula_cuda,
      spirula_run_prefix, zipfile):
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
        "spirula_cuda": {f"sm_{a}": capture([str(b), "train", "--help"],
                                            env=os.environ | {"LD_LIBRARY_PATH": str(spirula_run_prefix / "lib")})
                         for a, b in spirula_cuda.items()},
    }
    mo.ui.table([{"check": k, "result": str(v)[:300]} for k, v in probe.items()])
    return (probe, spirula)


@app.cell
def _():
    from huggingface_hub import HfFileSystem, hf_hub_download, sync_bucket
    return HfFileSystem, hf_hub_download, sync_bucket


@app.cell
def _(mo):
    mo.md("""
    ## Stage 2 — frames

    Every source video becomes sharpness-selected frames, one rig-consistent set per clip (`cliff_house.frames`).
    Work is keyed by fingerprint (source SHA-256, stage code, parameters): a session downloads and processes only
    sources whose frames are not already in the bucket, then builds the Pixeltable `frames` table from the bucket.
    """)
    return


@app.cell
def _(BUCKET, HF_REPO, HF_STORAGE, HfFileSystem, PXT_DIR, WORK, hf_hub_download, manifest, mo, native_prefix, os,
      pl, pxt, repo_dir, shutil, sync_bucket):
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(repo_dir / "src"))
    from cliff_house import frames as frames_stage
    from cliff_house.storage import retry

    FRAME_PARAMS = frames_stage.Params()
    # Tests narrow the run to named clips so it stays small; a normal session processes every source video.
    _only = [c for c in os.environ.get("CLIFF_HOUSE_FRAME_CLIPS", "").split(",") if c]
    videos = (manifest
              .filter(pl.col("capture_time_utc").is_not_null() & pl.col("path").str.contains("/source/video/"))
              .with_columns(clip=pl.col("path").str.extract(r"([^/]+)\.[^.]+$"))
              .filter(pl.lit(not _only) | pl.col("clip").is_in(_only))
              .with_columns(fingerprint=pl.col("sha256").map_elements(
                  lambda sha: frames_stage.fingerprint(sha, FRAME_PARAMS), return_dtype=pl.String)))
    _fs = HfFileSystem(token=HF_STORAGE["token"])
    _remote = lambda row: f"stages/frames/{row['fingerprint']}/{row['clip']}"
    missing = [r for r in videos.iter_rows(named=True)
               if not _fs.exists(f"buckets/{BUCKET}/{_remote(r)}/frames.parquet")]

    for _row in missing:
        _src_path = _Path(retry(hf_hub_download, HF_REPO, _row["path"], repo_type="dataset",
                                token=HF_STORAGE["token"], local_dir=WORK / "sources"))
        _source = frames_stage.probe(_src_path, _row["sha256"], ffprobe=str(native_prefix / "bin" / "ffprobe"))
        _out = WORK / "frames" / _remote(_row)
        shutil.rmtree(_out, ignore_errors=True)
        frames_stage.extract(_source, FRAME_PARAMS, _out, ffmpeg=str(native_prefix / "bin" / "ffmpeg"))
        retry(sync_bucket, str(_out), f"hf://buckets/{BUCKET}/{_remote(_row)}", token=HF_STORAGE["token"])
        _src_path.unlink()

    def _read(row):
        with _fs.open(f"buckets/{BUCKET}/{_remote(row)}/frames.parquet", "rb") as f:
            return pl.read_parquet(f).with_columns(
                clip=pl.lit(row["clip"]), fingerprint=pl.lit(row["fingerprint"]),
                file=pl.lit(f"{_remote(row)}/") + pl.col("file"))
    frame_rows = pl.concat([_read(r) for r in videos.iter_rows(named=True)])

    frames = pxt.create_table(
        f"{PXT_DIR}/frames",
        {"clip": pxt.String, "fingerprint": pxt.String, "camera": pxt.String, "frame": pxt.Int,
         "candidate": pxt.Int, "t_ms": pxt.Int, "sharpness": pxt.Float, "file": pxt.String},
        primary_key=["clip", "camera", "frame"], if_exists="replace")
    frames.insert(frame_rows.to_dicts())
    mo.md(f"Frames: **{frame_rows.height:,}** across **{videos.height}** sources "
          f"({len(missing)} processed this session) — `hf://buckets/{BUCKET}/stages/frames/`")
    return FRAME_PARAMS, frame_rows, frames, frames_stage, retry, videos


@app.cell
def _(mo):
    mo.md("""
    ## Stage 3 — masks (SAM 3)

    SAM 3 concept segmentation (Pixeltable `sam3_for_segmentation`) finds every instance of each prompt — by default
    the operator and passers-by (`person`) — on every frame. The union, grown a few pixels, becomes a training mask
    (0 = ignore, 255 = use). Keyed by the frames fingerprint, SAM 3 revision and prompts; only clips without masks in
    the bucket are processed.
    """)
    return


@app.cell
def _(BUCKET, HF_STORAGE, HfFileSystem, PXT_DIR, WORK, frames_stage, mo, pl, pxt, retry, shutil, sync_bucket,
      videos):
    import itertools as _it

    import PIL.Image as _Image
    from pixeltable.functions.huggingface import sam3_for_segmentation as _sam3

    from cliff_house import masks as masks_stage

    MASK_PARAMS = masks_stage.Params()
    _fs = HfFileSystem(token=HF_STORAGE["token"])
    clips = videos.with_columns(mask_fingerprint=pl.col("fingerprint").map_elements(
        lambda fp: masks_stage.fingerprint(fp, MASK_PARAMS), return_dtype=pl.String))
    _frames_remote = lambda r: f"stages/frames/{r['fingerprint']}/{r['clip']}"
    _masks_remote = lambda r: f"stages/masks/{r['mask_fingerprint']}/{r['clip']}"
    masks_missing = [r for r in clips.iter_rows(named=True)
                     if not _fs.exists(f"buckets/{BUCKET}/{_masks_remote(r)}/masks.parquet")]

    def _segment(clip_frames, frames_dir):
        work = pxt.create_table(f"{PXT_DIR}/mask_work", {"camera": pxt.String, "frame": pxt.Int,
                                                          "batch": pxt.Int, "image": pxt.Image},
                                 if_exists="replace")
        for i, prompt in enumerate(MASK_PARAMS.prompts):
            work.add_computed_column(**{f"p{i}": _sam3(
                work.image, text=prompt, model_id=MASK_PARAMS.model_id, revision=MASK_PARAMS.revision,
                threshold=MASK_PARAMS.threshold, mask_threshold=MASK_PARAMS.mask_threshold)})
        small_dir = frames_dir / "_seg"
        small_dir.mkdir(exist_ok=True)
        for b, batch in enumerate(_it.batched(clip_frames.iter_rows(named=True), 16)):
            rows = []
            for r in batch:
                img = _Image.open(frames_dir / r["file"])
                size = masks_stage.segmentation_size(*img.size, MASK_PARAMS)
                small = small_dir / f"{r['camera']}_{r['frame']:06d}.jpg"
                img.resize(size).save(small, quality=95)
                rows.append({"camera": r["camera"], "frame": r["frame"], "batch": b, "image": str(small),
                             "_full": img.size})
            work.insert([{k: v for k, v in r.items() if k != "_full"} for r in rows])
            cols = [getattr(work, f"p{i}") for i in range(len(MASK_PARAMS.prompts))]
            results = {(x["camera"], x["frame"]): x for x in
                       work.where(work.batch == b).select(work.camera, work.frame, *cols).collect()}
            for r in rows:
                res = results[(r["camera"], r["frame"])]
                instances = [res[f"p{i}"]["masks"] for i in range(len(MASK_PARAMS.prompts))]
                w, h = r["_full"]
                yield r["camera"], r["frame"], masks_stage.training_mask(
                    masks_stage.unwanted(instances, (h, w)), MASK_PARAMS.grow_px)

    for _row in masks_missing:
        _frames_dir = WORK / "frames" / _frames_remote(_row)
        retry(_fs.get, f"buckets/{BUCKET}/{_frames_remote(_row)}/", str(_frames_dir) + "/", recursive=True)
        _clip_frames = pl.read_parquet(_frames_dir / "frames.parquet")
        _out = WORK / "masks" / _masks_remote(_row)
        shutil.rmtree(_out, ignore_errors=True)
        masks_stage.write(_segment(_clip_frames, _frames_dir), _out)
        retry(sync_bucket, str(_out), f"hf://buckets/{BUCKET}/{_masks_remote(_row)}", token=HF_STORAGE["token"])

    def _read_masks(r):
        with _fs.open(f"buckets/{BUCKET}/{_masks_remote(r)}/masks.parquet", "rb") as f:
            return pl.read_parquet(f).with_columns(clip=pl.lit(r["clip"]), fingerprint=pl.lit(r["mask_fingerprint"]),
                                                   file=pl.lit(f"{_masks_remote(r)}/") + pl.col("file"))
    mask_rows = pl.concat([_read_masks(r) for r in clips.iter_rows(named=True)])
    masks = pxt.create_table(
        f"{PXT_DIR}/masks",
        {"clip": pxt.String, "fingerprint": pxt.String, "camera": pxt.String, "frame": pxt.Int,
         "ignored_fraction": pxt.Float, "file": pxt.String},
        primary_key=["clip", "camera", "frame"], if_exists="replace")
    masks.insert(mask_rows.to_dicts())
    mo.md(f"Masks: **{mask_rows.height:,}** frames, median ignored "
          f"{mask_rows['ignored_fraction'].median():.1%} ({len(masks_missing)} clips processed this session)")
    return MASK_PARAMS, mask_rows, masks, masks_stage


@app.cell
def _(mo):
    mo.md("""
    ## Stage 4 — poses (COLMAP)

    One structure-from-motion solve over every clip's frames and masks. The A1's lenses are one rig whose
    lens-to-lens transform comes from the camera's factory calibration (telemetry `lens.json`); each A1 lens is one
    camera across all clips; each phone clip is its own camera. Keyed by the masks' fingerprints and the solver
    parameters. The solve is in metres via the 71.3 mm factory baseline — a hint until LiDAR confirms it.
    """)
    return


@app.cell
def _(BUCKET, HF_STORAGE, HfFileSystem, WORK, clips, mo, pl, retry, sync_bucket):
    import json as _json

    from cliff_house import poses as poses_stage

    _fs = HfFileSystem(token=HF_STORAGE["token"])
    # The factory rig must be the same on every A1 clip; a disagreement means mixed cameras, which must stop the solve.
    _lens_files = sorted(_fs.glob(f"buckets/{BUCKET}/stages/telemetry/*/*/lens.json"))
    _rigs = {poses_stage.insta360_rig(_json.loads(_fs.read_text(f))) for f in _lens_files}
    if len(_rigs) != 1:
        raise ValueError(f"factory rig differs across {len(_lens_files)} telemetry records: {_rigs}")
    POSE_PARAMS = poses_stage.Params(rig=_rigs.pop())

    pose_fp = poses_stage.fingerprint(clips["mask_fingerprint"].to_list(), POSE_PARAMS)
    _remote = f"stages/poses/{pose_fp}"
    pose_missing = [] if _fs.exists(f"buckets/{BUCKET}/{_remote}/summary.json") else [pose_fp]

    def _frame_set(row):
        frames_dir = WORK / "frames" / f"stages/frames/{row['fingerprint']}/{row['clip']}"
        masks_dir = WORK / "masks" / f"stages/masks/{row['mask_fingerprint']}/{row['clip']}"
        for remote_dir, local in ((f"stages/frames/{row['fingerprint']}/{row['clip']}", frames_dir),
                                  (f"stages/masks/{row['mask_fingerprint']}/{row['clip']}", masks_dir)):
            retry(_fs.get, f"buckets/{BUCKET}/{remote_dir}/", str(local) + "/", recursive=True)
        table = pl.read_parquet(frames_dir / "frames.parquet")
        cameras = sorted(table["camera"].unique())
        # Two synchronized streams are the A1 rig (shared lens cameras); one stream is a phone clip (its own camera).
        folders = {c: c for c in cameras} if len(cameras) == 2 else {c: row["clip"] for c in cameras}
        return poses_stage.FrameSet(row["clip"], frames_dir, masks_dir, folders,
                                    tuple((r["camera"], r["frame"]) for r in table.iter_rows(named=True)))

    for _fp in pose_missing:
        _work = WORK / "poses" / _fp
        _sets = [_frame_set(r) for r in clips.iter_rows(named=True)]
        _rec = poses_stage.solve(_sets, _work, POSE_PARAMS)
        (_work / "summary.json").write_text(
            _json.dumps(poses_stage.summary(_rec, sum(len(s.frames) for s in _sets)), indent=1))
        retry(sync_bucket, str(_work), f"hf://buckets/{BUCKET}/{_remote}", token=HF_STORAGE["token"],
              include=["sparse/**", "summary.json"])
    pose_summary = _json.loads(_fs.read_text(f"buckets/{BUCKET}/{_remote}/summary.json"))
    mo.md(f"Poses `{pose_fp}`: **{pose_summary['registered_images']:,} / {pose_summary['total_images']:,}** images "
          f"registered, {pose_summary['points3D']:,} points, {pose_summary['mean_reprojection_error_px']} px; "
          f"rig baselines {pose_summary['rig_baselines_m']} m")
    return POSE_PARAMS, pose_fp, pose_missing, pose_summary, poses_stage


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
