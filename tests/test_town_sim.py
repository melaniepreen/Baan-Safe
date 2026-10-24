"""The town simulation stays inside the v0.2 contracts and its own data files."""

from __future__ import annotations

import json
import re

from contracts.models import Hazard, Household, Need, Resource, Route
from paths import ROOT

SIM = ROOT / "ui" / "sim" / "data"
PHONE = re.compile(r"(?:\+66|0)[\s-]?\d[\d\s-]{7,}")
NATIONAL_ID = re.compile(r"\b\d{13}\b")
STATUSES = {"clear", "at_risk", "flooded", "needs_help", "evacuated"}


def _load(name: str) -> dict:
    return json.loads((SIM / name).read_text(encoding="utf-8"))


def test_placeholder_streets_are_labelled_and_swappable():
    body = _load("streets.json")
    assert body["streets"], "streets.json is the file to replace with real names"
    for street in body["streets"]:
        assert street["placeholder"] is True
        assert "จำลอง" in street["name_th"]
        assert street["name_en"].startswith("PLACEHOLDER")
        assert len(street["points"]) >= 2


def test_buildings_match_household_contract_and_are_addressable():
    town = _load("town.json")
    ids = [building["id"] for building in town["buildings"]]
    assert len(ids) == len(set(ids))
    households = []
    for building in town["buildings"]:
        assert building["sim_status"] in STATUSES
        if building.get("household"):
            households.append(Household.model_validate(building["household"]))
    assert len(households) > 20
    assert len({row.household_id for row in households}) == len(households)
    placed = {building["fixture_id"] for building in town["buildings"] if building.get("fixture_id")}
    assert {"F01", "F06", "F08", "F10", "F12"} <= placed


def test_hazards_resources_and_routes_use_contracts():
    town = _load("town.json")
    flood = _load("flood.json")
    assert flood["type"] == "FeatureCollection"
    assert flood["properties"]["placeholder"] is True
    hazard_ids = set()
    for feature in flood["features"]:
        hazard = Hazard.model_validate(
            {
                "hazard_id": feature["properties"]["hazard_id"],
                "kind": feature["properties"]["kind"],
                "summary": feature["properties"]["summary"],
                "location_label": feature["properties"]["location_label"],
            }
        )
        assert hazard.kind == "flood"
        hazard_ids.add(hazard.hazard_id)
    assert {row["hazard_id"] for row in town["hazards"]} == hazard_ids
    for row in town["hazards"]:
        Hazard.model_validate(row)

    snapshot = json.loads((ROOT / "mocks" / "resources.json").read_text(encoding="utf-8"))
    mock_ids = {
        row["id"]
        for group in ("boats", "ambulances", "shelters", "welfare_points")
        for row in snapshot[group]
    }
    placed = set()
    for row in town["resources"]:
        resource = Resource.model_validate(row)
        assert resource.kind in {"boat", "ambulance", "shelter", "welfare_point", "other"}
        placed.add(resource.resource_id)
    assert placed == mock_ids
    on_buildings = {building["resource_id"] for building in town["buildings"] if building.get("resource_id")}
    assert on_buildings == mock_ids


def test_demo_routes_follow_the_graph_and_the_fixture_route_enum():
    town = _load("town.json")
    by_id = {building["id"]: building for building in town["buildings"]}
    adj: dict[str, list[dict]] = {}
    for edge in town["graph"]["edges"]:
        adj.setdefault(edge["from"], []).append(edge)
        adj.setdefault(edge["to"], []).append(edge)
    modes = {"foot": "route-f06-evac", "boat": "route-f10-rescue"}
    found = {route["id"] for route in town["routes"]}
    assert set(modes.values()) <= found
    for route in town["routes"]:
        assert Route(route["contract_route"])
        for need in route["needs"]:
            Need(need)
        fixture = by_id[route["from_building"] if route["fixture_id"] == "F06" else route["to_building"]]
        if route["fixture_id"] == "F10":
            fixture = by_id["bldg-f10"]
        assert fixture["fixture"]["expected_route"] == route["contract_route"]
        nodes = route["node_ids"]
        assert nodes[0] == route["from_node"]
        assert nodes[-1] == route["to_node"]
        assert len(nodes) >= 2
        for left, right in zip(nodes, nodes[1:]):
            assert any(
                route["mode"] in edge["modes"]
                and {edge["from"], edge["to"]} == {left, right}
                for edge in adj[left]
            ), f"{route['id']} has a gap between {left} and {right}"


def test_embedded_fixture_summaries_match_the_fixture_files():
    town = _load("town.json")
    for building in town["buildings"]:
        summary = building.get("fixture")
        if not summary:
            continue
        fixture = json.loads((ROOT / "fixtures" / "scenarios" / f"{summary['fixture_id']}.json").read_text())
        fields = fixture["case_state"]["fields"]
        assert summary["expected_route"] == fixture["expected"]["route"]
        assert summary["expected_priority"] == fixture["expected"]["priority"]
        assert summary["expected_system"] == fixture["expected"]["system"]
        assert summary["location"] == fields["location"]
        assert summary["people_count"] == fields["people_count"]
        household = building["household"]
        assert household["location_label"] == fields["location"]
        assert household["people_count"] == fields["people_count"]


def test_twenty_calls_link_fixtures_to_buildings():
    town = _load("town.json")
    index = json.loads((ROOT / "fixtures" / "index.json").read_text(encoding="utf-8"))
    expected_ids = [row["id"] for row in index["scenarios"]]
    assert [call["id"] for call in town["calls"]] == expected_ids
    assert len(town["calls"]) == 20
    buildings = {building["id"]: building for building in town["buildings"]}
    priorities = set()
    for call in town["calls"]:
        assert call["building_id"] in buildings
        fixture = json.loads((ROOT / "fixtures" / "scenarios" / f"{call['id']}.json").read_text(encoding="utf-8"))
        opening = next(turn["text"] for turn in fixture["transcript_stream"] if turn["speaker"] == "caller")
        assert call["opening"] == opening
        assert call["expected_priority"] == fixture["expected"]["priority"]
        assert call["expected_route"] == fixture["expected"]["route"]
        priorities.add(call["expected_priority"])
    assert priorities == {"P1", "P2", "P3", "P4"}
    page = (ROOT / "ui" / "sim" / "index.html").read_text(encoding="utf-8")
    assert 'id="calls-play"' in page
    assert "Mubit" in page


def test_renderer_is_pixi_and_vendored():
    page = (ROOT / "ui" / "sim" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "ui" / "sim" / "sim.js").read_text(encoding="utf-8")
    assert 'src="sim.js"' in page
    assert "vendor/pixi.min.mjs" in source
    assert "new Application" in source
    bundle = ROOT / "ui" / "sim" / "vendor" / "pixi.min.mjs"
    assert bundle.stat().st_size > 100_000
    assert "as Application" in bundle.read_text(encoding="utf-8")


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def test_town_files_do_not_look_like_personal_data():
    for name in ("town.json", "streets.json", "flood.json"):
        body = _load(name)
        for text in _strings(body):
            assert PHONE.search(text) is None, text
            assert NATIONAL_ID.search(text) is None, text
            assert "promptpay" not in text.lower()
