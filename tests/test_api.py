import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from fixtures.load import load_case


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["impl"]["S1_IMPL"] == "stub"


def test_fixtures_list_and_one(client):
    listing = client.get("/fixtures")
    assert listing.status_code == 200
    assert any(item["id"] == "F01" for item in listing.json()["fixtures"])
    one = client.get("/fixtures/F01")
    assert one.status_code == 200
    assert one.json()["id"] == "F01"


def test_stream(client):
    response = client.get("/fixtures/F01/stream", params={"pace": 0})
    assert response.status_code == 200
    assert "event: turn" in response.text
    assert "event: done" in response.text


def test_create_case_and_turn_and_get(client):
    created = client.post("/cases", json={"fixture_id": "F01"})
    assert created.status_code == 200
    case_id = created.json()["case"]["case_id"]
    turned = client.post(
        f"/cases/{case_id}/turns",
        json={"t_ms": 90000, "speaker": "operator", "text": "We have noted the water request."},
    )
    assert turned.status_code == 200
    assert turned.json()["decision"]["final_route"] == "welfare_distribution"
    fetched = client.get(f"/cases/{case_id}")
    assert fetched.status_code == 200
    assert fetched.json()["latest_decision"]["final_priority"] == "P3"


def test_triage(client):
    case = json.loads(load_case("F05").model_dump_json())
    response = client.post("/triage", json=case)
    assert response.status_code == 200
    assert response.json()["final_route"] == "information_only"


def test_correction_changes_paired_memory(client):
    client.post("/cases", json={"fixture_id": "C01-a"})
    client.post("/cases", json={"fixture_id": "C01-b"})
    before = client.get("/cases/C01-b").json()["case"]["memory_context"]
    response = client.post(
        "/cases/C01-a/corrections",
        json={
            "corrected_by": "operator",
            "field": "priority",
            "old_value": "P3",
            "new_value": "P1",
            "reason": "door water plus elderly is rescue, runtime check",
        },
    )
    assert response.status_code == 200
    notes = " ".join(response.json()["decision"]["policy_notes"])
    assert "runtime check" in notes or response.json()["correction"]["reason"]
    after = client.get("/cases/C01-b").json()["case"]["memory_context"]
    assert len(after) == len(before) + 1
    assert any("runtime check" in item["summary"] for item in after)


def test_trace(client):
    client.post("/cases", json={"fixture_id": "F03"})
    client.post(
        "/cases/F03/turns",
        json={"t_ms": 80000, "speaker": "caller", "text": "Still two of us, still dry."},
    )
    response = client.get("/cases/F03/trace")
    assert response.status_code == 200
    stages = {event["stage"] for event in response.json()}
    assert {"gateway", "system_1", "router"} <= stages


def test_town_sim_is_served(client):
    page = client.get("/ui/sim/index.html")
    assert page.status_code == 200
    assert "Block map" in page.text
    town = client.get("/ui/sim/data/town.json")
    assert town.status_code == 200
    body = town.json()
    assert body["routes"] and body["buildings"]
    assert client.get("/ui/sim/vendor/pixi.min.mjs").status_code == 200


def test_context_resources_maps(client):
    context = client.get("/context", params={"district": "Mae Mo District"})
    assert context.status_code == 200
    assert "rainfall_forecast_24h_mm" in context.json()
    point = client.get("/context", params={"lat": 18.4, "lon": 99.8})
    assert point.status_code == 200
    resources = client.get("/resources")
    assert resources.status_code == 200
    assert resources.json()["boats"]
    flood = client.get("/map/flood")
    facilities = client.get("/map/facilities")
    assert flood.status_code == 200 and flood.json()["type"] == "FeatureCollection"
    assert facilities.status_code == 200 and facilities.json()["features"]


def _welfare_available(client) -> int:
    units = {
        unit["id"]: unit["available"]
        for unit in client.get("/resources").json()["welfare_points"]
    }
    return units["welfare-fictional-01"]


def test_confirm_and_cancel_dispatches(client):
    before = _welfare_available(client)
    client.post("/cases", json={"fixture_id": "F01"})
    turned = client.post(
        "/cases/F01/turns",
        json={"t_ms": 90000, "speaker": "operator", "text": "Dispatch water desk."},
    )
    assert turned.status_code == 200
    decision = turned.json()["decision"]
    assert decision["next_action"] == "create_provisional_dispatch"
    assert decision["dispatches"]
    rid = decision["dispatches"][0]["resource_id"]
    assert rid == "welfare-fictional-01"
    assert _welfare_available(client) == before - 1

    confirmed = client.post("/cases/F01/dispatches/confirm")
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["action"] == "confirmed"
    assert body["holds"] == [
        {"resource_id": rid, "need": "water", "status": "confirmed"}
    ]
    assert _welfare_available(client) == before - 1

    cancelled = client.post("/cases/F01/dispatches/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["action"] == "cancelled"
    assert cancelled.json()["holds"][0]["status"] == "released"
    assert _welfare_available(client) == before


def test_confirm_without_holds_is_422(client):
    client.post("/cases", json={"fixture_id": "F05"})
    response = client.post("/cases/F05/dispatches/confirm")
    assert response.status_code == 422
    assert "no provisional holds" in response.json()["detail"]


def test_cancel_unknown_case_is_404(client):
    response = client.post("/cases/missing/dispatches/cancel")
    assert response.status_code == 404


def test_replay_and_metrics(client):
    replay = client.post("/replay", json={"fixture_ids": ["F01", "F10"], "s1_impl": "stub", "s2_impl": "stub"})
    assert replay.status_code == 200
    body = replay.json()
    assert body["system_1"]["priority_accuracy"] == 1
    assert body["system_2"]["route_accuracy"] == 1
    client.post("/cases", json={"fixture_id": "F01"})
    client.post(
        "/cases/F01/turns",
        json={"t_ms": 70000, "speaker": "caller", "text": "Still four people."},
    )
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "pct_handled_by_system_1" in metrics.json()


def test_s2_real_returns_503(client, monkeypatch):
    monkeypatch.setenv("S2_IMPL", "real")
    case = json.loads(load_case("F10").model_dump_json())
    response = client.post("/triage", json=case)
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "MUBIT_API_KEY is not set" in detail


def test_docs(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/triage" in schema.json()["paths"]
