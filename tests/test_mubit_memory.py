"""Mubit control-plane memory client (mocked HTTP)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from contracts.models import (
    CaseState,
    Correction,
    ExtractedFields,
    MemoryRecord,
    NextAction,
    Outcome,
    Priority,
    Route,
    RouterDecision,
    System,
    TranscriptTurn,
)
from memory import mubit


def _mock_transport(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        mubit.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )


def _record(case_id: str = "case-mem", corrections=()) -> MemoryRecord:
    case = _case(case_id)
    outcome = Outcome(
        system=System.system_1,
        outcome="fast_route",
        priority=Priority.P3,
        needs=case.fields.needs,
        route=Route.welfare_distribution,
        confidence=0.9,
        reason="Clear fast-path request with a confident location.",
        requires_human=False,
        escalate=False,
    )
    decision = RouterDecision(
        case_id=case_id,
        next_action=NextAction.create_provisional_dispatch,
        final_priority=Priority.P3,
        final_route=Route.welfare_distribution,
        requires_human=False,
        source_outcomes=[outcome],
    )
    return MemoryRecord(
        record_id=f"rec-{case_id}-1",
        case_id=case_id,
        case_summary="system_1 fast_route after 1 turn(s).",
        evidence=case.fields,
        decision=decision,
        corrections=list(corrections),
    )


def _case(case_id: str = "case-mem") -> CaseState:
    return CaseState(
        case_id=case_id,
        caller_id_hash=f"synthetic:{case_id}",
        transcript=[
            TranscriptTurn(t_ms=0, speaker="caller", text="We need drinking water.")
        ],
        fields=ExtractedFields(
            location="Mae Mo District, Lampang Province",
            location_confidence=0.9,
            people_count=3,
            vulnerable=[],
            medical=False,
            danger=[],
            needs=["water"],
        ),
        received_at=datetime.now(timezone.utc),
    )


def test_retrieve_maps_evidence(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai/compat/openrouter/v1")
    monkeypatch.delenv("MUBIT_PROJECT_ID", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/control/query"
        assert "Bearer mbt_test" in request.headers.get("Authorization", "")
        body = request.read()
        assert b"baansafe-demo" in body
        return httpx.Response(
            200,
            json={
                "final_answer": "Prior water call",
                "evidence": [
                    {
                        "id": "ev-1",
                        "content": "Open case F08 drinking water same household",
                        "origin_entry_type": "fact",
                        "score": 0.94,
                        "source_case_id": "F08",
                    },
                    {
                        "id": "ev-2",
                        "content": "Operator corrected priority to P2",
                        "origin_entry_type": "lesson",
                        "score": 0.8,
                    },
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        mubit.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    items = mubit.retrieve(_case())
    assert len(items) == 2
    assert items[0].memory_id == "ev-1"
    assert items[0].kind == "similar_case"
    assert items[0].source_case_id == "F08"
    assert items[0].relevance == pytest.approx(0.94)
    assert items[1].kind == "correction"


def test_retrieve_refuses_non_mubit_host(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://openrouter.ai/api/v1")
    with pytest.raises(RuntimeError, match="not a Mubit host"):
        mubit.retrieve(_case())


def test_write_correction_ingests_lesson(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/control/ingest"
        seen["body"] = request.read()
        return httpx.Response(200, json={"job_id": "job-1"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        mubit.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    correction = Correction(
        correction_id="corr-1",
        case_id="F02",
        corrected_by="operator",
        field="priority",
        old_value="P2",
        new_value="P3",
        reason="Needs food only",
        created_at=datetime.now(timezone.utc),
        task="s1_triage",
        output_correct="P3",
    )
    mubit.write_correction(correction)
    body = seen["body"]
    assert isinstance(body, bytes)
    assert b"lesson" in body
    assert b"Needs food only" in body


def test_adapter_retrieve_soft_fails_to_empty(monkeypatch):
    monkeypatch.setenv("MEMORY_IMPL", "mubit")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")

    def boom(case):
        raise RuntimeError("control plane down")

    monkeypatch.setattr(mubit, "retrieve", boom)
    from memory.adapter import last_retrieve_error, retrieve

    assert retrieve(_case()) == []
    # The gateway puts this on the memory trace so items=0 is never silent.
    assert last_retrieve_error() == "RuntimeError: control plane down"

    monkeypatch.setattr(mubit, "retrieve", lambda case: [])
    assert retrieve(_case()) == []
    assert last_retrieve_error() is None


def test_store_correction_keeps_local_log_when_ingest_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_IMPL", "mubit")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"error": {"code": "unknown_route", "message": "Unknown route."}}
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        mubit.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    from memory.adapter import store_correction
    from mocks.loader import read_corrections

    correction = Correction(
        correction_id="corr-404",
        case_id="F02",
        corrected_by="operator",
        field="priority",
        old_value="P2",
        new_value="P3",
        reason="kept locally",
        created_at=datetime.now(timezone.utc),
    )
    note = store_correction(correction)
    assert "ingest failed" in note
    assert "HTTP 404 unknown_route" in note
    assert "corr-404" in note
    assert "mbt_should_not_appear" not in note
    assert any(row.correction_id == "corr-404" for row in read_corrections())


def test_adapter_error_text_never_carries_key(monkeypatch):
    monkeypatch.setenv("MEMORY_IMPL", "mubit")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")

    def boom(case):
        raise RuntimeError("leaked mbt_should_not_appear in text")

    monkeypatch.setattr(mubit, "retrieve", boom)
    from memory.adapter import last_retrieve_error, retrieve

    assert retrieve(_case()) == []
    assert "mbt_should_not_appear" not in (last_retrieve_error() or "")


def test_query_404_names_route_code(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai/openai/v1")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"error": {"code": "unknown_route", "message": "Unknown route."}}
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        mubit.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    with pytest.raises(RuntimeError, match="HTTP 404 unknown_route"):
        mubit.retrieve(_case())


def test_control_url_override_wins_but_stays_on_mubit(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai/openai/v1")
    monkeypatch.setenv("MUBIT_CONTROL_URL", "https://memory-demo.mubit.ai")
    assert mubit._gateway_origin() == "https://memory-demo.mubit.ai"
    monkeypatch.setenv("MUBIT_CONTROL_URL", "https://openrouter.ai")
    with pytest.raises(RuntimeError, match="not a Mubit host"):
        mubit._gateway_origin()


def test_project_env_override(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    monkeypatch.setenv("MUBIT_PROJECT_ID", "proj-live-123")

    def handler(request: httpx.Request) -> httpx.Response:
        raw = request.read()
        assert b"proj-live-123" in raw
        assert b'"project_id"' in raw
        return httpx.Response(200, json={"evidence": []})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        mubit.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    assert mubit.retrieve(_case()) == []


def test_write_ingests_case_fact_with_case_id(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/control/ingest"
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"job_id": "job-2"})

    _mock_transport(monkeypatch, handler)
    correction = Correction(
        correction_id="corr-9",
        case_id="case-mem",
        corrected_by="operator",
        field="priority",
        old_value="P2",
        new_value="P3",
        reason="Needs water only",
        created_at=datetime.now(timezone.utc),
    )
    mubit.write(_record("case-mem", corrections=[correction]))

    body = seen["body"]
    assert body["run_id"] == "baansafe-demo"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["type"] == "fact"
    assert item["lane"] == "baansafe-case"
    assert item["source_case_id"] == "case-mem"
    assert item["metadata"]["source_case_id"] == "case-mem"
    assert item["metadata"]["lane"] == "baansafe-case"
    assert item["metadata"]["needs"] == ["water"]
    assert item["metadata"]["route"] == "welfare_distribution"
    # Content keeps the "Case <id>:" prefix as the regex fallback on read.
    assert item["content"].startswith("Case case-mem: needs=water;")
    assert "corrections=1" in item["content"]
    # Nothing from the transcript or resources leaves the process.
    assert "drinking water" not in item["content"]
    assert "caller_ip" not in json.dumps(body)
    assert "mbt_test" not in json.dumps(body)


def test_write_correction_carries_case_id(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={})

    _mock_transport(monkeypatch, handler)
    mubit.write_correction(
        Correction(
            correction_id="corr-2",
            case_id="F02",
            corrected_by="operator",
            field="priority",
            reason="Needs food only",
            created_at=datetime.now(timezone.utc),
        )
    )
    item = seen["body"]["items"][0]
    assert item["lane"] == "baansafe-correction"
    assert item["source_case_id"] == "F02"
    assert item["metadata"] == {
        "source_case_id": "F02",
        "lane": "baansafe-correction",
        "correction_id": "corr-2",
        "task": "priority",
    }


def test_retrieve_maps_lanes_and_source_case_id(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "evidence": [
                    {
                        # Lane at top level, case id only in metadata.
                        "id": "ev-case-meta",
                        "content": "needs=water; decision=create_provisional_dispatch",
                        "origin_entry_type": "lesson",
                        "lane": "baansafe-case",
                        "metadata": {"source_case_id": "F08"},
                        "score": 0.93,
                    },
                    {
                        # Lane only inside metadata, case id only in content.
                        "id": "ev-case-prefix",
                        "content": "Case case-prev: needs=food; route=welfare_distribution",
                        "origin_entry_type": "rule",
                        "metadata": {"lane": "baansafe-case"},
                        "score": 0.91,
                    },
                    {
                        "id": "ev-corr",
                        "content": "Human correction on F02 task=s1_triage output=P3: food only",
                        "origin_entry_type": "fact",
                        "origin_lane": "baansafe-correction",
                        "metadata": {"source_case_id": "F02"},
                        "score": 0.8,
                    },
                    {
                        "id": "ev-policy",
                        "content": "Sphere water minimum per person per day",
                        "origin_entry_type": "fact",
                        "lane": "baansafe-policy",
                        "score": 0.7,
                    },
                    {
                        # No lane, no metadata: the old summary-keyword fallback.
                        "id": "ev-legacy",
                        "content": "Previous attempt failed to reach the household",
                        "run_id": "baansafe-demo",
                        "score": 0.6,
                    },
                ]
            },
        )

    _mock_transport(monkeypatch, handler)
    items = mubit.retrieve(_case("case-now"))
    by_id = {item.memory_id: item for item in items}
    assert by_id["ev-case-meta"].kind == "similar_case"
    assert by_id["ev-case-meta"].source_case_id == "F08"
    assert by_id["ev-case-prefix"].kind == "similar_case"
    assert by_id["ev-case-prefix"].source_case_id == "case-prev"
    assert by_id["ev-corr"].kind == "correction"
    assert by_id["ev-corr"].source_case_id == "F02"
    assert by_id["ev-policy"].kind == "policy"
    assert by_id["ev-policy"].source_case_id is None
    assert by_id["ev-legacy"].kind == "prior_failure"
    # run_id is the project scope, never a case id.
    assert by_id["ev-legacy"].source_case_id is None


def test_retrieve_excludes_the_same_case(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "evidence": [
                    {
                        "id": "self-meta",
                        "content": "Case case-now: needs=water; priority=P3",
                        "lane": "baansafe-case",
                        "metadata": {"source_case_id": "case-now"},
                        "score": 0.99,
                    },
                    {
                        "id": "self-prefix",
                        "content": "Case case-now: needs=water; priority=P3",
                        "lane": "baansafe-case",
                        "score": 0.98,
                    },
                    {
                        "id": "self-correction",
                        "content": "Human correction on case-now task=s1_triage output=P2: medical",
                        "lane": "baansafe-correction",
                        "metadata": {"source_case_id": "case-now"},
                        "score": 0.97,
                    },
                    {
                        "id": "other",
                        "content": "Case case-old: needs=water; priority=P3",
                        "lane": "baansafe-case",
                        "metadata": {"source_case_id": "case-old"},
                        "score": 0.95,
                    },
                ]
            },
        )

    _mock_transport(monkeypatch, handler)
    items = mubit.retrieve(_case("case-now"))
    ids = [item.memory_id for item in items]
    # Own-case facts are dropped; own-case corrections and other cases stay.
    assert ids == ["self-correction", "other"]
    assert items[1].kind == "similar_case"
    assert items[1].source_case_id == "case-old"


def test_adapter_store_record_is_a_noop_in_mock_mode(monkeypatch):
    monkeypatch.setenv("MEMORY_IMPL", "mock")

    def boom(_record):
        raise AssertionError("mock mode must not reach the control plane")

    monkeypatch.setattr(mubit, "write", boom)
    from memory.adapter import store_record

    assert store_record(_record()) is False


def test_adapter_store_record_writes_in_mubit_mode(monkeypatch):
    monkeypatch.setenv("MEMORY_IMPL", "mubit")
    seen: list[MemoryRecord] = []
    monkeypatch.setattr(mubit, "write", seen.append)
    from memory.adapter import store_record

    assert store_record(_record("case-w")) is True
    assert seen[0].case_id == "case-w"


def test_workspace_env_sets_workspace_id(monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_test")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    monkeypatch.setenv("MUBIT_PROJECT_ID", "ws-3e4ac86aadff0b72")

    def handler(request: httpx.Request) -> httpx.Response:
        raw = request.read()
        assert b"ws-3e4ac86aadff0b72" in raw
        assert b'"workspace_id"' in raw
        return httpx.Response(200, json={"evidence": []})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        mubit.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    assert mubit.retrieve(_case()) == []
