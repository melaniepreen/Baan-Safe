"""RL loop with a fake System 2: graduation, recommendation, demotion.

Live/replay Mubit hops are covered with mocked llm.complete (no network).
"""

from __future__ import annotations

import json

import httpx
import pytest

from contracts.models import System
from eval.rl.learner import Learner
from eval.rl.run import _cache_key, _completer_for, run
from eval.rl.themes import THEMES, variant_case
from gateway.overlay import coarse_signature, narrow_signature
from system1.extract import extract
from trace import read_traces


def _narrow(theme_id, index=0):
    theme = next(item for item in THEMES if item.theme_id == theme_id)
    case = variant_case(theme, theme.variants[index])
    fields, flags = extract(case.transcript)
    case.fields = fields
    case.policy_flags = ["keyword_extraction", *flags]
    return narrow_signature(case)


def _coarse(theme_id):
    theme = next(item for item in THEMES if item.theme_id == theme_id)
    case = variant_case(theme, theme.variants[0])
    fields, flags = extract(case.transcript)
    case.fields = fields
    case.policy_flags = ["keyword_extraction", *flags]
    return coarse_signature(case)


def test_fake_loop_learns(tmp_path):
    payload = run(s2="fake", epochs=2, out_dir=tmp_path / "rl")
    overlay = payload["final_overlay"]

    for theme_id in ("road-info", "cold-hall"):
        assert _narrow(theme_id) in overlay["graduated"]
    for theme_id in ("quiet-grandmother", "upstairs-water"):
        narrow = _narrow(theme_id)
        assert narrow in overlay["recommendations"]
        assert narrow not in overlay["graduated"]
    for theme_id in ("aid-list", "fine-but-door"):
        assert _narrow(theme_id) not in overlay["graduated"]
        assert _narrow(theme_id) not in overlay["recommendations"]
    assert _coarse("weak-grandfather-water") in overlay["demoted"]

    kinds = [event["kind"] for event in payload["events"]]
    assert sorted(kinds) == ["demote", "graduate", "graduate", "recommend", "recommend"]
    assert len(kinds) == len(set(
        (event["kind"], event["signature"]) for event in payload["events"]
    ))

    weak = [
        row
        for row in payload["episodes"]
        if row["id"].startswith("RL-WEAK") and row["epoch"] == 2
    ]
    assert weak and all(row["systems"] == ["system_2"] for row in weak)
    assert all(row["correct"] for row in weak)

    graduated_road = [
        row
        for row in payload["episodes"]
        if row["id"] == "RL-ROAD-3" and row["epoch"] >= 1
    ]
    assert any(row["systems"] == ["system_1"] and row["correct"] for row in graduated_road)

    assert payload["schema"] == "baansafe.rl_run.v1"
    for key in ("epochs", "episodes", "events", "final_overlay", "training", "notes", "model", "mubit"):
        assert key in payload
    assert payload["mubit"]["via"] == "fake"
    assert "Mubit" in payload["notes"][0]
    on_disk = json.loads((tmp_path / "rl" / "run.json").read_text())
    assert on_disk["schema"] == "baansafe.rl_run.v1"
    assert on_disk["model"]
    assert on_disk["mubit"]["via"] == "fake"


def test_live_completer_traces_mubit_and_cache(monkeypatch, tmp_path):
    """Live miss → Mubit complete + mubit_chat ok; hit → cache_hit, no second POST."""
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai/compat/openrouter/v1")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    out = tmp_path / "rl"
    out.mkdir()
    posts = {"n": 0}

    def fake_post(url, **kwargs):
        posts["n"] += 1
        assert "openrouter.ai" not in url
        assert "api.mubit.ai" in url
        headers = kwargs.get("headers") or {}
        assert headers.get("Authorization", "").startswith("Bearer ")
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"priority":"P2","route":"information_only","needs":[],'
                                '"requires_human":false,"missing_evidence":[],'
                                '"next_question":null,"confidence":0.9,'
                                '"rationale":"mock","plan":[]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
            request=request,
        )

    monkeypatch.setattr("llm.client.httpx.post", fake_post)
    completer = _completer_for("live", out)
    messages = [
        {"role": "system", "content": "x"},
        {"role": "user", "content": json.dumps({"case_id": "RL-TRACE-1", "transcript": []})},
    ]
    model = "nvidia/nemotron-3-nano-30b-a3b"
    reply = completer(messages, model=model, case_id="RL-TRACE-1")
    assert reply["choices"]
    assert posts["n"] == 1
    events = read_traces("RL-TRACE-1")
    assert len(events) == 1
    assert events[0].stage == "mubit_chat"
    assert "status=ok" in (events[0].notes or "")
    assert "host=api.mubit.ai" in (events[0].notes or "")
    dumped = events[0].model_dump_json()
    assert "mbt_should_not_appear" not in dumped
    assert "Bearer" not in dumped

    reply2 = completer(messages, model=model, case_id="RL-TRACE-1")
    assert reply2 == reply
    assert posts["n"] == 1
    events = read_traces("RL-TRACE-1")
    assert len(events) == 2
    assert "status=cache_hit" in (events[1].notes or "")
    assert "host=rl_s2_cache" in (events[1].notes or "")
    assert events[1].latency_ms == 0


def test_replay_miss_is_fallback_not_a_host(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    out = tmp_path / "rl"
    out.mkdir()
    completer = _completer_for("replay", out)
    messages = [
        {"role": "system", "content": "x"},
        {"role": "user", "content": json.dumps({"case_id": "RL-MISS", "transcript": []})},
    ]
    with pytest.raises(ValueError, match="s2 cache miss"):
        completer(messages, model="nvidia/nemotron-3-nano-30b-a3b", case_id="RL-MISS")
    assert read_traces("RL-MISS") == []


def test_replay_hit_traces_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    out = tmp_path / "rl"
    out.mkdir()
    model = "nvidia/nemotron-3-nano-30b-a3b"
    messages = [
        {"role": "system", "content": "x"},
        {"role": "user", "content": json.dumps({"case_id": "RL-HIT", "transcript": []})},
    ]
    key = _cache_key(model, messages)
    reply = {"choices": [{"message": {"content": '{"priority":"P3"}'}}]}
    (out / "s2_cache.jsonl").write_text(
        json.dumps({"key": key, "reply": reply}) + "\n", encoding="utf-8"
    )
    completer = _completer_for("replay", out)
    assert completer(messages, model=model, case_id="RL-HIT") == reply
    events = read_traces("RL-HIT")
    assert len(events) == 1
    assert events[0].stage == "mubit_chat"
    assert "status=cache_hit" in (events[0].notes or "")
    assert events[0].latency_ms == 0


def test_bandit_allowed_arms():
    learner = Learner()
    door = variant_case(
        next(t for t in THEMES if t.theme_id == "fine-but-door"),
        THEMES[7].variants[0],
    )
    road = variant_case(
        next(t for t in THEMES if t.theme_id == "road-info"),
        THEMES[0].variants[0],
    )
    learner._bandit(
        door, "coarse-a", {System.system_2},
        hard_triggers=["need:rescue"], reward=1.0, epoch=1, sequence=0,
    )
    assert learner.bandit_log[-1]["pick"] == "system_2"
    learner._bandit(
        road, "coarse-b", {System.system_1, System.system_2},
        hard_triggers=[], reward=-1.0, epoch=1, sequence=1,
    )
    entry = learner.bandit_log[-1]
    assert entry["pick"] in {"system_1", "system_2"}
    assert ("coarse-b", "system_1") in learner.bandit
    assert ("coarse-b", "system_2") in learner.bandit
