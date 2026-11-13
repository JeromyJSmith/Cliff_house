"""Stage: sample — every `step`-th source frame of each lens as a numbered JPEG sequence, for site-analysis passes.

    pixi run python -m cliff_house.resolve.sample configs/resolve/<project>.toml [clip ...]

Analysis layers (depth, edges, vegetation, normals) do not need every frame: 3 fps (every 10th frame at 29.97 fps)
covers the walk with heavy overlap and keeps storage sane. Resolve imports a folder of numbered images as one clip,
so each pass runs once per (clip, lens) on this sequence.

Output (bucket layout `stages/sample/<fingerprint>/<clip>/<lens>/`): `000000.jpg …` (JPEG quality `quality`, full
source resolution) and `frames.parquet` mapping each sample index to its source frame and t_ms. Fingerprint = lens
file SHA-256 + this code + params.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl

_MODULE_BYTES = Path(__file__).read_bytes()


@dataclass(frozen=True)
class Params:
    step: int = 10        # every 10th frame: 2.997 fps at 29.97 fps
    quality: int = 2      # ffmpeg -q:v for MJPEG (2 ≈ JPEG quality 95)


def fingerprint(lens_sha256: str, p: Params) -> str:
    digest = hashlib.sha256(hashlib.sha256(_MODULE_BYTES).digest())
    for part in (lens_sha256, json.dumps(asdict(p), sort_keys=True)):
        digest.update(hashlib.sha256(part.encode()).digest())
    return digest.hexdigest()[:16]


def run(lens_path: Path, lens_sha256: str, frames: int, clip: str, lens: str, out_root: Path, p: Params) -> dict:
    fp = fingerprint(lens_sha256, p)
    out = out_root / "sample" / fp / clip / lens
    if (out / "frames.parquet").exists():
        return {"fingerprint": fp, "output_dir": str(out), "skipped": True,
                "samples": pl.read_parquet(out / "frames.parquet").height}
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-hwaccel", "videotoolbox", "-i", str(lens_path),
                    "-vf", f"select='not(mod(n\\,{p.step}))'", "-fps_mode", "passthrough", "-q:v", str(p.quality),
                    "-start_number", "0", str(out / "%06d.jpg")], check=True)
    files = sorted(out.glob("*.jpg"))
    expected = (frames + p.step - 1) // p.step
    table = pl.DataFrame({"sample": list(range(len(files))), "file": [f.name for f in files],
                          "frame": [k * p.step for k in range(len(files))],
                          "t_ms": [round(k * p.step * 1001 / 30, 3) for k in range(len(files))]})
    if len(files) != expected:
        raise RuntimeError(f"{clip}/{lens}: {len(files)} samples, expected {expected}")
    table.write_parquet(out / "frames.parquet")
    return {"fingerprint": fp, "output_dir": str(out), "samples": len(files)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    parser.add_argument("clips", nargs="*")
    args = parser.parse_args(argv)
    raw = tomllib.loads(args.config.read_text())
    manifest = Path(raw["stages"]["remux_manifest"])
    root = Path(raw["stages"]["local_root"])
    p = Params(**raw.get("sample", {}).get("params", {}))
    man = pl.read_parquet(manifest)
    for r in man.sort("clip", "cam").iter_rows(named=True):
        if args.clips and not any(r["clip"] == s or r["clip"].endswith(f"_{s}") for s in args.clips):
            continue
        res = run(manifest.parent / r["fingerprint"] / r["clip"] / f"{r['cam']}.mp4", r["sha256"], r["packets"],
                  r["clip"], r["cam"], root, p)
        print(json.dumps({"clip": r["clip"], "lens": r["cam"], **res}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
