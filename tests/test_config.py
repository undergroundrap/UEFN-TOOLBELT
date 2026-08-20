"""
Tests for the persistent config store (core/config.py).
==============================================================================
Config survives install.py updates and backs every `config_*` tool, so its
defaults-vs-overrides precedence and its on-disk round-trip are worth pinning.
"""

from __future__ import annotations

import json

import pytest

from UEFN_Toolbelt.core.config import DEFAULTS, Config


@pytest.fixture
def cfg(tmp_path):
    """A Config bound to a throwaway file — never touches the real Saved/ dir."""
    return Config(str(tmp_path / "UEFN_Toolbelt" / "config.json"))


# ── Precedence: user value → DEFAULTS → fallback ──────────────────────────────

def test_get_returns_default_when_unset(cfg):
    assert cfg.get("scatter.default_folder") == DEFAULTS["scatter.default_folder"]


def test_get_returns_fallback_for_unknown_key(cfg):
    assert cfg.get("no.such.key", fallback="sentinel") == "sentinel"


def test_get_returns_none_for_unknown_key_without_fallback(cfg):
    assert cfg.get("no.such.key") is None


def test_user_value_overrides_default(cfg):
    cfg.set("scatter.default_folder", "MyScatter")
    assert cfg.get("scatter.default_folder") == "MyScatter"


# ── Persistence ───────────────────────────────────────────────────────────────

def test_set_persists_to_disk(cfg, tmp_path):
    cfg.set("scatter.default_count", 123)
    written = json.loads((tmp_path / "UEFN_Toolbelt" / "config.json").read_text(encoding="utf-8"))
    assert written["scatter.default_count"] == 123


def test_value_survives_a_new_instance(cfg, tmp_path):
    cfg.set("text.default_color", "#ABCDEF")
    reopened = Config(str(tmp_path / "UEFN_Toolbelt" / "config.json"))
    assert reopened.get("text.default_color") == "#ABCDEF"


def test_corrupt_config_file_does_not_raise(tmp_path):
    """A hand-edited/truncated config must degrade to defaults, not crash the editor."""
    path = tmp_path / "UEFN_Toolbelt" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ this is not json", encoding="utf-8")

    cfg = Config(str(path))
    assert cfg.get("scatter.default_folder") == DEFAULTS["scatter.default_folder"]


# ── reset / is_default / all ──────────────────────────────────────────────────

def test_reset_restores_the_default(cfg):
    cfg.set("scatter.default_radius", 9999.0)
    assert cfg.reset("scatter.default_radius") is True
    assert cfg.get("scatter.default_radius") == DEFAULTS["scatter.default_radius"]


def test_reset_returns_false_when_key_was_never_set(cfg):
    assert cfg.reset("scatter.default_radius") is False


def test_is_default_tracks_customisation(cfg):
    assert cfg.is_default("text.default_size") is True
    cfg.set("text.default_size", 250.0)
    assert cfg.is_default("text.default_size") is False
    cfg.reset("text.default_size")
    assert cfg.is_default("text.default_size") is True


def test_all_merges_defaults_with_overrides(cfg):
    cfg.set("scatter.default_count", 7)
    merged = cfg.all()
    assert merged["scatter.default_count"] == 7                      # override wins
    assert merged["arena.fallback_mesh"] == DEFAULTS["arena.fallback_mesh"]
    assert set(DEFAULTS).issubset(merged)                            # nothing dropped


def test_all_returns_a_copy_not_the_live_dict(cfg):
    snapshot = cfg.all()
    snapshot["scatter.default_count"] = -1
    assert cfg.get("scatter.default_count") == DEFAULTS["scatter.default_count"]
