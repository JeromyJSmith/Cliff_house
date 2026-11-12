# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo[recommended,lsp,mcp,otel]>=0.25",
#     "pixeltable>=0.7",
#     "polars>=1.30",
#     "duckdb>=1.3",
#     "pyarrow>=20",
#     "huggingface-hub>=1.0",
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
    """)
    return


@app.cell
def _():
    CLIENT, PROPERTY = "frasier", "cliff-house"
    HF_REPO = f"ojeromyo/{CLIENT}-{PROPERTY}"
    SOURCES_URI = f"hf://datasets/{HF_REPO}"
    BUCKET = HF_REPO
    PXT_DIR = f"{CLIENT}/{PROPERTY.replace('-', '_')}"
    return BUCKET, PXT_DIR, SOURCES_URI


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
def _(BUCKET, by_kind, mo):
    import datetime as dt
    import tempfile
    from pathlib import Path

    from huggingface_hub import batch_bucket_files

    session_id = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    remote = f"sessions/{session_id}/sources_by_kind.parquet"
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "sources_by_kind.parquet"
        by_kind.write_parquet(local)
        batch_bucket_files(BUCKET, add=[(str(local), remote)])
    mo.md(f"Session summary written to `hf://buckets/{BUCKET}/{remote}`")
    return


if __name__ == "__main__":
    app.run()
