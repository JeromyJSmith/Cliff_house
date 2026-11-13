"""Mirror the Resolve and static-mask stages from the local stage root into the project's HF bucket.

    pixi run python -m cliff_house.resolve.upload configs/resolve/<project>.toml [--dry-run]

Uploads `stages/resolve/` and `stages/static_mask/` as they are on disk (outputs, frames.parquet, pass.json,
static_mask.json, bootstrap records, logs, review sheets). Never deletes anything in the bucket, and skips files
already there with the same size and time. Resolve's render intermediates are left out (the PNGs under
`resolve/_render/`): nothing reads them and they are reproducible from the fingerprint. The small `click.drx`
grades beside them are uploaded, because they record what each mask was given.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from huggingface_hub import sync_bucket

from ..storage import retry
from .config import load

STAGES = ("resolve", "static_mask")
EXCLUDE = ["_render/**/*.png"]


def upload(config_path: Path, dry_run: bool = False) -> dict:
    cfg = load(config_path)
    bucket = cfg.bucket.removeprefix("hf://buckets/").rstrip("/")
    plans = {}
    for stage in STAGES:
        local = cfg.local_stage_root / stage
        if not local.is_dir():
            continue
        plans[stage] = retry(sync_bucket, str(local), f"hf://buckets/{bucket}/stages/{stage}",
                             exclude=EXCLUDE, dry_run=dry_run, quiet=True)
    return plans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    for stage, plan in upload(args.config, args.dry_run).items():
        print(stage, plan if args.dry_run else getattr(plan, "summary", plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
