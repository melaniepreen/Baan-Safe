"""TrainingEvent v1, the correction adapter, and the append-only log."""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import app
from contracts.models import Correction, NextAction
from contracts.training import (
    DEFAULT_WEIGHTS,
    S1Label,
    S2Action,
    AdaptError,
    InputRef,
    SaplingVerdict,
    TrainingEvent,
    adapt_correction,
    content_hash_for,
)
from system2.sapling_client import VERDICTS
from training.log import append_event, read_events


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _ref() -> InputRef:
    return InputRef(
        case_id="F01",
        turn_ids=["0"],
        lang="en",
        policy_ids=["SPHERE-WASH-15L"],
        memory_ref=None,
    )


def _event(**overrides) -> TrainingEvent:
    base = dict(
        task="sapling_verdict",
        group_id="group-1",
        input_ref=_ref(),
        output_model=None,
        output_correct="supported",
        reason="Synthetic claim matches the policy text.",
        source="coach",
        model_version="sapling@v1",
        policy_version="a" * 64,
    )
    base.update(overrides)
    return TrainingEvent(**base)


def _correction(**overrides) -> Correction:
    base = dict(
        correction_id="corr-1",
        case_id="F01",
        corrected_by="supervisor",
        field="verdict",
        old_value="unsure",
        new_value="supported",
        reason="The claim matches the policy text.",
        created_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
        model_version="sapling@v1",
        policy_version="b" * 64,
    )
    base.update(overrides)
    return Correction(**base)


def test_closed_enums_match_their_sources():
    from policies.service import get_service

    body = get_service().labels()
    api_ids = {row["id"] for row in body["labels"]}
    assert api_ids == {item.value for item in S1Label}
    assert {item.value for item in S2Action} == {item.value for item in NextAction}
    assert {item.value for item in SaplingVerdict} == set(VERDICTS)


def test_event_rejects_extra_and_wrong_task_label():
    with pytest.raises(ValidationError):
        _event(note="nope")
    with pytest.raises(ValidationError):
        _event(task="s1_triage", output_correct="supported")
    with pytest.raises(ValidationError):
        _event(schema_version=2)
    human = _event(source="human", corrected_by="operator")
    assert human.weight == DEFAULT_WEIGHTS["human"]
    with pytest.raises(ValidationError):
        _event(source="human", corrected_by=None)


def test_weight_defaults_and_env_override(monkeypatch):
    assert _event(source="coach").weight == 0.5
    assert _event(source="sim").weight == 0.25
    monkeypatch.setenv("TRAINING_WEIGHT_SIM", "0.1")
    assert _event(source="sim").weight == 0.1
    assert _event(source="sim", weight=0.4).weight == 0.4


def test_content_hash_is_stable_and_ignores_reason():
    first = _event(reason="one reason")
    second = _event(reason="another reason")
    assert first.content_hash == second.content_hash
    assert first.event_id != second.event_id
    assert first.content_hash == content_hash_for(
        first.task, first.input_ref, first.output_correct
    )
    with pytest.raises(ValidationError):
        _event(content_hash="0" * 64)


def test_log_appends_once_per_content_hash(tmp_path):
    path = tmp_path / "events.jsonl"
    original = _event()
    first = append_event(original, path=path)
    assert first.written is True
    body = path.read_bytes()
    second = append_event(_event(reason="same labels, new words"), path=path)
    assert second.written is False
    assert path.read_bytes() == body
    changed = _event(output_correct="violation")
    third = append_event(changed, path=path)
    assert third.written is True
    rows = read_events(path)
    assert [row.output_correct.value for row in rows] == ["supported", "violation"]
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_legacy_correction_adapts_when_the_value_is_a_closed_label():
    event = adapt_correction(_correction())
    assert event.task == "sapling_verdict"
    assert event.source == "human"
    assert event.corrected_by == "supervisor"
    assert event.output_model is not None
    assert event.output_model.value == "unsure"
    assert event.output_correct.value == "supported"
    assert event.weight == 1.0
    assert event.group_id == "F01"
    assert event.input_ref.lang == "en"
    assert event.model_version == "sapling@v1"
    assert event.schema_version == 1


def test_legacy_route_correction_is_not_invented_as_a_label():
    legacy = _correction(
        field="route",
        old_value="information_only",
        new_value="welfare_distribution",
        model_version=None,
        policy_version=None,
    )
    with pytest.raises(AdaptError):
        adapt_correction(legacy)


def test_old_correction_json_still_loads():
    raw = {
        "correction_id": "corr-old",
        "case_id": "C01-a",
        "corrected_by": "operator",
        "field": "priority",
        "old_value": "P3",
        "new_value": "P1",
        "reason": "door water plus elderly is rescue",
        "created_at": "2026-10-24T00:00:00Z",
    }
    row = Correction.model_validate(raw)
    assert row.task is None
    assert row.schema_version is None
    with pytest.raises(ValidationError):
        Correction.model_validate(raw | {"task": "not-a-task"})


def test_legacy_api_correction_does_not_enter_the_log(client):
    client.post("/cases", json={"fixture_id": "F01"})
    response = client.post(
        "/cases/F01/corrections",
        json={
            "corrected_by": "operator",
            "field": "priority",
            "old_value": "P3",
            "new_value": "P1",
            "reason": "legacy priority note stays on the memory path",
        },
    )
    assert response.status_code == 200
    assert read_events() == []


def test_v1_api_correction_is_logged_once(client):
    client.post("/cases", json={"fixture_id": "F01"})
    body = {
        "corrected_by": "operator",
        "field": "label",
        "old_value": "niems_white_general",
        "new_value": "sphere_water_short",
        "reason": "Synthetic water request, not a general patient.",
        "task": "s1_triage",
        "group_id": "F01-water",
        "lang": "en",
        "output_model": "niems_white_general",
        "output_correct": "sphere_water_short",
        "model_version": "s1@v1",
        "policy_version": "ab" * 32,
    }
    first = client.post("/cases/F01/corrections", json=body)
    second = client.post("/cases/F01/corrections", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["correction"]["schema_version"] == 1
    events = read_events()
    assert len(events) == 1
    assert events[0].output_correct.value == "sphere_water_short"
    assert events[0].output_model is not None
    assert events[0].output_model.value == "niems_white_general"
    assert events[0].group_id == "F01-water"
    assert events[0].content_hash
    line = json.loads(events[0].model_dump_json())
    assert line["content_hash"] == events[0].content_hash


def test_v1_api_correction_rejects_a_label_from_another_task(client):
    client.post("/cases", json={"fixture_id": "F01"})
    response = client.post(
        "/cases/F01/corrections",
        json={
            "corrected_by": "caseworker",
            "field": "label",
            "reason": "P1 is a priority, not an s1 label.",
            "task": "s1_triage",
            "output_correct": "P1",
            "model_version": "s1@v1",
            "policy_version": "cd" * 32,
        },
    )
    assert response.status_code == 422
    assert read_events() == []
