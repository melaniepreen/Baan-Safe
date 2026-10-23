"""Keep tests off the developer's trace file and correction log."""

from __future__ import annotations

import pytest

from api.store import reset


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("MOCK_CORRECTIONS_PATH", str(tmp_path / "corrections.jsonl"))
    monkeypatch.setenv("S1_IMPL", "stub")
    monkeypatch.setenv("S2_IMPL", "stub")
    monkeypatch.setenv("MEMORY_IMPL", "mock")
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    reset()
    yield
    reset()
