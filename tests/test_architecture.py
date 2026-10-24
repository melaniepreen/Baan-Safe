import json
import os

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config.settings import DecisionRequired
from contracts.models import AidEligibility, Failure, Person
from eval.correction_loop import run as correction_loop
from fixtures.load import load_case
from gateway.route import handle
from llm.client import chat_completions_url, complete
from trace import read_traces


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_exclusive_routes_record_one_system(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PATH", str(tmp_path / "traces.jsonl"))
    fast = handle(load_case("F01"), use_stubs=True)
    assert [item.system.value for item in fast.source_outcomes] == ["system_1"]
    slow = handle(load_case("F10"), use_stubs=True)
    assert [item.system.value for item in slow.source_outcomes] == ["system_2"]
    f01_stages = [event.stage for event in read_traces("F01")]
    f10_stages = [event.stage for event in read_traces("F10")]
    assert "system_2" not in f01_stages
    assert "system_1" not in f10_stages
    f10_system = [event for event in read_traces("F10") if event.stage == "system_2"]
    assert f10_system and f10_system[0].outcome is not None
    assert f10_system[0].outcome.outcome == "reasoned_recommendation" or f10_system[0].outcome.system.value == "system_2"


def test_s1_real_does_not_run_on_a_system_2_fixture(client, monkeypatch):
    monkeypatch.setenv("S1_IMPL", "real")
    case = json.loads(load_case("F10").model_dump_json())
    response = client.post("/triage", json=case)
    assert response.status_code == 200
    systems = [item["system"] for item in response.json()["source_outcomes"]]
    assert systems == ["system_2"]


def test_non_fixture_route_is_todo_human(client):
    case = json.loads(load_case("F01").model_dump_json())
    case["case_id"] = "case-not-a-fixture"
    response = client.post("/triage", json=case)
    assert response.status_code == 501
    assert "gateway.route_chooser" in response.json()["detail"]


def test_llm_refuses_without_mubit_url(monkeypatch):
    monkeypatch.delenv("MUBIT_BASE_URL", raising=False)
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MUBIT_BASE_URL"):
        complete([{"role": "user", "content": "synthetic"}])


def test_llm_refuses_other_hosts_and_hides_the_key(monkeypatch):
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    with pytest.raises(RuntimeError, match="not a Mubit host") as caught:
        complete([{"role": "user", "content": "synthetic"}])
    assert "mbt_should_not_appear" not in str(caught.value)


def test_llm_refuses_openrouter_and_ignores_its_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should_not_appear")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    with pytest.raises(RuntimeError, match="not a Mubit host") as caught:
        complete([{"role": "user", "content": "synthetic"}])
    text = str(caught.value)
    assert "sk-should_not_appear" not in text
    assert "mbt_should_not_appear" not in text
    assert "openrouter.ai" in text


def test_compat_openrouter_prefix_is_the_chat_url():
    assert (
        chat_completions_url("https://api.mubit.ai/compat/openrouter/v1")
        == "https://api.mubit.ai/compat/openrouter/v1/chat/completions"
    )
    assert (
        chat_completions_url("https://api.mubit.ai")
        == "https://api.mubit.ai/openai/v1/chat/completions"
    )
    with pytest.raises(RuntimeError, match="not the gateway root"):
        chat_completions_url("https://api.mubit.ai/openai/v1/models")


def test_llm_still_needs_model_after_provider_route_is_set(monkeypatch):
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai/compat/openrouter/v1")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    with pytest.raises(DecisionRequired, match="orchestrator_model") as caught:
        complete([{"role": "user", "content": "synthetic"}])
    assert "mbt_should_not_appear" not in str(caught.value)


def test_openai_client_registers_compat_prefix(monkeypatch):
    from llm.openai_client import make_client, registered_base_url

    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai/compat/openrouter/v1")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    assert registered_base_url() == "https://api.mubit.ai/compat/openrouter/v1"
    client = make_client()
    assert str(client.base_url).rstrip("/") == "https://api.mubit.ai/compat/openrouter/v1"
    assert "mbt_should_not_appear" not in repr(client)


def test_aid_stubs_return_501(client):
    eligibility = client.get("/aid/eligibility", params={"case_id": "F01"})
    assert eligibility.status_code == 501
    assert "Melanie" in eligibility.json()["detail"]
    assert "auto-approve" in eligibility.json()["detail"]
    case = json.loads(load_case("F16").model_dump_json())
    exceptions = client.post("/aid/exceptions", json=case)
    assert exceptions.status_code == 501
    assert "Melanie" in exceptions.json()["detail"]


def test_ontology_models_reject_extra_fields():
    person = Person(person_id="synthetic:person-1", role="caller")
    assert person.person_id.startswith("synthetic:")
    with pytest.raises(Exception):
        Person(person_id="synthetic:person-1", phone="0800000000")
    failure = Failure(
        failure_id="fail-1",
        case_id="CORR-LOOP-1",
        summary="Wrong route on a synthetic water request.",
        kind="wrong_route",
    )
    assert failure.kind == "wrong_route"
    eligibility = AidEligibility(case_id="F01")
    assert eligibility.status == "unset"


def test_correction_loop_exports_jsonl_and_comparison(tmp_path, monkeypatch):
    monkeypatch.delenv("MUBIT_BASE_URL", raising=False)
    report = correction_loop(out_dir=tmp_path)
    dataset = (tmp_path / "sft.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(dataset) == 1
    row = json.loads(dataset[0])
    assert [message["role"] for message in row["messages"]] == ["system", "user", "assistant"]
    assert row["messages"][2]["content"] == "welfare_distribution"
    assert report["quality"]["before"] == 0.0
    assert report["quality"]["after"] == 1.0
    assert report["cost_usd"]["before"] is None
    assert report["cost_usd"]["after"] is None
    assert report["promoted_to_system_1"] is False
    registry = json.loads((tmp_path / "model_registry.json").read_text(encoding="utf-8"))
    versions = [item["version_id"] for item in registry["versions"]]
    assert versions == ["stub-0", "stub-1"]
    assert registry["jobs"][0]["status"] == "stub"
    assert "MUBIT_BASE_URL" not in os.environ or os.environ.get("MUBIT_BASE_URL", "") == ""
    from training.log import read_events

    events = read_events()
    assert len(events) == 1
    assert events[0].task == "s1_triage"
    assert events[0].source == "human"
    assert events[0].output_correct.value == "sphere_water_short"
    assert events[0].output_model is None
    assert events[0].group_id == "CORR-LOOP-1"
    assert events[0].schema_version == 1
    assert report["training_event_written"] is True
