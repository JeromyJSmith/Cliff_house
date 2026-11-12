"""Contract: the project environment provides the full toolchain, and it loads as one consistent process."""
import subprocess
import sys

import pytest

PYTHON_MODULES = [
    "numpy", "scipy", "PIL", "cv2", "pixeltable", "marimo", "huggingface_hub",
    "trimesh", "plyfile", "laspy", "jsonschema", "pycolmap", "open3d", "av",
    "polars", "polars_st", "duckdb", "pyarrow", "shapely", "pyproj",
]

# (command, text its output must contain) — exit codes are not uniform across these tools' help/version flags.
NATIVE_TOOLS = [
    (["ffmpeg", "-version"], "ffmpeg version"),
    (["ffprobe", "-version"], "ffprobe version"),
    (["exiftool", "-ver"], "."),
    (["colmap", "-h"], "COLMAP"),
    (["DensifyPointCloud", "--help"], "OpenMVS"),
    (["pdal", "--version"], "pdal"),
    (["git-lfs", "version"], "git-lfs/"),
    (["marimo", "--version"], "."),
    (["hf", "version"], "version"),
]


def test_all_python_modules_load_together_without_duplicate_native_classes():
    # Duplicate Objective-C classes (two Qt majors, or a wheel-bundled libav beside conda ffmpeg) are a latent
    # crash on macOS; the import must therefore happen in one process and stderr must stay free of the warning.
    result = subprocess.run(
        [sys.executable, "-c", "; ".join(f"import {m}" for m in PYTHON_MODULES)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "is implemented in both" not in result.stderr, result.stderr


@pytest.mark.parametrize(("command", "marker"), NATIVE_TOOLS, ids=[c[0] for c, _ in NATIVE_TOOLS])
def test_native_tool_runs(command, marker, tmp_path):
    # OpenMVS writes a log into its working directory even for --help.
    result = subprocess.run(command, capture_output=True, text=True, cwd=tmp_path)
    assert marker in result.stdout + result.stderr, (command, result.returncode, result.stderr[-2000:])
