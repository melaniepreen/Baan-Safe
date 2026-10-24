"""Mubit chat tracing: mocked httpx, no live network."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app
from contracts.models import TraceEvent
from llm.client import complete, emit_mubit_chat_trace
from trace import read_traces


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": '{"priority":"P2"}'}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        },
        request=request,
    )


def test_complete_emits_mubit_chat_on_success(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai/compat/openrouter/v1")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")

    def fake_post(url, **kwargs):
        assert "openrouter.ai" not in url
        assert "api.mubit.ai" in url
        headers = kwargs.get("headers") or {}
        assert headers.get("Authorization", "").startswith("Bearer ")
        return _ok_response(httpx.Request("POST", url))

    monkeypatch.setattr("llm.client.httpx.post", fake_post)
    body = complete(
        [{"role": "user", "content": "synthetic"}],
        model="nvidia/nemotron-3-nano-30b-a3b",
        case_id="F10",
    )
    assert body["usage"]["prompt_tokens"] == 11
    events = read_traces("F10")
    assert len(events) == 1
    event = events[0]
    assert event.stage == "mubit_chat"
    assert event.model == "nvidia/nemotron-3-nano-30b-a3b"
    assert event.tokens_in == 11
    assert event.tokens_out == 7
    assert event.notes is not None
    assert "status=ok" in event.notes
    assert "host=api.mubit.ai" in event.notes
    assert "mbt_should_not_appear" not in event.notes
    assert "Bearer" not in event.notes


def test_complete_emits_http_429_status(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")

    def limited(url, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(429, request=request, text="rate")

    monkeypatch.setattr("llm.client.httpx.post", limited)
    with pytest.raises(httpx.HTTPStatusError):
        complete(
            [{"role": "user", "content": "synthetic"}],
            model="nvidia/nemotron-3-nano-30b-a3b",
            case_id="F10",
        )
    events = read_traces("F10")
    assert len(events) == 1
    assert events[0].stage == "mubit_chat"
    assert "status=http_429" in (events[0].notes or "")
    dumped = events[0].model_dump_json()
    assert "mbt_should_not_appear" not in dumped


def test_config_refusal_does_not_emit_mubit_chat(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    with pytest.raises(RuntimeError, match="MUBIT_API_KEY"):
        complete([{"role": "user", "content": "synthetic"}], model="x")
    assert read_traces() == []


def test_emit_helper_never_embeds_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    emit_mubit_chat_trace(
        case_id="F01",
        model="nvidia/nemotron-3-nano-30b-a3b",
        latency_ms=12,
        status="ok",
        host="api.mubit.ai",
    )
    line = (tmp_path / "traces.jsonl").read_text(encoding="utf-8").strip()
    row = json.loads(line)
    assert row["stage"] == "mubit_chat"
    assert "mbt_" not in line
    assert "Bearer" not in line
    TraceEvent.model_validate(row)


def test_metrics_surfaces_mubit_chat(client, monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    emit_mubit_chat_trace(
        case_id="F10",
        model="nvidia/nemotron-3-nano-30b-a3b",
        latency_ms=40,
        status="ok",
        host="api.mubit.ai",
    )
    emit_mubit_chat_trace(
        case_id="F10",
        model="nvidia/nemotron-3-nano-30b-a3b",
        latency_ms=10,
        status="http_429",
        host="api.mubit.ai",
    )
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    mubit = body["mubit_chat"]
    assert mubit["call_count"] == 2
    assert mubit["ok_count"] == 1
    assert mubit["error_count"] == 1
    assert mubit["avg_latency_ms"] == 25.0
    assert mubit["models"]["nvidia/nemotron-3-nano-30b-a3b"] == 2
    assert mubit["via"] == "api.mubit.ai"
    assert body["avg_latency_ms"]["mubit_chat"] == 25.0


def test_gateway_emits_enrich_and_memory(client):
    client.post("/cases", json={"fixture_id": "F03"})
    client.post(
        "/cases/F03/turns",
        json={"t_ms": 80000, "speaker": "caller", "text": "Still two of us, still dry."},
    )
    response = client.get("/cases/F03/trace")
    assert response.status_code == 200
    stages = {event["stage"] for event in response.json()}
    assert {"enrich", "memory", "gateway", "system_1", "router"} <= stages
