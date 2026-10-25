"""Keep tests off the developer's trace file and correction log."""

from __future__ import annotations

import pytest

from api.store import reset
from router.ledger import reset as reset_ledger


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    reset_ledger()
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("MOCK_CORRECTIONS_PATH", str(tmp_path / "corrections.jsonl"))
    monkeypatch.setenv("TRAINING_EVENTS_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("S1_IMPL", "stub")
    monkeypatch.setenv("S2_IMPL", "stub")
    monkeypatch.setenv("MEMORY_IMPL", "mock")
    # A local-mode test must set its own tmp file; never the developer's var/.
    monkeypatch.delenv("MEMORY_LOCAL_PATH", raising=False)
    # Same refusal on every machine: a Mubit host, no key, no socket.
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    monkeypatch.delenv("MUBIT_PROJECT_ID", raising=False)
    reset()
    yield
    reset()
