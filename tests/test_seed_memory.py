"""scripts/seed_memory.py: corpus-derived lessons, dry-run, idempotent ingest (mocked HTTP)."""

from __future__ import annotations

import json

import httpx
import pytest

from memory import mubit
from policies.service import get_service
from scripts import seed_memory


def _mock_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        mubit.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )


def _mubit_env(monkeypatch):
    monkeypatch.setenv("MEMORY_IMPL", "mubit")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai/compat/openrouter/v1")
    monkeypatch.setenv("MUBIT_PROJECT_ID", "ws-test")


def test_lessons_come_from_the_corpus():
    items = seed_memory.build_lessons()
    assert 6 <= len(items) <= 10
    rules = get_service().known_ids()
    seen_tags: set[str] = set()
    for item in items:
        assert item["lane"] == seed_memory.LANE
        assert item["type"] in {"rule", "lesson"}
        content = item["content"]
        assert len(content) <= seed_memory.MAX_CHARS
        tags = seed_memory.tags_in(content)
        assert len(tags) == 1
        tag = tags.pop()
        assert content.startswith(tag)
        assert tag not in seen_tags
        seen_tags.add(tag)
        rule_id = item["metadata"]["policy_id"]
        assert tag == seed_memory.tag_for(rule_id)
        rule = rules[rule_id]
        corpus_text = rule.languages["en"].text
        body = content[len(tag) :].strip()
        if item["type"] == "rule":
            # Rules are corpus sentences only.
            for sentence in seed_memory._sentences(body):
                assert sentence in corpus_text, (rule_id, sentence)
        else:
            # Lessons start with corpus sentences and end with one BaanSafe note.
            assert "BaanSafe:" in body
            corpus_part = body.split("BaanSafe:")[0].strip()
            assert corpus_part
            for sentence in seed_memory._sentences(corpus_part):
                assert sentence in corpus_text, (rule_id, sentence)
    assert "[policy:IFRC-PGI-UASC]" in seen_tags  # the unaccompanied lesson
    assert "[policy:MOF-2569-NO-DUPLICATE]" in seen_tags  # duplicate-call merge


def test_unknown_rule_is_an_error(monkeypatch):
    bad = seed_memory.LessonSpec("MOF-2569-NO-DUPLICATE", "rule", ("not in the text at all",))
    monkeypatch.setattr(seed_memory, "SPECS", (bad,))
    with pytest.raises(ValueError, match="do not invent"):
        seed_memory.build_lessons()


def test_dry_run_posts_nothing(monkeypatch, capsys):
    _mubit_env(monkeypatch)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    _mock_transport(monkeypatch, handler)
    assert seed_memory.run(["--dry-run", "--case-fact", "case-dry"]) == 0
    assert calls == []
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "[policy:" in out
    assert "Case case-dry" in out
    assert "mbt_should_not_appear" not in out


def test_refuses_without_mubit_mode_or_key(monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_IMPL", "mock")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    assert seed_memory.run([]) == 2
    err = capsys.readouterr().err
    assert "MEMORY_IMPL" in err
    assert "mbt_should_not_appear" not in err

    monkeypatch.setenv("MEMORY_IMPL", "mubit")
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    assert seed_memory.run([]) == 2
    assert "MUBIT_API_KEY" in capsys.readouterr().err


def test_idempotent_skips_present_tags(monkeypatch, capsys):
    _mubit_env(monkeypatch)
    expected = seed_memory.build_lessons()
    present_tag = seed_memory.tags_in(expected[0]["content"]).pop()
    seen: dict[str, list[dict]] = {"query": [], "ingest": []}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        assert "Bearer mbt_should_not_appear" in request.headers.get("Authorization", "")
        assert body["workspace_id"] == "ws-test"
        if request.url.path == "/v2/control/query":
            seen["query"].append(body)
            # Same body shape as memory.mubit.retrieve.
            assert body["mode"] == "agent_routed"
            assert set(body["entry_types"]) == {"lesson", "rule"}
            assert present_tag in body["query"]
            return httpx.Response(
                200,
                json={
                    "evidence": [
                        {
                            "id": "ev-1",
                            "content": expected[0]["content"],
                            "origin_entry_type": "rule",
                            "score": 0.9,
                        }
                    ]
                },
            )
        assert request.url.path == "/v2/control/ingest"
        seen["ingest"].append(body)
        return httpx.Response(200, json={"job_id": "job-1", "accepted": len(body["items"])})

    _mock_transport(monkeypatch, handler)
    assert seed_memory.run(["--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(seen["query"]) == 1
    assert len(seen["ingest"]) == 1
    sent = seen["ingest"][0]["items"]
    assert len(sent) == len(expected) - 1
    assert all(present_tag not in item["content"] for item in sent)
    assert all(item["lane"] == seed_memory.LANE for item in sent)
    assert report["already_present"] == [present_tag]
    assert report["skipped"] == 1
    assert report["ingested"] == len(expected) - 1
    assert report["ingest_response"]["job_id"] == "job-1"
    assert "mbt_should_not_appear" not in json.dumps(report)


def test_case_fact_is_always_sent(monkeypatch, capsys):
    _mubit_env(monkeypatch)
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        if request.url.path == "/v2/control/query":
            return httpx.Response(200, json={"evidence": []})
        sent.extend(body["items"])
        return httpx.Response(200, json={})

    _mock_transport(monkeypatch, handler)
    assert seed_memory.run(["--case-fact", "F06"]) == 0
    facts = [item for item in sent if item["type"] == "fact"]
    assert len(facts) == 1
    assert facts[0]["lane"] == seed_memory.CASE_LANE
    assert facts[0]["content"].startswith("Case F06: needs=")


def test_query_failure_reports_without_key(monkeypatch, capsys):
    _mubit_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"error": {"code": "unknown_route", "message": "Unknown route."}},
        )

    _mock_transport(monkeypatch, handler)
    assert seed_memory.run([]) == 1
    captured = capsys.readouterr()
    assert "HTTP 404 unknown_route" in captured.out
    assert "MUBIT_CONTROL_URL" in captured.err
    assert "mbt_should_not_appear" not in captured.out + captured.err
