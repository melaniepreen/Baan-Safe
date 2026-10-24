"""Unit checks for make sync conflict helpers (no network, no modal)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_workspace.py"


def _load():
    spec = importlib.util.spec_from_file_location("sync_workspace", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_meaningful_dirty_ignores_vscode_only():
    mod = _load()
    assert mod.meaningful_dirty("?? .vscode/\n") is False
    assert mod.meaningful_dirty(" M Makefile\n") is True
    assert mod.meaningful_dirty("?? .vscode/\n M README.md\n") is True


def test_keep_mode_default_and_override(monkeypatch: pytest.MonkeyPatch):
    mod = _load()
    monkeypatch.delenv("SYNC_KEEP", raising=False)
    assert mod.keep_mode() == "local"
    monkeypatch.setenv("SYNC_KEEP", "remote")
    assert mod.keep_mode() == "remote"
    monkeypatch.setenv("SYNC_KEEP", "manual")
    assert mod.keep_mode() == "manual"
    monkeypatch.setenv("SYNC_KEEP", "weird")
    assert mod.keep_mode() == "local"


def test_porcelain_paths_handles_rename():
    mod = _load()
    assert mod.porcelain_paths("R  old.py -> new.py\n") == ["new.py"]
