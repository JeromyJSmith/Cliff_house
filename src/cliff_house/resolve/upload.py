"""Mirror the Resolve, mask, equirect and sample stages from the local stage root into the project's HF bucket.

    pixi run python -m cliff_house.resolve.upload configs/resolve/<project>.toml [--dry-run]

Uploads `stages/gear_mask/`, `stages/static_mask/`, `stages/resolve/`, `stages/equirect/` (the levelled 360 masters
with their frames.parquet, review stills and pass.json) and `stages/sample/` (the 3 fps analysis sample) as they are on
disk (outputs, frames.parquet, pass.json, static_mask.json, templates and positions, bootstrap records, logs, review
sheets and README.txt status files). Never deletes anything in the bucket, and skips files already there with the
same size and time. Resolve's render intermediates are left out (the PNGs under
`resolve/_render/`): nothing reads them and they are reproducible from the fingerprint. The small `click.drx`
grades beside them are uploaded, because they record what each mask was given.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from huggingface_hub import batch_bucket_files, sync_bucket

from ..storage import retry
from .config import load

STAGES = ("gear_mask", "static_mask", "resolve", "equirect", "sample")  # small stages first, then the large media
EXCLUDE = ["_render/**/*.png"]
BATCH_FILES, BATCH_BYTES = 200, 512 * 2**20


def _batches(ops: list) -> list[list]:
    """Group upload operations so each commit is small: a dropped connection then costs one batch, and a re-run
    resumes after the last committed batch (sync skips what is already there)."""
    out, cur, size = [], [], 0
    for op in ops:
        if cur and (len(cur) >= BATCH_FILES or size + (op.size or 0) > BATCH_BYTES):
            out.append(cur)
            cur, size = [], 0
        cur.append(op)
        size += op.size or 0
    return out + ([cur] if cur else [])


def upload(config_path: Path, dry_run: bool = False, log=print) -> dict:
    cfg = load(config_path)
    bucket = cfg.bucket.removeprefix("hf://buckets/").rstrip("/")
    done = {}
    for stage in STAGES:
        local = cfg.local_stage_root / stage
        if not local.is_dir():
            continue
        plan = retry(sync_bucket, str(local), f"hf://buckets/{bucket}/stages/{stage}", exclude=EXCLUDE,
                     dry_run=True, quiet=True)
        ops = [op for op in plan.operations if op.action == "upload"]
        total = sum(op.size or 0 for op in ops)
        log(f"{stage}: {len(ops)} files, {total / 1e9:.2f} GB to upload")
        if dry_run:
            done[stage] = {"files": len(ops), "bytes": total, "uploaded": 0}
            continue
        sent = 0
        for k, batch in enumerate(_batches(ops), 1):
            retry(batch_bucket_files, bucket,
                  add=[(str(local / op.path), f"stages/{stage}/{op.path}") for op in batch])
            sent += sum(op.size or 0 for op in batch)
            log(f"  {stage} batch {k}: {len(batch)} files, {sent / 1e9:.2f} / {total / 1e9:.2f} GB")
        done[stage] = {"files": len(ops), "bytes": total, "uploaded": sent}
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    print(upload(args.config, args.dry_run, log=lambda m: print(m, flush=True)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
