"""Check a Hugging Face dataset repo against the local source manifest, byte for byte.

The Hub reports SHA-256 for large (LFS/Xet) files and a git blob id for small ones, so each file is compared by
whichever content hash the Hub holds for it. Exit status 0 only when every manifest row exists remotely with the
same size and content and no remote file is unaccounted for.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import polars as pl
from huggingface_hub import HfApi

from cliff_house.source_manifest import MANIFEST_PATH


def _git_blob_id(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def compare(root: Path, repo_id: str) -> dict:
    manifest = pl.read_parquet(root / MANIFEST_PATH)
    remote = {f.path: f for f in HfApi().list_repo_tree(repo_id, recursive=True, expand=True, repo_type="dataset")
              if hasattr(f, "size")}
    expected = {r["path"]: r for r in manifest.iter_rows(named=True)} | {
        MANIFEST_PATH.as_posix(): {"bytes": (root / MANIFEST_PATH).stat().st_size,
                                   "sha256": hashlib.sha256((root / MANIFEST_PATH).read_bytes()).hexdigest()}}
    missing = sorted(set(expected) - set(remote))
    unexpected = sorted(set(remote) - set(expected) - {".gitattributes"})
    mismatched = []
    for path in sorted(set(expected) & set(remote)):
        want, got = expected[path], remote[path]
        same = got.size == want["bytes"] and (
            got.lfs.sha256 == want["sha256"] if got.lfs else got.blob_id == _git_blob_id(root / path))
        if not same:
            mismatched.append(path)
    return {"expected": len(expected), "remote": len(remote), "missing": missing,
            "unexpected": unexpected, "mismatched": mismatched}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("repo_id")
    args = parser.parse_args()
    report = compare(args.root.resolve(), args.repo_id)
    print(json.dumps({k: v if isinstance(v, int) else {"count": len(v), "sample": v[:10]} for k, v in report.items()}))
    sys.exit(0 if not (report["missing"] or report["unexpected"] or report["mismatched"]) else 1)


if __name__ == "__main__":
    main()
