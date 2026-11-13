"""Pure checks of the Resolve stages: config loading, setting readback comparison, fingerprints, pass tags and the
two-render matte recovery. None of these talk to Resolve."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from cliff_house.resolve import config, passes

CONFIG_DIR = Path(__file__).parents[1] / "configs" / "resolve"


def test_every_project_config_loads_and_sets_timeline_before_media():
    configs = sorted(CONFIG_DIR.glob("*.toml"))
    assert configs
    for path in configs:
        cfg = config.load(path)
        assert cfg.storage_root.is_absolute()
        for key in config.REQUIRED_SETTINGS:
            assert key in cfg.settings
        assert "{storage_root}" not in "".join(cfg.settings.values())


def test_config_rejects_missing_timeline_settings(tmp_path):
    path = tmp_path / "p.toml"
    path.write_text('[project]\nname="p"\nstorage_root="/x"\n[stages]\nlocal_root="/s"\nbucket="b"\n'
                    'remux_manifest="/m"\n[settings]\ntimelineResolutionWidth="10"\n')
    with pytest.raises(ValueError, match="timelineFrameRate"):
        config.load(path)


def test_settings_match_compares_frame_rate_numerically():
    wanted = {"timelineFrameRate": "29.97", "timelineResolutionWidth": "3840"}
    assert config.settings_match(wanted, {"timelineFrameRate": 29.97, "timelineResolutionWidth": "3840"}) == {}
    assert config.settings_match(wanted, {"timelineFrameRate": 24.0, "timelineResolutionWidth": "3840"}) == {
        "timelineFrameRate": ("29.97", 24.0)}
    assert "timelineResolutionWidth" in config.settings_match(wanted, {"timelineFrameRate": 29.97})


def test_only_masks_may_feed_reconstruction():
    reconstruction = {p.name for p in passes.PASSES.values() if p.use == "reconstruction"}
    assert reconstruction == {"mask_people"}
    assert all(passes.PASSES[n].params.get("method") == "magic_mask" for n in reconstruction)


def test_clicks_come_from_config_by_full_name_or_suffix():
    cfg = config.load(CONFIG_DIR / "frasier-cliff-house.toml")
    by_suffix = cfg.clicks("mask_people", "VID_20261110_132328_041", "cam0")
    assert len(by_suffix) >= 1 and all(len(c) == 3 for c in by_suffix)
    assert cfg.clicks("mask_people", "VID_20261110_132328_041", "cam1") == []


def test_fingerprint_changes_with_source_and_parameters():
    spec = passes.PASSES["depth_map"]
    base = passes.fingerprint("a" * 64, spec, {})
    assert base == passes.fingerprint("a" * 64, spec, {})
    assert base != passes.fingerprint("b" * 64, spec, {})
    other = passes.PassSpec(spec.name, spec.use, {**spec.params, "Mode": "Faster"})
    assert base != passes.fingerprint("a" * 64, other, {})


@pytest.mark.skipif(not passes.MM_AUTHOR.exists(), reason="Magic Mask click author not installed")
def test_magic_mask_fingerprint_includes_the_click():
    spec = passes.PASSES["mask_people"]
    one = passes.fingerprint("a" * 64, spec, {"clicks": [{"frame": 1, "u": 0.5, "v": 0.1}]})
    two = passes.fingerprint("a" * 64, spec, {"clicks": [{"frame": 2, "u": 0.5, "v": 0.1}]})
    assert one != two


@pytest.mark.parametrize("level", [1.0, 0.499753])  # Resolve clamps the CDL offset to ~0.5 (live readback)
def test_matte_is_recovered_from_black_and_white_renders(tmp_path, level):
    rng = np.random.default_rng(0)
    image = rng.integers(0, 256, (32, 32, 3)).astype(np.float64)
    m = np.zeros((32, 32))
    m[8:24, 8:24] = 1.0
    m[8:24, 7] = 0.5  # a soft edge
    inside_black = (1 - m)[..., None] * image
    inside_white = m[..., None] * 255 * level + (1 - m)[..., None] * image
    for name, img in (("a.png", inside_black), ("b.png", inside_white)):
        cv2.imwrite(str(tmp_path / name), img.round().astype(np.uint8))
    matte = passes._matte(tmp_path / "a.png", tmp_path / "b.png", level)
    # 8-bit renders: one rounding step per render, amplified by 1/level.
    assert np.abs(matte.astype(int) - (m * 255).round()).max() <= np.ceil(1 / level) + 1


def test_per_lens_acceptance_replaces_the_class_rule():
    bands = {"every_frame": True, "coverage": [0.04, 0.15], "cam1": {"every_frame": True}}
    assert passes.lens_rule(bands, "cam0") == {"every_frame": True, "coverage": [0.04, 0.15]}
    assert passes.lens_rule(bands, "cam1") == {"every_frame": True}
    cfg = config.load(CONFIG_DIR / "frasier-cliff-house.toml")
    assert "coverage" not in passes.lens_rule(cfg.acceptance["mask_people"], "cam1")


def test_delete_renders_removes_pngs_and_keeps_click_grades(tmp_path):
    for k in ("k0", "k1"):
        for variant in ("inside_black", "inside_white"):
            d = tmp_path / k / variant
            d.mkdir(parents=True)
            for i in range(3):
                (d / f"f{i:08d}.png").write_bytes(b"png")
        (tmp_path / k / "click.drx").write_text("<drx/>")
    assert passes.delete_renders(tmp_path) == 12
    assert not list(tmp_path.rglob("*.png"))
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()) == [
        "k0/click.drx", "k1/click.drx"]
    assert not (tmp_path / "k0" / "inside_black").exists()
