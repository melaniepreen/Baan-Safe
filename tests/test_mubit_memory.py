"""Mubit control-plane memory client (mocked HTTP)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from contracts.models import CaseState, Correction, ExtractedFields, TranscriptTurn
from memory import mubit


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
