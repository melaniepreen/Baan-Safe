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

    def boom(**_kwargs):
        raise RuntimeError("control plane down")

    monkeypatch.setattr(mubit, "retrieve", boom)
    from memory.adapter import retrieve

    assert retrieve(_case()) == []


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
