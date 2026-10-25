"""End-of-turn case record write (MEMORY_IMPL=mubit, control plane mocked).

`memory.mubit.retrieve` / `write` are monkeypatched so no socket opens. The
gateway must trace `memory_write`, never break the turn on an ingest error,
and `GET /metrics` must count retrievals, hits, writes, and duplicate merges.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from contracts.models import (
    CaseState,
    ExtractedFields,
    MemoryItem,
    MemoryRecord,
    TranscriptTurn,
)
from gateway.route import handle
from memory import mubit
from trace import read_traces


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def control_plane(monkeypatch):
    """Fake Mubit memory: scripted retrieve, recording write."""
    monkeypatch.setenv("MEMORY_IMPL", "mubit")
    monkeypatch.setenv("S1_IMPL", "real")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    state: dict = {"items": [], "fail_write": False, "records": [], "lessons": []}

    def fake_retrieve(case: CaseState) -> list[MemoryItem]:
        return [
            item
            for item in state["items"]
            if not (item.kind == "similar_case" and item.source_case_id == case.case_id)
        ]

    def fake_write(record: MemoryRecord) -> None:
        if state["fail_write"]:
            raise RuntimeError("Mubit memory ingest failed HTTP 500.")
        state["records"].append(record)

    monkeypatch.setattr(mubit, "retrieve", fake_retrieve)
    monkeypatch.setattr(mubit, "write", fake_write)
    monkeypatch.setattr(mubit, "write_correction", state["lessons"].append)
    return state


def _similar(source_case_id: str, relevance: float = 0.95) -> MemoryItem:
    return MemoryItem(
        memory_id=f"mem-{source_case_id}",
        kind="similar_case",
        summary=f"Case {source_case_id}: needs=water; route=welfare_distribution",
        relevance=relevance,
        source_case_id=source_case_id,
    )


def _write_events(client, case_id: str) -> list[dict]:
    trace = client.get(f"/cases/{case_id}/trace").json()
    return [event for event in trace if event["stage"] == "memory_write"]


def test_turn_writes_record_traces_and_counts(client, control_plane):
    client.post("/cases", json={"fixture_id": "F01"})
    turned = client.post(
        "/cases/F01/turns",
        json={"t_ms": 90000, "speaker": "operator", "text": "Noted the water request."},
    )
    assert turned.status_code == 200
    assert turned.json()["decision"]["final_route"] == "welfare_distribution"

    # One record, built from the case fields and the router's decision.
    assert len(control_plane["records"]) == 1
    record = control_plane["records"][0]
    assert record.case_id == "F01"
    assert record.evidence.model_dump(mode="json") == turned.json()["case"]["fields"]
    assert record.decision.final_route.value == "welfare_distribution"
    assert record.decision.next_action.value == turned.json()["decision"]["next_action"]
    assert record.corrections == []
    assert record.record_id == "rec-F01-" + str(len(turned.json()["case"]["transcript"]))

    events = _write_events(client, "F01")
    assert len(events) == 1
    note = events[0]["notes"]
    assert "status=ok" in note
    assert "kind=case_record" in note
    assert "mbt_should_not_appear" not in note
    assert events[0]["latency_ms"] >= 0

    memory = client.get("/metrics").json()["memory"]
    assert memory["mode"] == "mubit"
    assert memory["retrieve_count"] == 1
    assert memory["hit_count"] == 0
    assert memory["item_total"] == 0
    assert memory["hit_rate"] == 0.0
    assert memory["write_count"] == 1
    assert memory["write_error_count"] == 0
    assert memory["duplicate_merge_count"] == 0


def test_repeat_caller_duplicate_merges_and_write_error_soft_fails(client, control_plane):
    client.post("/cases", json={"fixture_id": "F01"})
    client.post(
        "/cases/F01/turns",
        json={"t_ms": 90000, "speaker": "operator", "text": "Noted."},
    )
    # The next turn retrieves an earlier case's record; ingest is down.
    control_plane["items"] = [_similar("case-earlier")]
    control_plane["fail_write"] = True
    turned = client.post(
        "/cases/F01/turns",
        json={"t_ms": 95000, "speaker": "caller", "text": "Still need the water."},
    )
    assert turned.status_code == 200, "an ingest error must not break the turn"
    decision = turned.json()["decision"]
    assert decision["final_route"] == "duplicate_merge"
    assert decision["next_action"] == "finalize_case"
    assert decision["source_outcomes"][0]["system"] == "system_1"
    assert len(control_plane["records"]) == 1

    events = _write_events(client, "F01")
    assert [("status=ok" in e["notes"], "status=error" in e["notes"]) for e in events] == [
        (True, False),
        (False, True),
    ]
    assert "error=RuntimeError" in events[1]["notes"]
    assert "HTTP 500" not in events[1]["notes"]

    memory = client.get("/metrics").json()["memory"]
    assert memory["retrieve_count"] == 2
    assert memory["hit_count"] == 1
    assert memory["item_total"] == 1
    assert memory["hit_rate"] == pytest.approx(0.5)
    assert memory["write_count"] == 1
    assert memory["write_error_count"] == 1
    assert memory["duplicate_merge_count"] == 1


def test_own_case_record_does_not_merge_against_itself(client, control_plane):
    client.post("/cases", json={"fixture_id": "F01"})
    # The control plane returns this case's own record from turn 1.
    control_plane["items"] = [_similar("F01", 0.99)]
    turned = client.post(
        "/cases/F01/turns",
        json={"t_ms": 90000, "speaker": "operator", "text": "Noted."},
    )
    assert turned.status_code == 200
    assert turned.json()["decision"]["final_route"] == "welfare_distribution"
    assert client.get("/metrics").json()["memory"]["duplicate_merge_count"] == 0


def test_stored_corrections_ride_on_the_record(client, control_plane):
    client.post("/cases", json={"fixture_id": "F01"})
    response = client.post(
        "/cases/F01/corrections",
        json={
            "corrected_by": "operator",
            "field": "priority",
            "old_value": "P3",
            "new_value": "P2",
            "reason": "elderly in the household",
        },
    )
    assert response.status_code == 200
    assert len(control_plane["lessons"]) == 1
    assert control_plane["records"][-1].corrections[0].reason == "elderly in the household"
    events = _write_events(client, "F01")
    kinds = [e["notes"].split("kind=")[1].split(";")[0] for e in events]
    assert kinds == ["correction", "case_record"]
    assert all("status=ok" in e["notes"] for e in events)
    assert client.get("/metrics").json()["memory"]["write_count"] == 2


def test_no_stub_fallback_and_mock_mode_do_not_write(monkeypatch, control_plane):
    case = CaseState(
        case_id="case-unknown",
        caller_id_hash="synthetic:case-unknown",
        transcript=[TranscriptTurn(t_ms=0, speaker="caller", text="We need water.")],
        fields=ExtractedFields(),
        received_at=datetime.now(timezone.utc),
    )
    # Stub path, no stub file: the fixture_stub fallback is not a case to remember.
    monkeypatch.setenv("S1_IMPL", "stub")
    decision = handle(case, use_stubs=True)
    assert decision.source_outcomes[0].missing_evidence == ["fixture_stub"]
    assert control_plane["records"] == []
    assert [e for e in read_traces("case-unknown") if e.stage == "memory_write"] == []

    # Mock memory never writes, even for a real decision.
    monkeypatch.setenv("MEMORY_IMPL", "mock")
    monkeypatch.setenv("S1_IMPL", "real")
    handle(case, use_stubs=True)
    assert control_plane["records"] == []
    assert [e for e in read_traces("case-unknown") if e.stage == "memory_write"] == []
