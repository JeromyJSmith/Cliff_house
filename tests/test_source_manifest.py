import hashlib
import os

from cliff_house.source_manifest import MANIFEST_PATH, build


def test_manifest_inventories_uploadable_files(tmp_path):
    (tmp_path / "frasier/cliff-house/evidence").mkdir(parents=True)
    real = tmp_path / "frasier/cliff-house/evidence/frame.jpg"
    real.write_bytes(b"jpeg bytes")
    os.symlink("frame.jpg", tmp_path / "frasier/cliff-house/evidence/alias.jpg")
    (tmp_path / "frasier/.DS_Store").write_bytes(b"finder")
    (tmp_path / MANIFEST_PATH.parent).mkdir()
    (tmp_path / MANIFEST_PATH).write_bytes(b"previous manifest")

    rows = {r["path"]: r for r in build(tmp_path).to_dicts()}

    assert set(rows) == {"frasier/cliff-house/evidence/frame.jpg", "frasier/cliff-house/evidence/alias.jpg"}
    expected_sha = hashlib.sha256(b"jpeg bytes").hexdigest()
    assert rows["frasier/cliff-house/evidence/frame.jpg"] | {"mtime_ns": 0} == {
        "path": "frasier/cliff-house/evidence/frame.jpg", "bytes": 10, "sha256": expected_sha,
        "mtime_ns": 0, "link_target": None, "capture_time_utc": None,
    }
    alias = rows["frasier/cliff-house/evidence/alias.jpg"]
    assert (alias["sha256"], alias["bytes"], alias["link_target"]) == (expected_sha, 10, "frame.jpg")
