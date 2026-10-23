import json

from contracts.models import MemoryItem, Outcome
from paths import ROOT
from mocks.loader import (
    append_correction,
    load_memory,
    load_resources,
    load_s1_stub,
    load_s2_stub,
)
from contracts.models import Correction
from datetime import datetime, timezone


def test_loader_validates_objects():
    memory = load_memory("F10")
    assert memory and all(isinstance(item, MemoryItem) for item in memory)
    assert memory[0].kind == "policy"
    assert isinstance(load_s1_stub("F01"), Outcome)
    assert isinstance(load_s2_stub("F10"), Outcome)
    resources = load_resources()
    assert resources.boats and resources.shelters


def test_correction_pair_memory_files():
    left = load_memory("C01-a")
    right = load_memory("C01-b")
    assert all(item.kind != "correction" for item in left)
    assert any(item.kind == "correction" and item.source_case_id == "C01-a" for item in right)


def test_runtime_correction_appears_on_pair(tmp_path, monkeypatch):
    before = len(load_memory("C01-b"))
    append_correction(
        Correction(
            correction_id="corr-test",
            case_id="C01-a",
            corrected_by="operator",
            field="priority",
            old_value="P3",
            new_value="P1",
            reason="water at the door plus elderly is rescue",
            created_at=datetime.now(timezone.utc),
        )
    )
    after = load_memory("C01-b")
    assert len(after) == before + 1
    assert any("corr-test" in item.memory_id for item in after)
    static_left = json.loads((ROOT / "mocks/memory_context/C01-a.json").read_text())
    assert all(item["kind"] != "correction" for item in static_left)
