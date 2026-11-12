"""Fingerprint of a Spirula CUDA build: everything that can change the binary, nothing that cannot.

Inputs are the Spirula commit, the CUDA architecture, the build script's bytes, and the exact package URLs the lock
resolves for the `spirula-build` environment — so editing unrelated dependencies does not force a rebuild.

Usage: python spirula_fingerprint.py <pixi.lock> <build_spirula_cuda.sh> <commit> <cuda-arch>   → prints the fingerprint
"""
import hashlib
import sys

import yaml


def fingerprint(lock_text: str, script: bytes, commit: str, arch: str) -> str:
    packages = yaml.safe_load(lock_text)["environments"]["spirula-build"]["packages"]["linux-64"]
    urls = sorted(next(iter(p.values())) for p in packages)
    digest = hashlib.sha256()
    for part in (commit.encode(), f"sm_{arch}".encode(), script, "\n".join(urls).encode()):
        digest.update(hashlib.sha256(part).digest())
    return digest.hexdigest()[:16]


if __name__ == "__main__":
    lock, script, commit, arch = sys.argv[1:]
    print(fingerprint(open(lock).read(), open(script, "rb").read(), commit, arch))
