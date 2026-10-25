"""GET /training, the training page, and the fine-tune metrics helpers.

No GPU, no network, no torch or setfit import. The registry, metrics,
run.json, and traces are temp files.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.routes import training as surface
from contracts.models import TraceEvent
from infra.modal import finetune_job as job
from paths import ROOT

# --- fine-tune metrics helpers (pure) ---------------------------------------


def test_loss_curve_from_log_history_prefers_embedding_loss_and_skips_eval_rows():
    history = [
        {"embedding_loss": 0.9, "step": 1, "epoch": 0.1},
        {"embedding_loss": 0.5, "step": 2},
        {"eval_embedding_loss": 0.4, "step": 2},
        {"loss": 0.3, "step": 3},
        {"learning_rate": 1e-5, "step": 4},
        "not a dict",
        {"loss": "nan-ish"},
    ]
    curve = job.loss_curve_from_log_history(history)
    assert curve == [
        {"step": 1, "loss": 0.9},
        {"step": 2, "loss": 0.5},
        {"step": 3, "loss": 0.3},
    ]
    assert job.loss_curve_from_log_history(None) == []
    # A missing step falls back to the row position.
    assert job.loss_curve_from_log_history([{"loss": 1.0}, {"loss": 0.5}]) == [
        {"step": 1, "loss": 1.0},
        {"step": 2, "loss": 0.5},
    ]


def test_loss_summary_and_empty_curve():
    curve = [{"step": 1, "loss": 1.0}, {"step": 2, "loss": 0.25}, {"step": 3, "loss": 0.5}]
    summary = job.loss_summary(curve)
    assert summary == {
        "first_loss": 1.0,
        "last_loss": 0.5,
        "min_loss": 0.25,
        "mean_loss": pytest.approx(0.5833, abs=1e-3),
    }
    assert job.loss_summary([]) == {
        "first_loss": None,
        "last_loss": None,
        "min_loss": None,
        "mean_loss": None,
    }


def test_setfit_log_history_reads_st_trainer_then_trainer_then_nothing():
    inner = SimpleNamespace(state=SimpleNamespace(log_history=[{"embedding_loss": 0.7, "step": 1}]))
    wrapped = SimpleNamespace(st_trainer=inner, state=SimpleNamespace(log_history=[]))
    assert job.setfit_log_history(wrapped) == [{"embedding_loss": 0.7, "step": 1}]
    direct = SimpleNamespace(state=SimpleNamespace(log_history=[{"loss": 0.2, "step": 5}]))
    assert job.setfit_log_history(direct) == [{"loss": 0.2, "step": 5}]
    assert job.setfit_log_history(SimpleNamespace()) == []
    assert job.setfit_log_history(SimpleNamespace(st_trainer=None, state=None)) == []


def test_setfit_loss_curve_falls_back_to_callback_then_logger():
    fake = SimpleNamespace(st_trainer=SimpleNamespace(state=SimpleNamespace(log_history=[])))
    curve, source = job.setfit_loss_curve(
        fake,
        callback_logs=[{"embedding_loss": 0.6, "step": 1}, {"embedding_loss": 0.4, "step": 2}],
        handler_entries=[{"embedding_loss": 9.0, "step": 1}],
    )
    assert source == "callback"
    assert [point["loss"] for point in curve] == [0.6, 0.4]
    curve, source = job.setfit_loss_curve(
        fake, callback_logs=[], handler_entries=[{"embedding_loss": 0.8, "step": 3}]
    )
    assert source == "logger"
    assert curve == [{"step": 3, "loss": 0.8}]
    curve, source = job.setfit_loss_curve(fake)
    assert (curve, source) == ([], "none")
    with_state = SimpleNamespace(
        st_trainer=SimpleNamespace(
            state=SimpleNamespace(log_history=[{"embedding_loss": 0.3, "step": 2}])
        )
    )
    curve, source = job.setfit_loss_curve(with_state, callback_logs=[{"loss": 5.0}])
    assert source == "log_history"
    assert curve == [{"step": 2, "loss": 0.3}]


def test_loss_log_handler_parses_setfit_dict_lines():
    handler = job.LossLogHandler()
    logger = logging.getLogger("setfit.test_training_surface")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        logger.info("{'embedding_loss': 0.4123, 'learning_rate': 2e-05, 'epoch': 0.2, 'step': 3}")
        logger.info("Epoch 1/1 done")
        logger.info("{'loss': 0.11, 'step': 4}")
        logger.info("{'eval_embedding_loss': 0.9, 'step': 4}")
    finally:
        logger.removeHandler(handler)
    assert [entry.get("step") for entry in handler.entries] == [3, 4]
    assert job.loss_curve_from_log_history(handler.entries) == [
        {"step": 3, "loss": 0.4123},
        {"step": 4, "loss": 0.11},
    ]
    assert job.parse_loss_lines("no dict here") == []
    assert job.parse_loss_lines("{'embedding_loss': not valid}") == []


def test_heldout_metrics_accuracy_and_per_label():
    expected = ["a", "a", "b", "c"]
    predicted = ["a", "b", "b", "b"]
    block = job.heldout_metrics(expected, predicted)
    assert block["rows"] == 4
    assert block["accuracy"] == 0.5
    assert block["per_label"]["a"] == {"support": 2, "precision": 1.0, "recall": 0.5}
    assert block["per_label"]["b"]["support"] == 1
    assert block["per_label"]["b"]["precision"] == pytest.approx(1 / 3)
    assert block["per_label"]["b"]["recall"] == 1.0
    assert block["per_label"]["c"] == {"support": 1, "precision": None, "recall": 0.0}
    assert job.heldout_metrics([], [])["accuracy"] is None
    with pytest.raises(ValueError):
        job.heldout_metrics(["a"], [])


def test_heldout_path_for_sibling_and_env(tmp_path, monkeypatch):
    monkeypatch.delenv("FINETUNE_HELDOUT", raising=False)
    dataset = tmp_path / "s1_synthetic.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")
    assert job.heldout_path_for(str(dataset)) is None
    sibling = tmp_path / job.HELDOUT_NAME
    sibling.write_text('{"text": "x", "label": "sphere_water_short"}\n', encoding="utf-8")
    assert job.heldout_path_for(str(dataset)) == sibling
    explicit = tmp_path / "other.jsonl"
    explicit.write_text("", encoding="utf-8")
    monkeypatch.setenv("FINETUNE_HELDOUT", str(explicit))
    assert job.heldout_path_for(str(dataset)) == explicit
    monkeypatch.setenv("FINETUNE_HELDOUT", str(tmp_path / "missing.jsonl"))
    assert job.heldout_path_for(str(dataset)) is None
    assert job.heldout_path_for("") is None
    rows = job.parse_heldout('{"text": "water", "label": "sphere_water_short"}\n')
    assert rows[0]["label"] == "sphere_water_short"


def test_metrics_dict_shapes_without_torch_or_setfit():
    curve = [{"step": 1, "loss": 2.0}, {"step": 2, "loss": 1.0}]
    lora = job.lora_metrics(
        curve,
        rows=3,
        max_length=512,
        trainable_parameters=1234,
        wall_seconds=12.3456,
        base_model="base/model",
        gpu_name="T4",
    )
    assert lora["trainer"] == "lora"
    assert lora["steps"] == 2
    assert lora["rows"] == 3
    assert lora["max_length"] == 512
    assert lora["lr"] == job.LORA_LR
    assert lora["lora_r"] == job.LORA_R
    assert lora["trainable_parameters"] == 1234
    assert lora["wall_seconds"] == 12.346
    assert lora["loss_curve"] == curve
    assert (lora["first_loss"], lora["last_loss"], lora["min_loss"], lora["mean_loss"]) == (
        2.0,
        1.0,
        1.0,
        1.5,
    )
    rows = [
        {"text": "a", "label": "sphere_water_short"},
        {"text": "b", "label": "medical_urgent"},
        {"text": "c", "label": "sphere_water_short"},
    ]
    setfit = job.setfit_metrics(
        curve,
        rows=rows,
        base_model="sentence/model",
        max_steps=2,
        wall_seconds=1.0,
        loss_source="log_history",
        heldout={"rows": 2, "accuracy": 0.5, "per_label": {}},
    )
    assert setfit["trainer"] == "setfit"
    assert setfit["rows"] == 3
    assert setfit["label_count"] == 2
    assert setfit["labels"] == ["medical_urgent", "sphere_water_short"]
    assert setfit["base_model"] == "sentence/model"
    assert setfit["loss_source"] == "log_history"
    assert setfit["heldout"]["accuracy"] == 0.5
    assert setfit["first_loss"] == 2.0 and setfit["min_loss"] == 1.0
    without = job.setfit_metrics(
        [], rows=rows, base_model="m", max_steps=1, wall_seconds=0, loss_source="none"
    )
    assert "heldout" not in without
    assert without["last_loss"] is None
    for name in ("torch", "setfit", "peft"):
        assert name not in sys.modules, f"{name} was imported by the pure helpers"


def test_dry_run_still_avoids_training_imports(tmp_path, monkeypatch):
    text = json.dumps({"text": "water please", "label": "sphere_water_short"}) + "\n"
    version_id, registry = job.plan_version(text, "base/x", dry_run=True, task="s1_triage")
    assert version_id.startswith("ft-")
    assert registry["jobs"][0]["status"] == "stub"
    for name in ("torch", "setfit", "peft"):
        assert name not in sys.modules


# --- GET /training ----------------------------------------------------------


def _trace(case_id: str, status: str, latency: int, tokens_in=10, tokens_out=5, at="04:00:00"):
    return TraceEvent(
        case_id=case_id,
        stage="mubit_chat",
        started_at=datetime.fromisoformat(f"2026-10-25T{at}+00:00"),
        latency_ms=latency,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model="nvidia/nemotron-3-nano-30b-a3b",
        notes=f"mubit chat host=api.mubit.ai status={status}",
    )


@pytest.fixture
def surface_files(tmp_path, monkeypatch):
    registry_dir = tmp_path / "vol"
    registry_dir.mkdir()
    older = "ft-20261025T010000Z-aaaaaaaa"
    newer = "ft-20261025T020000Z-bbbbbbbb"
    registry = {
        "versions": [
            {
                "version_id": older,
                "model_name": "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1",
                "role": "system_2",
                "parent_version_id": None,
                "training_job_id": f"job-{older}",
                "notes": "LoRA adapter saved on the Modal volume. Task s2_action.",
            },
            {
                "version_id": newer,
                "model_name": "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1",
                "role": "system_1",
                "parent_version_id": older,
                "training_job_id": f"job-{newer}",
                "notes": "SetFit model saved on the Modal volume. Task s1_triage.",
            },
        ],
        "jobs": [
            {
                "job_id": f"job-{older}",
                "status": "completed",
                "dataset_path": f"/vol/versions/{older}/train.jsonl",
                "base_model": "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1",
                "target_version_id": older,
                "notes": "",
            },
            {
                "job_id": f"job-{newer}",
                "status": "failed",
                "dataset_path": f"/vol/versions/{newer}/train.jsonl",
                "base_model": "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1",
                "target_version_id": newer,
                "notes": "boom",
            },
        ],
    }
    (registry_dir / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    metrics_dir = registry_dir / "versions" / older
    metrics_dir.mkdir(parents=True)
    metrics = job.lora_metrics(
        [{"step": 1, "loss": 2.5}, {"step": 2, "loss": 1.5}, {"step": 3, "loss": 1.0}],
        rows=4,
        max_length=256,
        trainable_parameters=99,
        wall_seconds=30,
        base_model="nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1",
        gpu_name="T4",
    )
    (metrics_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(registry_dir / "registry.json"))

    run = {
        "schema": "baansafe.rl_run.v1",
        "s2": "live",
        "model": "nvidia/nemotron-3-nano-30b-a3b",
        "seed": 17,
        "epochs": [
            {
                "epoch": 1,
                "episodes": 48,
                "mean_reward": -0.4,
                "correct": 18,
                "under_triage": 16,
                "critical_under": 9,
                "missed_human": 9,
                "share_s1_only": 0.27,
                "share_cascade": 0.25,
                "share_s2_only": 0.48,
                "s2_fallbacks": 0,
            },
            {
                "epoch": 2,
                "episodes": 48,
                "mean_reward": 0.1,
                "correct": 30,
                "under_triage": 8,
                "critical_under": 2,
                "missed_human": 3,
                "share_s1_only": 0.3,
                "share_cascade": 0.3,
                "share_s2_only": 0.4,
                "s2_fallbacks": 1,
            },
        ],
        "episodes": [{}] * 96,
        "events": [{"kind": "graduate"}, {"kind": "demote"}],
        "final_overlay": {
            "schema": "baansafe.rl_overlay.v1",
            "graduation_threshold": 2,
            "graduated": {"sig-a": {}},
            "recommendations": {},
            "demoted": {"sig-b": {}, "sig-c": {}},
        },
        "mubit": {
            "via": "api.mubit.ai",
            "model": "nvidia/nemotron-3-nano-30b-a3b",
            "mubit_chat_count": 209,
            "live_ok": 54,
            "cache_hits": 154,
            "errors": 1,
            "avg_latency_ms": 450.6,
        },
        "training": {
            "status": "exported",
            "counts": {"s1": 18, "s2": 36, "sapling": 0, "prefs": 8},
            "finetune": "ready: make modal-finetune",
        },
        "notes": [],
    }
    run_path = tmp_path / "rl_run.json"
    run_path.write_text(json.dumps(run), encoding="utf-8")
    monkeypatch.setenv("RL_RUN_PATH", str(run_path))

    trace_path = tmp_path / "traces.jsonl"
    rows = [
        _trace("C01", "ok", 1000, at="04:00:00"),
        _trace("C01", "ok", 2000, at="04:00:05"),
        _trace("C02", "http_429", 300, tokens_in=None, tokens_out=None, at="04:00:10"),
        _trace("C03", "cache_hit", 0, tokens_in=None, tokens_out=None, at="04:00:20"),
        _trace("C04", "ok", 3000, at="04:01:00"),
    ]
    other = TraceEvent(
        case_id="C01",
        stage="system_2",
        started_at=datetime(2026, 10, 25, 4, 0, tzinfo=timezone.utc),
        latency_ms=1200,
    )
    trace_path.write_text(
        "".join(event.model_dump_json() + "\n" for event in [*rows, other]), encoding="utf-8"
    )
    monkeypatch.setenv("TRACE_PATH", str(trace_path))

    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"task": "s1_triage", "source": "human"}),
                json.dumps({"task": "s1_triage", "source": "sim"}),
                json.dumps({"task": "s2_action", "source": "sim"}),
                "not json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TRAINING_EVENTS_PATH", str(events_path))
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "s1.manifest.json").write_text(
        json.dumps({"schema_version": 1, "event_count": 18, "policy_version": "abc", "hash": "h"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(surface, "MANIFEST_DIRS", (manifests, tmp_path / "absent"))
    return {"older": older, "newer": newer, "tmp": tmp_path}


@pytest.fixture
def client():
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_training_endpoint_joins_registry_run_traces_and_events(client, surface_files):
    response = client.get("/training")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"generated_at", "finetune", "rl", "mubit_traffic", "events", "missing", "note"}

    finetune = body["finetune"]
    assert finetune["version_count"] == 2
    assert [v["version_id"] for v in finetune["versions"]] == [
        surface_files["newer"],
        surface_files["older"],
    ]
    newer, older = finetune["versions"]
    assert newer["task"] == "s1_triage"
    assert newer["role"] == "system_1"
    assert newer["status"] == "failed"
    assert newer["loss_curve"] == []
    assert newer["created_at"] == "2026-10-25T02:00:00+00:00"
    assert older["task"] == "s2_action"
    assert older["status"] == "completed"
    assert older["gpu"] == "T4"
    assert older["steps"] == 3
    assert older["rows"] == 4
    assert (older["first_loss"], older["last_loss"], older["min_loss"]) == (2.5, 1.0, 1.0)
    assert older["loss_curve"][0] == {"step": 1, "loss": 2.5}
    assert older["metrics"]["lora_r"] == job.LORA_R
    assert older["heldout_accuracy"] is None
    assert finetune["decided"] == {
        "base_model": "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1",
        "gpu": "T4",
    }
    assert finetune["missing"] == []

    rl = body["rl"]
    assert rl["schema"] == "baansafe.rl_run.v1"
    assert rl["s2"] == "live"
    assert [e["epoch"] for e in rl["epochs"]] == [1, 2]
    assert rl["epochs"][1]["mean_reward"] == 0.1
    assert rl["epochs"][1]["share_cascade"] == 0.3
    assert rl["mubit"]["live_ok"] == 54
    assert rl["overlay"] == {
        "graduation_threshold": 2,
        "graduated": 1,
        "recommendations": 0,
        "demoted": 2,
    }
    assert rl["training"]["counts"]["s2"] == 36
    assert rl["finetune"] == "ready: make modal-finetune"
    assert rl["episode_count"] == 96
    assert rl["event_count"] == 2

    mubit = body["mubit_traffic"]
    assert mubit["call_count"] == 5
    assert mubit["ok_count"] == 3
    assert mubit["error_count"] == 1
    assert mubit["cache_hit_count"] == 1
    assert mubit["distinct_sessions"] == 4
    # Cache hits (0 ms) are not latency samples.
    assert mubit["avg_latency_ms"] == pytest.approx((1000 + 2000 + 300 + 3000) / 4)
    assert mubit["p50_latency_ms"] == 2000.0
    assert mubit["p95_latency_ms"] == 3000.0
    assert mubit["tokens_in_total"] == 30
    assert mubit["tokens_out_total"] == 15
    assert mubit["models"] == {"nvidia/nemotron-3-nano-30b-a3b": 5}
    assert mubit["first_call_at"].startswith("2026-10-25T04:00:00")
    assert mubit["last_call_at"].startswith("2026-10-25T04:01:00")
    assert mubit["kept_example_threshold"] == 25
    assert "Mubit console" in mubit["note"]

    events = body["events"]
    assert events["total"] == 3
    assert events["skipped_lines"] == 1
    assert events["by_task"] == {"s1_triage": 2, "s2_action": 1}
    assert events["by_source"] == {"human": 1, "sim": 2}
    assert len(events["manifests"]) == 1
    assert events["manifests"][0]["event_count"] == 18
    assert events["manifests"][0]["path"] == "s1.manifest.json"
    assert events["missing"] == ["absent"]
    assert body["missing"] == ["absent"]

    text = response.text
    assert str(surface_files["tmp"]) not in text, "temp paths must not leak"
    assert "MUBIT_API_KEY" not in text


def test_training_endpoint_with_nothing_on_disk(client, tmp_path, monkeypatch):
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(tmp_path / "none" / "registry.json"))
    monkeypatch.setenv("RL_RUN_PATH", str(tmp_path / "none" / "run.json"))
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "none" / "traces.jsonl"))
    monkeypatch.setenv("TRAINING_EVENTS_PATH", str(tmp_path / "none" / "events.jsonl"))
    monkeypatch.setattr(surface, "MANIFEST_DIRS", (tmp_path / "none" / "manifests",))
    response = client.get("/training")
    assert response.status_code == 200
    body = response.json()
    assert body["finetune"]["versions"] == []
    assert body["finetune"]["decided"]["base_model"]
    assert body["rl"]["epochs"] == []
    assert body["rl"]["overlay"] == {}
    assert body["mubit_traffic"]["call_count"] == 0
    assert body["mubit_traffic"]["avg_latency_ms"] is None
    assert body["mubit_traffic"]["distinct_sessions"] == 0
    assert body["events"]["total"] == 0
    assert body["events"]["manifests"] == []
    assert body["missing"] == [
        "registry.json",
        "run.json",
        "traces.jsonl",
        "events.jsonl",
        "manifests",
    ]
    assert str(tmp_path) not in response.text


def test_registry_path_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("TRAINING_REGISTRY_PATH", raising=False)
    monkeypatch.setattr(surface, "VOLUME_REGISTRY_PATH", str(tmp_path / "vol" / "registry.json"))
    assert surface.registry_path() == surface.LOCAL_REGISTRY_PATH
    (tmp_path / "vol").mkdir()
    assert surface.registry_path() == tmp_path / "vol" / "registry.json"
    monkeypatch.setenv("TRAINING_REGISTRY_PATH", str(tmp_path / "x.json"))
    assert surface.registry_path() == tmp_path / "x.json"
    monkeypatch.delenv("RL_RUN_PATH", raising=False)
    assert surface.rl_run_path() == surface.DEFAULT_RL_RUN_PATH


def test_display_path_hides_paths_outside_repo_and_volumes(tmp_path):
    assert surface.display_path(ROOT / "eval" / "out" / "rl" / "run.json") == "eval/out/rl/run.json"
    assert surface.display_path(Path("/vol/registry.json")) == "/vol/registry.json"
    assert surface.display_path(Path("/data/rl_run.json")) == "/data/rl_run.json"
    assert surface.display_path(tmp_path / "secret-dir" / "traces.jsonl") == "traces.jsonl"
    assert surface.display_path(Path("/volume-not/registry.json")) == "registry.json"


def test_decided_never_raises(monkeypatch):
    assert surface._decided("modal.finetune_gpu") == "T4"
    assert surface._decided("modal.s2_model_id") == "TODO_HUMAN"
    assert surface._decided("no.such.key") == "TODO_HUMAN"


def test_training_page_is_served_and_reads_the_endpoint(client):
    page = client.get("/ui/training.html")
    assert page.status_code == 200
    assert "training.js" in page.text
    script = client.get("/ui/training.js")
    assert script.status_code == 200
    source = script.text
    assert 'fetch("/training")' in source
    for key in ("mubit_traffic", "distinct_sessions", "loss_curve", "mean_reward", "by_task"):
        assert key in source
    assert "<svg" not in source and "createElementNS" in source
    for banned in ("MUBIT_", "OPENROUTER", "Bearer", "api.mubit.ai"):
        assert banned not in source
    html = (ROOT / "ui" / "training.html").read_text(encoding="utf-8")
    assert "import " not in html.split("<script")[0]
    assert "<script src=\"training.js\">" in html
