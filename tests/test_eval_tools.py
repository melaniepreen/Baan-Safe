"""rl-compare, GET /training compare + /training/episodes, eval-gate, mubit-requests.

Temp run.json files, a temp registry, and a temp trace file. No network, no
model, and no secret: a crafted note with a key-looking token must never be
printed by `mubit_requests`.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.routes import training as surface
from contracts.models import Outcome, TraceEvent
from eval.rl import compare as rl_compare

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_A = ROOT / "eval" / "snapshots" / "rl" / rl_compare.DEFAULT_A
SNAPSHOT_B = ROOT / "eval" / "snapshots" / "rl" / rl_compare.DEFAULT_B


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _episode(epoch, seq, case_id, *, critical=False, under=False, missed=False, correct=True, systems=("system_1",)):
    return {
        "epoch": epoch,
        "seq": seq,
        "id": case_id,
        "kind": "fixture",
        "systems": list(systems),
        "cascaded": len(systems) > 1,
        "priority": "P2" if under else "P1",
        "truth_priority": "P1",
        "route": "rescue_coordination",
        "reward": -1.8 if critical else (1.0 if correct else -0.2),
        "correct": correct,
        "under_triage": under or critical,
        "critical_under": critical,
        "missed_human": missed,
        "s2_fell_back": False,
    }


def _run(epoch_rows, episodes, *, overlay=None, mubit=None):
    return {
        "schema": "baansafe.rl_run.v1",
        "s2": "fake",
        "model": "nvidia/nemotron-3-nano-30b-a3b",
        "seed": 1,
        "epochs": epoch_rows,
        "episodes": episodes,
        "events": [],
        "final_overlay": overlay
        or {"schema": "baansafe.rl_overlay.v1", "graduation_threshold": 2, "graduated": {}, "recommendations": {}, "demoted": {}},
        "mubit": mubit or {"live_ok": 0, "cache_hits": 0, "errors": 0},
        "training": {"status": "none", "counts": {}},
        "notes": [],
    }


def _epoch(n, **values):
    row = {
        "epoch": n,
        "episodes": 4,
        "mean_reward": 0.0,
        "correct": 2,
        "under_triage": 1,
        "critical_under": 1,
        "missed_human": 0,
        "share_s1_only": 0.5,
        "share_cascade": 0.25,
        "share_s2_only": 0.25,
        "s2_fallbacks": 0,
    }
    row.update(values)
    return row


@pytest.fixture
def two_runs(tmp_path):
    run_a = _run(
        [_epoch(1, correct=1, critical_under=2, mean_reward=-0.5), _epoch(2, correct=2, critical_under=2, missed_human=1, mean_reward=-0.3)],
        [
            _episode(2, 0, "F01", critical=True, correct=False),
            _episode(2, 1, "F02", critical=True, correct=False, missed=True),
            _episode(2, 2, "F03"),
            _episode(2, 3, "G01"),
            _episode(1, 0, "F01", critical=True, correct=False),
        ],
        overlay={"graduation_threshold": 2, "graduated": {"s": {}}, "recommendations": {}, "demoted": {"d": {}}},
        mubit={"live_ok": 10, "cache_hits": 5, "errors": 1},
    )
    run_b = _run(
        [_epoch(1, correct=3, critical_under=1, mean_reward=0.1), _epoch(2, correct=3, critical_under=1, mean_reward=0.25)],
        [
            _episode(2, 0, "F01"),
            _episode(2, 1, "F02", under=True, correct=False),
            _episode(2, 2, "F03", critical=True, correct=False, systems=("system_2", "system_1")),
            _episode(2, 3, "G01"),
        ],
        overlay={"graduation_threshold": 2, "graduated": {}, "recommendations": {"r": {}, "r2": {}}, "demoted": {"d": {}}},
        mubit={"live_ok": 20, "cache_hits": 2, "errors": 0},
    )
    dir_a = tmp_path / "snap-a"
    dir_b = tmp_path / "snap-b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "run.json").write_text(json.dumps(run_a), encoding="utf-8")
    (dir_b / "run.json").write_text(json.dumps(run_b), encoding="utf-8")
    return dir_a, dir_b


# --- eval/rl/compare.py -----------------------------------------------------


def test_compare_resolves_names_dirs_and_files(tmp_path, two_runs):
    dir_a, _ = two_runs
    assert rl_compare.resolve(rl_compare.DEFAULT_A) == SNAPSHOT_A / "run.json"
    assert rl_compare.resolve(dir_a) == dir_a / "run.json"
    assert rl_compare.resolve(dir_a / "run.json") == dir_a / "run.json"
    assert rl_compare.resolve("no-such-snapshot") == SNAPSHOT_A.parent / "no-such-snapshot" / "run.json"
    assert rl_compare.label_for(dir_a / "run.json") == "snap-a"
    with pytest.raises(FileNotFoundError):
        rl_compare.load_run(tmp_path / "missing")


def test_compare_metrics_deltas_and_flips(two_runs):
    dir_a, dir_b = two_runs
    report = rl_compare.compare_refs(dir_a, dir_b)
    assert report["schema"] == rl_compare.SCHEMA
    assert report["a"]["label"] == "snap-a" and report["b"]["label"] == "snap-b"
    assert [row["epoch"] for row in report["epochs"]] == [1, 2]
    assert report["epochs"][0]["metrics"]["correct"] == {"a": 1, "b": 3, "delta": 2}
    last = report["last_epoch"]
    assert (last["epoch_a"], last["epoch_b"]) == (2, 2)
    assert last["metrics"]["critical_under"] == {"a": 2, "b": 1, "delta": -1}
    assert last["metrics"]["missed_human"] == {"a": 1, "b": 0, "delta": -1}
    assert last["metrics"]["mean_reward"]["delta"] == pytest.approx(0.55)
    assert report["mubit"]["live_ok"] == {"a": 10, "b": 20, "delta": 10}
    assert report["mubit"]["errors"]["delta"] == -1
    assert report["overlay"]["graduated"] == {"a": 1, "b": 0, "delta": -1}
    assert report["overlay"]["recommendations"] == {"a": 0, "b": 2, "delta": 2}
    assert report["overlay"]["demoted"]["delta"] == 0
    flips = report["flips"]["critical_under"]
    # Uses the last epoch only: F01 was critical in epoch 1 and 2 of A, fixed in B;
    # F03 is new in B; F02 dropped to plain under-triage so it is fixed too.
    assert flips == {"fixed_in_b": ["F01", "F02"], "new_in_b": ["F03"], "both": []}
    assert report["flips"]["missed_human"]["fixed_in_b"] == ["F02"]
    groups = {(row["group"], row["metric"]) for row in report["summary"]}
    assert ("last_epoch", "critical_under") in groups and ("mubit", "live_ok") in groups and ("overlay", "demoted") in groups


def test_compare_markdown_and_cli_write_files(tmp_path, two_runs, capsys):
    dir_a, dir_b = two_runs
    out_md = tmp_path / "out" / "rl_compare.md"
    out_json = tmp_path / "out" / "rl_compare.json"
    code = rl_compare.main(["--a", str(dir_a), "--b", str(dir_b), "--out", str(out_md), "--json", str(out_json)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "rl-compare snap-a vs snap-b" in printed
    assert "critical_under 2→1" in printed
    text = out_md.read_text(encoding="utf-8")
    assert "| critical_under | 2 | 1 | -1 |" in text
    assert "`critical_under` fixed in B: F01, F02" in text
    assert "`critical_under` new in B: F03" in text
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["last_epoch"]["metrics"]["correct"]["b"] == 3
    assert rl_compare.main(["--a", str(tmp_path / "nope"), "--b", str(dir_b), "--out", str(out_md), "--json", str(out_json)]) == 2


def test_compare_default_snapshots_headline():
    """The two committed 25 Oct runs: memory on removes most critical under-triage."""

    report = rl_compare.compare_refs(rl_compare.DEFAULT_A, rl_compare.DEFAULT_B)
    last = report["last_epoch"]["metrics"]
    assert last["critical_under"]["a"] == 9 and last["critical_under"]["b"] == 2
    assert last["mean_reward"]["delta"] > 0
    assert report["flips"]["critical_under"]["new_in_b"] == []


# --- GET /training compare section and /training/episodes ------------------


@pytest.fixture
def client():
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_training_compare_section_uses_env_or_defaults(client, two_runs, monkeypatch, tmp_path):
    dir_a, dir_b = two_runs
    monkeypatch.setenv("RL_COMPARE_A", str(dir_a))
    monkeypatch.setenv("RL_COMPARE_B", str(dir_b))
    body = client.get("/training").json()
    compare = body["compare"]
    assert compare["available"] is True
    assert compare["a"]["label"] == "snap-a"
    assert compare["last_epoch"]["metrics"]["critical_under"]["delta"] == -1
    assert compare["missing"] == []
    # Paths outside the repo are reduced to file names.
    assert str(tmp_path) not in json.dumps(body)

    monkeypatch.setenv("RL_COMPARE_B", str(tmp_path / "absent"))
    body = client.get("/training").json()
    assert body["compare"]["available"] is False
    assert "run.json" in body["compare"]["missing"]
    assert "run.json" in body["missing"]

    monkeypatch.delenv("RL_COMPARE_A")
    monkeypatch.delenv("RL_COMPARE_B")
    body = client.get("/training").json()
    assert body["compare"]["available"] is True
    assert body["compare"]["a"]["label"] == rl_compare.DEFAULT_A
    assert body["compare"]["b"]["run_path"] == f"eval/snapshots/rl/{rl_compare.DEFAULT_B}/run.json"


def test_training_episodes_filters_epoch_limit_and_titles(client, two_runs, monkeypatch):
    dir_a, _ = two_runs
    monkeypatch.setenv("RL_RUN_PATH", str(dir_a / "run.json"))
    body = client.get("/training/episodes").json()
    assert body["filter"] == "critical_under"
    assert body["epoch"] is None
    assert body["count"] == 3 and body["matched"] == 3 and body["total"] == 5
    assert [(e["epoch"], e["id"]) for e in body["episodes"]] == [(1, "F01"), (2, "F01"), (2, "F02")]
    assert body["episodes"][0]["fixture_title"] == "Drinking water, dry ground"
    assert body["run_path"] == "run.json"

    body = client.get("/training/episodes?filter=missed_human&epoch=2").json()
    assert [e["id"] for e in body["episodes"]] == ["F02"]
    body = client.get("/training/episodes?filter=all&epoch=2&limit=2").json()
    assert body["count"] == 2 and body["matched"] == 4
    body = client.get("/training/episodes?filter=incorrect").json()
    assert {e["id"] for e in body["episodes"]} == {"F01", "F02"}
    assert client.get("/training/episodes?filter=bogus").status_code == 400

    monkeypatch.setenv("RL_RUN_PATH", str(dir_a / "nope.json"))
    body = client.get("/training/episodes?filter=all").json()
    assert body["episodes"] == [] and body["missing"] == ["nope.json"]


def test_fixture_title_covers_fixtures_synthetic_themes_sim_and_unknown():
    assert surface.fixture_title("F01") == "Drinking water, dry ground"
    assert surface.fixture_title("syn-niems-red-critical-01-en") == "niems_red_critical en 1"
    assert surface.fixture_title("RL-ROAD-1").startswith("road-info")
    assert surface.fixture_title("sim-omit-phrae").startswith("sim caller: omits_location")
    assert surface.fixture_title("no-such-case") is None


def test_training_page_renders_compare_and_episodes(client):
    source = client.get("/ui/training.js").text
    assert "Memory off vs on" in source
    assert "/training/episodes" in source
    for key in ("fixture_title", "truth_priority", "critical_under", "fixed_in_b"):
        assert key in source
    for banned in ("MUBIT_", "OPENROUTER", "Bearer"):
        assert banned not in source
    html = client.get("/ui/training.html").text
    assert 'id="episode-filter"' in html and 'id="compare-card"' in html


# --- scripts/eval_gate.py ---------------------------------------------------


def _registry(tmp_path, *, heldout, task="s1_triage", version_id="ft-20261025T045101Z-e4ce5eb6"):
    registry_dir = tmp_path / "vol"
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "versions": [
            {
                "version_id": version_id,
                "model_name": "sentence-transformers/x",
                "role": "system_1",
                "training_job_id": f"job-{version_id}",
                "notes": f"SetFit model saved. Task {task}.",
            }
        ],
        "jobs": [{"job_id": f"job-{version_id}", "status": "completed", "gpu": "T4"}],
    }
    (registry_dir / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    metrics = {"trainer": "setfit", "steps": 10, "rows": 100, "loss_curve": []}
    if heldout is not None:
        metrics["heldout"] = {"rows": 72, "accuracy": heldout, "per_label": {}}
    metrics_dir = registry_dir / "versions" / version_id
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    return registry_dir / "registry.json"


def test_eval_gate_s1_pass_fail_skip(tmp_path, monkeypatch, capsys):
    gate = _script("eval_gate")
    monkeypatch.setenv("RL_RUN_PATH", str(tmp_path / "no-run.json"))

    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(_registry(tmp_path / "pass", heldout=0.875)))
    assert gate.main([]) == 0
    out = capsys.readouterr().out
    assert "PASS s1_heldout: ft-20261025T045101Z-e4ce5eb6 heldout accuracy 0.875 on 72 rows, threshold 0.85" in out
    assert "SKIP rl_critical_under: no current run" in out

    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(_registry(tmp_path / "fail", heldout=0.5)))
    assert gate.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL s1_heldout" in out and "0.500" in out
    assert gate.main(["--s1-acc", "0.4"]) == 0
    monkeypatch.setenv("EVAL_GATE_S1_ACC", "0.45")
    assert gate.main([]) == 0

    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(_registry(tmp_path / "noheld", heldout=None)))
    assert gate.main([]) == 0
    assert "SKIP s1_heldout" in capsys.readouterr().out and True
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(_registry(tmp_path / "other", heldout=0.1, task="s2_action")))
    assert gate.main([]) == 0
    assert "SKIP s1_heldout: no s1_triage version" in capsys.readouterr().out
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(tmp_path / "none" / "registry.json"))
    assert gate.main([]) == 0
    assert "SKIP s1_heldout: no fine-tune registry" in capsys.readouterr().out


def test_eval_gate_rl_pass_fail_skip(tmp_path, monkeypatch, capsys, two_runs):
    gate = _script("eval_gate")
    dir_a, dir_b = two_runs  # A: critical_under 2 in the last epoch; B: 1
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(tmp_path / "none" / "registry.json"))

    monkeypatch.setenv("RL_RUN_PATH", str(dir_b / "run.json"))
    monkeypatch.setenv("EVAL_GATE_BASELINE", str(dir_a))
    assert gate.main([]) == 0
    assert "PASS rl_critical_under: current 1 (epoch 2, run.json) vs baseline 2 (epoch 2, snap-a)" in capsys.readouterr().out

    monkeypatch.setenv("RL_RUN_PATH", str(dir_a / "run.json"))
    monkeypatch.setenv("EVAL_GATE_BASELINE", str(dir_b))
    assert gate.main([]) == 1
    assert "FAIL rl_critical_under: current 2" in capsys.readouterr().out
    assert gate.main(["--baseline", str(dir_a)]) == 0

    monkeypatch.setenv("EVAL_GATE_BASELINE", str(tmp_path / "absent"))
    assert gate.main([]) == 0
    assert "SKIP rl_critical_under: baseline" in capsys.readouterr().out
    monkeypatch.delenv("EVAL_GATE_BASELINE")
    monkeypatch.setenv("RL_RUN_PATH", str(tmp_path / "absent.json"))
    assert gate.main([]) == 0
    assert "SKIP rl_critical_under: no current run at absent.json" in capsys.readouterr().out
    # Default baseline is the committed memory-local snapshot.
    assert gate.baseline_ref() == rl_compare.DEFAULT_B


# --- scripts/mubit_requests.py ----------------------------------------------


def _outcome(system: str, priority: str, route: str) -> Outcome:
    return Outcome(
        system=system,
        outcome="reasoned_recommendation" if system == "system_2" else "fast_route",
        priority=priority,
        needs=["rescue"],
        route=route,
        confidence=0.9,
        reason="test",
        requires_human=priority == "P1",
        escalate=False,
    )


def _event(stage, case_id, at, **kwargs):
    return TraceEvent(
        case_id=case_id,
        stage=stage,
        started_at=datetime(2026, 10, 25, 6, 0, at, tzinfo=timezone.utc),
        latency_ms=kwargs.pop("latency_ms", 0),
        **kwargs,
    )


@pytest.fixture
def trace_file(tmp_path, monkeypatch):
    req_a = "mreq_" + "a" * 32
    req_b = "mreq_" + "b" * 32
    req_c = "mreq_" + "c" * 32
    events = [
        _event("mubit_chat", "C01", 1, latency_ms=900, model="m", notes=f"mubit chat host=api.mubit.ai status=ok request_id={req_a}"),
        _event("system_2", "C01", 2, latency_ms=900, outcome=_outcome("system_2", "P1", "rescue_coordination")),
        _event("router", "C01", 3, notes="router.merge ran on the selected outcome(s)"),
        _event("mubit_chat", "C02", 4, latency_ms=0, model="m", notes=f"mubit chat host=s2_cache/case status=cache_hit request_id={req_b} (recorded)"),
        _event("system_2", "C02", 5, outcome=_outcome("system_2", "P2", "supervisor_escalation")),
        # No request id: a 429 before Mubit answered. Not listed.
        _event("mubit_chat", "C03", 6, latency_ms=300, model="m", notes="mubit chat host=api.mubit.ai status=http_429"),
        # A crafted note: the key-looking token must not be printed.
        _event("mubit_chat", "C04", 7, latency_ms=100, model="m", notes=f"mubit chat host=api.mubit.ai status=ok request_id={req_c} key=mbt_should_not_appear"),
        _event("system_1", "C04", 8, outcome=_outcome("system_1", "P3", "welfare_distribution")),
        _event("router", "C04", 9, notes="router.merge ran on the selected outcome(s)"),
    ]
    path = tmp_path / "traces.jsonl"
    path.write_text("".join(e.model_dump_json() + "\n" for e in events), encoding="utf-8")
    monkeypatch.setenv("TRACE_PATH", str(path))
    return path, (req_a, req_b, req_c)


def test_mubit_requests_table_newest_first_with_outcomes(trace_file, capsys):
    mod = _script("mubit_requests")
    path, (req_a, req_b, req_c) = trace_file
    assert mod.main(["--n", "20"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].split()[:3] == ["time", "case_id", "request_id"]
    # The time cell is "YYYY-MM-DD HH:MM:SS", so the request id is the fourth token.
    assert [line.split()[3] for line in lines[2:]] == [req_c, req_b, req_a]
    assert "mbt_should_not_appear" not in out and "key=" not in out
    assert "s2_cache/case" in out and "cache_hit" in out and "(recorded)" in out
    assert "rescue_coordination P1" in out
    assert "welfare_distribution P3 (system_1)" in out
    assert mod.main(["--n", "1"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 3


def test_mubit_requests_json_and_missing_file(trace_file, capsys, tmp_path, monkeypatch):
    mod = _script("mubit_requests")
    path, (req_a, req_b, _) = trace_file
    assert mod.main(["--n", "2", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["trace_path"] == "traces.jsonl" and payload["count"] == 2
    second = payload["hops"][1]
    assert second["request_id"] == req_b and second["recorded"] is True
    assert second["status"] == "cache_hit" and second["routed"] is False
    assert second["outcome"] == "supervisor_escalation P2" and second["outcome_system"] == "system_2"
    first = [h for h in payload["hops"] if h["request_id"] == req_a]
    assert first == [] or first[0]["routed"] is True
    assert str(tmp_path) not in json.dumps(payload)
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "none.jsonl"))
    assert mod.main([]) == 0
    assert "no trace file" in capsys.readouterr().err
