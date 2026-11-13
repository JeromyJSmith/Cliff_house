"""The one place transfer failures are handled: every Hugging Face transfer in the pipeline goes through `retry`.

The Hub's Xet storage drops long-running connections intermittently (seen on two machines at once while the network
itself was healthy). Transfers are idempotent — downloads overwrite, bucket syncs and repo uploads skip what is already
stored — so retrying a dropped transfer is always safe; anything that is not a connection failure is raised at once.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, TypeVar

from huggingface_hub import sync_bucket

T = TypeVar("T")

TRANSIENT = (ConnectionError, TimeoutError)


def retry(fn: Callable[..., T], *args, attempts: int = 6, first_wait_s: float = 15.0,
          sleep: Callable[[float], None] = time.sleep, **kwargs) -> T:
    """Call fn(*args, **kwargs); on a transient connection failure wait (doubling each time) and try again."""
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except TRANSIENT as e:
            if attempt == attempts:
                raise ConnectionError(f"{getattr(fn, '__name__', fn)} failed after {attempts} attempts: {e}") from e
            sleep(first_wait_s * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def fetch(bucket: str, remote: str, local: Path | str, token: str) -> Path:
    """Mirror the bucket folder `remote` into `local`, returning `local`.

    A bucket sync batches and parallelises the transfer; fetching file by file through HfFileSystem was 13x slower
    on the same clip (27.9 s against 2.1 s, identical bytes) and made the poses stage spend most of an hour on it.
    """
    retry(sync_bucket, f"hf://buckets/{bucket}/{remote}", str(local), token=token, quiet=True)
    return Path(local)
