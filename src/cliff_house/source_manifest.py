"""Inventory of the local data tree as it will exist on the Hugging Face dataset repo.

One row per uploaded file. Paths are POSIX, relative to the data root, so the same string addresses the file
locally and at hf://datasets/<repo>/<path>. Symlinks upload as their target's bytes; the row keeps the link text
as provenance. The manifest itself is excluded from its own inventory.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import polars as pl

MANIFEST_PATH = Path("_manifest/sources.parquet")
EXCLUDED_NAMES = frozenset({".DS_Store"})
VIDEO_SUFFIXES = frozenset({".insv", ".mp4", ".mov"})

SCHEMA = pl.Schema({
    "path": pl.String,
    "bytes": pl.Int64,
    "sha256": pl.String,
    "mtime_ns": pl.Int64,
    "link_target": pl.String,
    "capture_time_utc": pl.Datetime("us", "UTC"),
})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _capture_time(path: Path) -> dt.datetime | None:
    # Embedded container time is authoritative over the filename clock, which is known to drift on these cameras.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    stamp = json.loads(probe.stdout).get("format", {}).get("tags", {}).get("creation_time")
    return dt.datetime.fromisoformat(stamp) if stamp else None


def _row(root: Path, path: Path) -> dict:
    stat = path.stat()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": stat.st_size,
        "sha256": _sha256(path),
        "mtime_ns": stat.st_mtime_ns,
        "link_target": os.readlink(path) if path.is_symlink() else None,
        "capture_time_utc": _capture_time(path) if path.suffix.lower() in VIDEO_SUFFIXES else None,
    }


def inventory(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.name not in EXCLUDED_NAMES
        and (p.is_file() or p.is_symlink())
        and p.relative_to(root) != MANIFEST_PATH
    )


def build(root: Path, workers: int = 8) -> pl.DataFrame:
    paths = inventory(root)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(lambda p: _row(root, p), paths))
    return pl.DataFrame(rows, schema=SCHEMA)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="data root, e.g. ../data")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = build(root)
    out = root / MANIFEST_PATH
    out.parent.mkdir(exist_ok=True)
    manifest.write_parquet(out)
    print(json.dumps({
        "manifest": str(out),
        "rows": manifest.height,
        "bytes": manifest["bytes"].sum(),
        "links": manifest["link_target"].is_not_null().sum(),
        "videos_with_capture_time": manifest["capture_time_utc"].is_not_null().sum(),
    }))


if __name__ == "__main__":
    main()
