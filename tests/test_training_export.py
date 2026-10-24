"""Training exports and per-task fine-tune datasets. No GPU and no SetFit import."""

import hashlib
import json
import sys
from datetime import datetime, timezone

import pytest

from contracts.training import InputRef, TrainingEvent, current_policy_version
from eval.correction_loop import run as correction_loop
from infra.modal.finetune_job import (
    DatasetError,
    load_task_datasets,
    parse_dataset,
    plan_version,
    role_for,
)
from training.export import default_source, export_datasets


def _event(policy_version: str, **overrides) -> TrainingEvent:
    ref = overrides.pop(
        "input_ref",
        InputRef(
            case_id="F01",
            turn_ids=["0"],
            lang="en",
            policy_ids=["SPHERE-WASH-15L"],
            memory_ref=None,
        ),
    )
    base = dict(
        event_id="00000000-0000-4000-8000-000000000010",
        created_at=datetime(2026, 10, 24, 1, tzinfo=timezone.utc),
        task="s1_triage",
        group_id="F01-water",
        input_ref=ref,
        output_model=None,
        output_correct="sphere_water_short",
        reason="Synthetic water request, not a general patient.",
        source="human",
        corrected_by="operator",
        weight=1.0,
        model_version="s1@v3",
        policy_version=policy_version,
    )
    base.update(overrides)
    return TrainingEvent(**base)


def _write(path, events: list[TrainingEvent]) -> None:
    path.write_text(
        "".join(event.model_dump_json() + "\n" for event in events),
        encoding="utf-8",
    )


def test_export_is_deterministic_and_deduped(tmp_path):
    version = current_policy_version()
    early = _event(version, weight=1.0, reason="first reason")
    later = _event(
        version,
        event_id="00000000-0000-4000-8000-000000000099",
        created_at=datetime(2026, 10, 24, 2, tzinfo=timezone.utc),
        weight=0.2,
        reason="later reason that must not win",
    )
    s2 = _event(
        version,
        event_id="00000000-0000-4000-8000-000000000020",
        created_at=datetime(2026, 10, 24, 3, tzinfo=timezone.utc),
        task="s2_action",
        output_correct="ask_next_question",
        reason="Ask which district.",
        model_version="s2@v1",
    )
    sapling = _event(
        version,
        event_id="00000000-0000-4000-8000-000000000030",
        created_at=datetime(2026, 10, 24, 4, tzinfo=timezone.utc),
        task="sapling_verdict",
        output_model="unsure",
        output_correct="supported",
        reason="The claim matches the policy text.",
        source="coach",
        corrected_by=None,
        model_version="sapling@v1",
    )
    missing = _event(
        "ab" * 32,
        event_id="00000000-0000-4000-8000-000000000040",
        created_at=datetime(2026, 10, 24, 5, tzinfo=timezone.utc),
        task="sapling_verdict",
        group_id="missing-policy",
        input_ref=InputRef(
            case_id="NOT-A-FIXTURE",
            turn_ids=[],
            lang="en",
            policy_ids=["SPHERE-WASH-15L"],
        ),
        output_model=None,
        output_correct="violation",
        reason="The pin is not in the local corpus.",
        source="sim",
        corrected_by=None,
        model_version="sapling@v1",
    )
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    _write(first_dir / "01.jsonl", [early, later, s2])
    _write(first_dir / "02.jsonl", [sapling, missing])
    _write(second_dir / "01.jsonl", [missing, sapling, later])
    _write(second_dir / "02.jsonl", [s2, early])

    out_a = tmp_path / "out-a"
    out_b = tmp_path / "out-b"
    manifests_a = export_datasets(first_dir, out_a)
    manifests_b = export_datasets(second_dir, out_b)
    for name in ("s1", "s2", "sapling", "prefs"):
        assert (out_a / f"{name}.jsonl").read_bytes() == (out_b / f"{name}.jsonl").read_bytes()
        body = (out_a / f"{name}.jsonl").read_text(encoding="utf-8")
        manifest = json.loads((out_a / f"{name}.manifest.json").read_text(encoding="utf-8"))
        assert manifest == manifests_a[name] == manifests_b[name]
        assert manifest["schema_version"] == 1
        assert manifest["hash"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert set(manifest) == {"schema_version", "event_count", "policy_version", "hash"}

    s1_rows = [json.loads(line) for line in (out_a / "s1.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(s1_rows) == 1
    assert s1_rows[0]["label"] == "sphere_water_short"
    assert s1_rows[0]["group_id"] == "F01-water"
    assert s1_rows[0]["weight"] == 1.0
    assert s1_rows[0]["text"] == "caller: Hello, we need drinking water for the house."
    assert "later reason" not in s1_rows[0]["text"]
    assert manifests_a["s1"]["event_count"] == 1
    assert manifests_a["s1"]["policy_version"] == version

    s2_row = json.loads((out_a / "s2.jsonl").read_text(encoding="utf-8").strip())
    assert [message["role"] for message in s2_row["messages"]] == ["system", "user", "assistant"]
    assert "[SPHERE-WASH-15L]" in s2_row["messages"][0]["content"]
    assert "15 litres" in s2_row["messages"][0]["content"]
    assert s2_row["messages"][1]["content"].startswith("caller: ")
    assert s2_row["messages"][2]["content"].startswith("ask_next_question\n")

    sapling_rows = [
        json.loads(line) for line in (out_a / "sapling.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    by_verdict = {row["verdict"]: row for row in sapling_rows}
    assert set(by_verdict) == {"supported", "violation"}
    assert by_verdict["supported"]["claim"] == "The claim matches the policy text."
    assert "15 litres" in by_verdict["supported"]["policy"]
    assert "case_id: NOT-A-FIXTURE" in by_verdict["violation"]["evidence"]
    assert "not available" in by_verdict["violation"]["policy"]
    assert manifests_a["sapling"]["policy_version"] == ",".join(sorted([version, "ab" * 32]))

    prefs = [
        json.loads(line) for line in (out_a / "prefs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert prefs == [
        {
            "chosen": "supported",
            "prompt": prefs[0]["prompt"],
            "rejected": "unsure",
        }
    ]
    assert "15 litres" in prefs[0]["prompt"]
    assert manifests_a["prefs"]["event_count"] == 1


def test_empty_log_writes_manifests(tmp_path):
    missing = tmp_path / "no-log"
    out = tmp_path / "out"
    manifests = export_datasets(missing, out, allow_missing=True)
    empty_hash = hashlib.sha256(b"").hexdigest()
    for name, manifest in manifests.items():
        assert manifest["event_count"] == 0
        assert manifest["policy_version"] is None
        assert manifest["hash"] == empty_hash
        assert (out / f"{name}.jsonl").read_bytes() == b""


def test_correction_loop_event_exports_an_s1_row(tmp_path, monkeypatch):
    monkeypatch.delenv("MUBIT_BASE_URL", raising=False)
    correction_loop(out_dir=tmp_path)
    out = tmp_path / "export"
    manifests = export_datasets(default_source(), out)
    assert manifests["s1"]["event_count"] == 1
    assert manifests["s2"]["event_count"] == 0
    assert manifests["prefs"]["event_count"] == 0
    row = json.loads((out / "s1.jsonl").read_text(encoding="utf-8").strip())
    assert row["label"] == "sphere_water_short"
    assert row["group_id"] == "CORR-LOOP-1"
    assert row["weight"] == 1.0
    assert "case_id: CORR-LOOP-1" in row["text"]


def test_s1_dataset_plans_setfit_and_sft_jsonl_still_plans(tmp_path):
    s1 = json.dumps(
        {
            "text": "Synthetic caller needs drinking water.",
            "label": "sphere_water_short",
            "group_id": "g",
            "weight": 1,
        }
    ) + "\n"
    parsed = parse_dataset(s1, "s1_triage")
    assert parsed[0]["label"] == "sphere_water_short"
    version_id, registry = plan_version(
        s1, "TODO_HUMAN", dry_run=True, role="system_1", task="s1_triage"
    )
    assert version_id.startswith("ft-")
    assert registry["jobs"][0]["status"] == "stub"
    assert registry["versions"][0]["role"] == "system_1"
    assert "Task s1_triage." in registry["jobs"][0]["notes"]
    assert "Dry run. No weights were trained." in registry["jobs"][0]["notes"]
    _planned_id, planned = plan_version(
        s1, "TODO_HUMAN", dry_run=False, role="system_1", task="s1_triage"
    )
    assert planned["jobs"][0]["status"] == "completed"
    assert "SetFit" in planned["jobs"][0]["notes"]
    assert "setfit" not in sys.modules
    with pytest.raises(DatasetError):
        parse_dataset(s1, "sft")
    with pytest.raises(DatasetError, match="S1Label"):
        parse_dataset(
            json.dumps({"text": "Synthetic caller.", "label": "welfare_distribution"}) + "\n",
            "s1_triage",
        )

    messages = json.dumps(
        {
            "messages": [
                {"role": "system", "content": "Label a synthetic flood-call route."},
                {"role": "user", "content": "Synthetic caller. Drinking water requested."},
                {"role": "assistant", "content": "welfare_distribution"},
            ]
        }
    ) + "\n"
    legacy_id, legacy = plan_version(messages, "TODO_HUMAN", dry_run=True)
    assert legacy_id.startswith("ft-")
    assert legacy["jobs"][0]["status"] == "stub"
    assert legacy["jobs"][0]["notes"] == "Dry run. No weights were trained."
    assert role_for("s1_triage") == "system_1"
    assert role_for("sft") == "system_2"

    s2 = json.dumps(
        {
            "messages": [
                {"role": "system", "content": "[SPHERE-WASH-15L]\nSynthetic policy."},
                {"role": "user", "content": "caller: Synthetic water request."},
                {"role": "assistant", "content": "ask_next_question\nAsk the district."},
            ]
        }
    ) + "\n"
    assert parse_dataset(s2, "s2_action")[0][2]["content"].startswith("ask_next_question")
    with pytest.raises(DatasetError, match="S2Action"):
        parse_dataset(messages, "s2_action")

    s1_path = tmp_path / "s1.jsonl"
    s2_path = tmp_path / "s2.jsonl"
    sft_path = tmp_path / "sft.jsonl"
    s1_path.write_text(s1, encoding="utf-8")
    s2_path.write_text(s2, encoding="utf-8")
    sft_path.write_text(messages, encoding="utf-8")
    named = load_task_datasets("", "", str(s1_path), str(s2_path))
    assert [item[0] for item in named] == ["s1_triage", "s2_action"]
    inferred = load_task_datasets(str(sft_path))
    assert inferred[0][0] == "sft"
