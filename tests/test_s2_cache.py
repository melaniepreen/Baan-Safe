"""S2_IMPL=cache: exact-key replay, miss handling, record path, route wiring."""

from __future__ import annotations

import json
import os

import pytest

from contracts.models import System
from fixtures.load import load_case
from system2 import cache, orchestrator
from system2.orchestrator import orchestrate
from trace import read_traces

GOOD = {
    "choices": [
        {
            "message": {
                "content": (
                    '{"priority": "P2", "route": "rescue_coordination", '
                    '"needs": ["rescue"], "requires_human": true, '
                    '"missing_evidence": [], "next_question": null, '
                    '"confidence": 0.8, "rationale": "Cached.", "plan": ["Send a boat."]}'
                )
            }
        }
    ]
}


@pytest.fixture
def cache_env(monkeypatch, tmp_path):
    monkeypatch.setenv("S2_IMPL", "cache")
    monkeypatch.setenv("S2_CACHE_PATH", str(tmp_path / "demo.jsonl"))
    monkeypatch.setenv("S2_CACHE_RECORD_PATH", str(tmp_path / "record.jsonl"))
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    monkeypatch.delenv("MUBIT_BASE_URL", raising=False)
    cache._loaded.clear()
    return tmp_path


def _seed(path, model, messages, reply=GOOD):
    path.write_text(json.dumps({"key": cache.cache_key(model, messages), "reply": reply}) + "\n")


def test_key_matches_rl_loop_key():
    from eval.rl.run import _cache_key

    messages = [{"role": "system", "content": "a"}, {"role": "user", "content": "b"}]
    assert _cache_key("m", messages) == cache.cache_key("m", messages)
    assert cache.cache_key("m", messages) != cache.cache_key("m2", messages)


def test_case_key_ignores_case_id_memory_resources_only():
    base = {"case_id": "case-1", "transcript": [{"speaker": "caller", "text": "help"}],
            "fields": {"needs": ["water"]}, "memory": ["lesson"], "resources": {"boats": 1}}
    other = {**base, "case_id": "case-2", "memory": [], "resources": {"boats": 0}}
    changed = {**base, "fields": {"needs": ["rescue"]}}
    msgs = lambda p: [{"role": "system", "content": "S"}, {"role": "user", "content": json.dumps(p)}]
    assert cache.cache_key("m", msgs(base)) != cache.cache_key("m", msgs(other))
    assert cache.cache_key("m", msgs(base), "case") == cache.cache_key("m", msgs(other), "case")
    assert cache.cache_key("m", msgs(base), "case") != cache.cache_key("m", msgs(changed), "case")
    with pytest.raises(ValueError):
        cache.cache_key("m", msgs(base), "fuzzy")


def test_case_key_mode_hits_across_case_ids(cache_env, monkeypatch):
    monkeypatch.setenv("S2_CACHE_KEY", "case")
    case = load_case("F10")
    model = orchestrator.require_decision("system2.orchestrator_model")
    key = cache.cache_key(model, orchestrator._messages(case, None, None), "case")
    (cache_env / "demo.jsonl").write_text(json.dumps({"key": key, "reply": GOOD}) + "\n")

    def no_socket(*_a, **_k):  # pragma: no cover - must not be reached
        raise AssertionError("case-key hit must not call Mubit")

    monkeypatch.setattr("llm.client.complete", no_socket)
    # Same transcript under a fresh id with a different memory context.
    renamed = case.model_copy(update={"case_id": "case-fresh", "memory_context": []})
    assert orchestrate(renamed).outcome == "reasoned_recommendation"
    hop = [e for e in read_traces("case-fresh") if e.stage == "mubit_chat"][0]
    assert "host=s2_cache/case" in (hop.notes or "")


def test_hit_replays_without_socket_and_traces_cache_hit(cache_env, monkeypatch):
    case = load_case("F10")
    model = orchestrator.require_decision("system2.orchestrator_model")
    messages = orchestrator._messages(case, None, None)
    _seed(cache_env / "demo.jsonl", model, messages)

    def no_socket(*_a, **_k):  # pragma: no cover - must not be reached
        raise AssertionError("cache hit must not call Mubit")

    monkeypatch.setattr("llm.client.complete", no_socket)
    outcome = orchestrate(case)
    assert outcome.system is System.system_2
    assert outcome.outcome == "reasoned_recommendation"
    hops = [e for e in read_traces("F10") if e.stage == "mubit_chat"]
    assert len(hops) == 1
    assert "status=cache_hit" in (hops[0].notes or "")
    assert "host=s2_cache" in (hops[0].notes or "")
    assert not (cache_env / "record.jsonl").exists()


def test_hit_replays_recorded_mubit_request_id(cache_env, monkeypatch):
    case = load_case("F10")
    model = orchestrator.require_decision("system2.orchestrator_model")
    messages = orchestrator._messages(case, None, None)
    recorded = {**GOOD, "mubit_request_id": "mreq_feedfacefeedfacefeedfacefeedface"}
    _seed(cache_env / "demo.jsonl", model, messages, reply=recorded)
    monkeypatch.setattr("llm.client.complete", lambda *_a, **_k: pytest.fail("no socket"))
    orchestrate(case)
    hop = [e for e in read_traces("F10") if e.stage == "mubit_chat"][0]
    assert "status=cache_hit" in (hop.notes or "")
    # The id of the call that was recorded, flagged so nobody reads it as new.
    assert "request_id=mreq_feedfacefeedfacefeedfacefeedface (recorded)" in (hop.notes or "")


def test_miss_without_credentials_falls_back_safely(cache_env):
    outcome = orchestrate(load_case("F10"))
    assert outcome.missing_evidence == ["system2_unavailable"]
    assert outcome.requires_human is True
    assert not [e for e in read_traces("F10") if e.stage == "mubit_chat"]


def test_miss_with_credentials_calls_mubit_once_and_records(cache_env, monkeypatch):
    monkeypatch.setenv("MUBIT_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    calls = {"n": 0}

    def fake_complete(messages, model=None, **kwargs):
        calls["n"] += 1
        return GOOD

    monkeypatch.setattr("llm.client.complete", fake_complete)
    case = load_case("F10")
    assert orchestrate(case).outcome == "reasoned_recommendation"
    assert calls["n"] == 1
    rows = [json.loads(l) for l in (cache_env / "record.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["reply"] == GOOD
    assert "test-key-not-real" not in (cache_env / "record.jsonl").read_text()
    # Second identical turn is a hit: no further call.
    cache._loaded.clear()
    assert orchestrate(case).outcome == "reasoned_recommendation"
    assert calls["n"] == 1


def test_use_completer_override_beats_cache_mode(cache_env):
    with orchestrator.use_completer(lambda *a, **k: GOOD):
        assert orchestrate(load_case("F10")).outcome == "reasoned_recommendation"


def test_route_treats_cache_as_live_s2(cache_env, monkeypatch):
    from gateway.route import _S2_LIVE, _impl

    assert _impl("S2_IMPL") == "cache"
    assert "cache" in _S2_LIVE and "real" in _S2_LIVE


def test_committed_demo_cache_parses():
    assert cache.DEFAULT_PATH.is_file()
    rows = cache._read(cache.DEFAULT_PATH)
    assert rows, "fixtures/s2_cache/demo.jsonl must hold at least one reply"
    text = cache.DEFAULT_PATH.read_text(encoding="utf-8")
    assert "mbt_" not in text and "Bearer" not in text


def test_gateway_app_keeps_cache_mode(monkeypatch, tmp_path):
    from infra.modal import gateway_app as gateway

    monkeypatch.setenv("S1_IMPL", "real")
    monkeypatch.setenv("S2_IMPL", "cache")
    monkeypatch.setenv("MEMORY_IMPL", "local")
    monkeypatch.setenv("MEMORY_LOCAL_PATH", str(tmp_path / "memory.jsonl"))
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    monkeypatch.delenv("MUBIT_BASE_URL", raising=False)
    gateway.apply_runtime_impl()
    assert os.environ["S2_IMPL"] == "cache"
    assert gateway.hosting()["backends"] == "cache"
    assert "S2_CACHE_RECORD_PATH" in gateway.STUB_ENV
    assert gateway.STUB_ENV["S2_CACHE_KEY"] == "case"
    monkeypatch.setenv("MUBIT_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    gateway.apply_runtime_impl()
    assert os.environ["S2_IMPL"] == "cache"
    assert "recorded" in gateway.hosting()["note"]
