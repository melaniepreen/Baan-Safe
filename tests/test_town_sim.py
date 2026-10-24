"""The town simulation stays inside the v0.2 contracts and its own data files."""

from __future__ import annotations

import json
import re
import subprocess

from contracts.models import Hazard, Household, Need, Resource, Route
from paths import ROOT

SIM = ROOT / "ui" / "sim" / "data"
PHONE = re.compile(r"(?:\+66|0)[\s-]?\d[\d\s-]{7,}")
NATIONAL_ID = re.compile(r"\b\d{13}\b")
STATUSES = {"clear", "at_risk", "flooded", "needs_help", "evacuated"}


def _load(name: str) -> dict:
    return json.loads((SIM / name).read_text(encoding="utf-8"))


ROMAN_STREETS = {
    "thanon-chamlong-nam-thuam": "Thanon Sukhumvit",
    "soi-chamlong-bon": "Thanon Phetchaburi Tat Mai",
    "soi-chamlong-lang": "Thanon At Narong",
    "soi-chamlong-khlong": "Soi Sukhumvit 39",
    "soi-chamlong-wat-fa": "Soi Sukhumvit 49",
    "soi-chamlong-talat": "Soi Sukhumvit 55",
    "soi-chamlong-ho-nuea": "Soi Sukhumvit 40",
    "soi-chamlong-fai": "Soi Sukhumvit 63",
    "khlong-chamlong": "Khlong Saen Saep",
}
SOUTH_SOIS = {
    "soi-chamlong-khlong": "Soi Sukhumvit 24",
    "soi-chamlong-wat-fa": "Soi Sukhumvit 36",
    "soi-chamlong-talat": "Soi Sukhumvit 38",
    "soi-chamlong-fai": "Soi Sukhumvit 42",
}
LANDMARKS = {
    "bldg-school": "School",
    "bldg-tower-white": "White apartment block",
    "bldg-tower-pink": "Pink apartment block",
    "bldg-shelter": "Evacuation shelter",
    "bldg-clinic": "Clinic",
    "bldg-welfare": "Water desk",
    "bldg-jetty": "Jetty",
    "bldg-temple": "Wat That Thong",
    "bldg-sala": "Sala",
    "bldg-stupa": "Chedi",
}
THAI_SCRIPT = re.compile(r"[\u0e00-\u0e7f]")
SOI_NUMBER = re.compile(r"Soi Sukhumvit (\d+)")
BANNED_COPY = re.compile(r"fictional|placeholder|demo street|\bsample\b", re.IGNORECASE)
RESOURCE_ID = re.compile(r"^(?:boat|amb|shelter|welfare)-fictional-01$")


def test_sukhumvit_streets_use_real_romanised_names():
    body = _load("streets.json")
    assert body["streets"]
    assert BANNED_COPY.search(body["note"]) is None
    seen = set()
    sukhumvit = next(street for street in body["streets"] if street["id"] == "thanon-chamlong-nam-thuam")
    for street in body["streets"]:
        assert "placeholder" not in street
        assert street["name_th"] == street["name_en"] == ROMAN_STREETS[street["id"]]
        assert THAI_SCRIPT.search(street["name_th"]) is None
        assert len(street["points"]) >= 2
        seen.add(street["id"])
        for label in street.get("labels") or []:
            assert label["name_th"] == label["name_en"]
            assert THAI_SCRIPT.search(label["name_en"]) is None
        if street["id"] in SOUTH_SOIS:
            north, south = street["labels"]
            assert north["name_en"] == street["name_en"]
            assert south["name_en"] == SOUTH_SOIS[street["id"]]
            assert north["t"] < 0.5 < south["t"]
            assert int(SOI_NUMBER.search(north["name_en"]).group(1)) % 2 == 1
            assert int(SOI_NUMBER.search(south["name_en"]).group(1)) % 2 == 0
            assert street["axis"] == "v"
            assert street["start"] < sukhumvit["fixed"] < street["end"]
    assert seen == set(ROMAN_STREETS)
    north_road = next(street for street in body["streets"] if street["id"] == "soi-chamlong-bon")
    south_road = next(street for street in body["streets"] if street["id"] == "soi-chamlong-lang")
    assert north_road["fixed"] < sukhumvit["fixed"] < south_road["fixed"]
    ho = next(street for street in body["streets"] if street["id"] == "soi-chamlong-ho-nuea")
    assert ho["start"] == sukhumvit["fixed"]
    assert int(SOI_NUMBER.search(ho["name_en"]).group(1)) % 2 == 0


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
    assert "placeholder" not in flood["properties"]
    assert flood["properties"]["live_layer"].startswith("/map/flood")
    depths = {feature["properties"]["hazard_id"]: feature["properties"]["depth_m"] for feature in flood["features"]}
    assert depths["haz-flood-canal"] > depths["haz-flood-south-deep"] > depths["haz-flood-streets"]
    for feature in flood["features"]:
        assert feature["properties"]["location_label"] == "Sukhumvit, Watthana"
        assert "placeholder" not in feature["properties"]
        assert BANNED_COPY.search(feature["properties"]["summary"]) is None
    town_names = {row["hazard_id"]: row["summary"] for row in town["hazards"]}
    flood_names = {feature["properties"]["hazard_id"]: feature["properties"]["summary"] for feature in flood["features"]}
    assert town_names == flood_names
    page = (ROOT / "ui" / "sim" / "index.html").read_text(encoding="utf-8")
    assert "Flooded" in page
    source = (ROOT / "ui" / "sim" / "sim.js").read_text(encoding="utf-8")
    assert "0x3a5854" in source
    assert "drawFloodRipple" in source
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
    assert "Mubit" not in page
    assert 'id="mubit-node"' not in page
    assert "link-to-mubit" not in page
    assert 'id="town-reset"' in page
    assert 'id="dispatch-reset"' in page
    assert 'alt="Baan-Safe"' in page
    assert "baansafe-logo.png" in page
    assert 'id="phone"' in page
    assert 'id="phone-record"' in page
    assert 'id="backend"' in page
    assert 'id="flow"' in page
    assert 'id="inspector"' not in page
    assert 'id="priority-actions"' not in page
    assert 'id="op-accept"' in page
    assert 'id="op-reject"' in page
    assert 'id="prompt-drawer"' in page
    assert "flood-opacity" not in page
    assert 'id="side-stack"' in page
    assert page.index('id="side-stack"') < page.index('class="block-map"') < page.index('id="backend"')
    assert 'id="log-export"' not in page
    assert "Export JSON" not in page
    assert 'id="pattern-list"' in page
    assert 'id="pattern-reset"' in page
    assert 'id="priority-badge"' in page
    source = (ROOT / "ui" / "sim" / "sim.js").read_text(encoding="utf-8")
    assert "DEMO-ONLY" in source
    assert "gateway.route_chooser" in source
    assert "Web Speech API" in source
    assert "/stt/transcribe" in source
    assert "attachLiveFeed" in source
    assert "sim_events.json" in source
    assert "replies.json" in source
    assert "patterns.js" in source
    assert "Scripted reply, not a live operator." in source
    assert "log-export" not in source
    assert "operatorLine" not in source
    assert "right: narrow ? 16 : 344" in source
    assert "Mubit" in source
    assert "paintWat" in source
    assert "paintStilt" in source
    assert "outlineBuilding" in source
    assert "drawBoatSprite" in source


def _inside(building: dict, x: float, y: float) -> bool:
    return building["x"] + 0.15 < x < building["x"] + building["w"] - 0.15 and building["y"] + 0.15 < y < building["y"] + building["d"] - 0.15


def test_response_routes_stay_on_drawn_links():
    town = _load("town.json")
    nodes = {node["id"]: node for node in town["graph"]["nodes"]}
    edges = town["graph"]["edges"]
    calls = {call["id"]: call for call in town["calls"]}
    found = {(route["call_id"], route["role"]) for route in town["response_routes"]}
    for call_id in calls:
        assert {(call_id, role) for role in ("rescue", "evac", "welfare", "notice")} <= found
    for route in town["response_routes"]:
        assert Route(route["contract_route"])
        assert route["building_id"] == calls[route["call_id"]]["building_id"]
        assert route["legs"]
        for leg in route["legs"]:
            assert leg["mode"] in {"foot", "boat", "road"}
            nodes_on_leg = leg["node_ids"]
            assert nodes_on_leg
            for left, right in zip(nodes_on_leg, nodes_on_leg[1:]):
                assert any(
                    leg["mode"] in edge["modes"] and {edge["from"], edge["to"]} == {left, right}
                    for edge in edges
                ), route["id"]
    for edge in edges:
        if not edge.get("lane"):
            continue
        a, b = nodes[edge["from"]], nodes[edge["to"]]
        steps = max(3, int(edge["length_m"] / 1.5))
        for step in range(steps + 1):
            t = step / steps
            x = a["x"] + (b["x"] - a["x"]) * t
            y = a["y"] + (b["y"] - a["y"]) * t
            for building in town["buildings"]:
                assert not _inside(building, x, y), (edge["id"], building["id"])
    rescue = next(route for route in town["response_routes"] if route["call_id"] == "F10" and route["role"] == "rescue")
    assert any(leg["mode"] == "boat" for leg in rescue["legs"])
    welfare = next(route for route in town["response_routes"] if route["call_id"] == "F02" and route["role"] == "welfare")
    assert any(leg["mode"] == "foot" for leg in welfare["legs"])


def test_response_copy_separates_policy_from_suggestion():
    body = _load("responses.json")
    assert body["policy_source"] == "config/priorities.yaml"
    assert "not repo policy" in body["suggestion_label"].lower() or "not repo policy" in body["suggestion_label"]
    assert body["suggestion_source"] == "research/thai-flood-management.md"
    blob = json.dumps(body).lower()
    assert "baht" not in blob
    assert "฿" not in blob
    for priority in ("P1", "P2", "P3", "P4"):
        row = body["priorities"][priority]
        assert row["policy"]
        assert row["suggestion"]
        assert row["policy"] != row["suggestion"]
    decisions = (ROOT / "config" / "decisions.yaml").read_text(encoding="utf-8")
    assert "route_chooser: field precheck" in decisions
    assert "sapling_scope: aid_eligibility,denial" in decisions


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


def test_activity_prompts_and_rulebook_are_draft_simulations():
    events = _load("sim_events.json")
    prompts = _load("prompts.json")
    rules = _load("rulebook.json")
    assert events["schema_version"] == "baansafe.sim_activity.v1"
    assert events["simulated"] is True
    assert events["confidence_threshold"] == 0.75
    assert "attachLiveFeed" in events["stream"]["how"]
    town = _load("town.json")
    call_ids = {call["id"] for call in town["calls"]}
    assert set(events["scenarios"]) == call_ids
    for fixture_id, scenario in events["scenarios"].items():
        assert abs(sum(scenario["scores"].values()) - 1) < 0.02
        assert abs(sum(scenario["needs"].values()) - 1) < 0.02
        assert scenario["steps"][0]["source"] == "simulated"
        kinds = {step["kind"] for step in scenario["steps"]}
        assert {"memory", "tool", "system_1", "router"} <= kinds
        theme = scenario["theme"]
        assert theme["id"] and theme["label"]
        assert isinstance(theme["learns"], bool)
        assert isinstance(theme["life_safety"], bool)
    assert events["learning"]["promote_after"] == 3
    assert events["learning"]["simulated"] is True
    water = events["scenarios"]["F01"]["theme"]["id"]
    assert water == events["scenarios"]["F08"]["theme"]["id"] == events["scenarios"]["F09"]["theme"]["id"]
    assert events["scenarios"]["F14"]["theme"]["id"] == "says-fine"
    assert events["scenarios"]["F14"]["theme"]["life_safety"] is False
    for fixture_id in ("F10", "F11", "F16", "C01-a", "C01-b"):
        assert events["scenarios"][fixture_id]["theme"]["life_safety"] is True
    assert events["scenarios"]["F17"]["theme"]["learns"] is False
    assert events["scenarios"]["F18"]["theme"]["learns"] is False
    etas = {rule["id"]: rule.get("eta_min") for rule in rules["rules"]}
    assert etas["p1-medical"] == 12
    assert etas["p1-rescue"] == 10
    assert etas["p2-evac"] == 15
    assert etas["p3-welfare"] == 20
    groups = {group["id"]: group["prompts"] for group in prompts["groups"]}
    assert set(groups) == {"system_1", "system_2", "sapling"}
    for rows in groups.values():
        assert len(rows) >= 4
        for prompt in rows:
            assert prompt["fixture_id"] in call_ids
            assert prompt["en"]
    assert rules["draft"] is True
    assert "not repo policy" in rules["label"].lower()
    vehicles = {rule["vehicle"] for rule in rules["rules"]}
    assert {"boat", "truck", "van", "pulse", "none"} <= vehicles
    actions = " ".join(rule["action"] for rule in rules["rules"]).lower()
    assert "truck" not in actions
    assert "van" not in actions
    assert "evacuation boat" in actions
    assert "supply boat" in actions
    blob = json.dumps({"events": events, "prompts": prompts, "rules": rules}).lower()
    assert "baht" not in blob
    assert "฿" not in blob
    subprocess.run(["node", "ui/sim/check_hospital.mjs"], cwd=ROOT, check=True)
    subprocess.run(["node", "ui/sim/check_patterns.mjs"], cwd=ROOT, check=True)


def test_scripted_replies_stay_in_human_language():
    replies = _load("replies.json")
    assert replies["simulated"] is True
    templates = replies["templates"]
    assert templates[0]["id"] == "aid"
    assert any(row["id"] == "boat-medical" for row in templates)
    spoken = "\n".join(row["en"] + "\n" + row.get("th", "") for row in templates)
    assert "Help is on the way. A rescue boat is leaving the jetty now" in spoken
    lowered = spoken.lower()
    assert "truck" not in lowered
    assert "van" not in lowered
    assert "supply boat" in lowered
    assert "evacuation boat" in lowered
    assert "baht" not in lowered
    assert "฿" not in spoken
    for banned in (
        "create_provisional",
        "rescue_coordination",
        "welfare_distribution",
        "aid_caseworker",
        "ask_next_question",
        "escalate_to_supervisor",
    ):
        assert banned not in lowered
    assert re.search(r"\bP[1-4]\b", spoken) is None
    for text in _strings({"spoken": spoken}):
        assert PHONE.search(text) is None, text
        assert NATIONAL_ID.search(text) is None, text


def test_raised_houses_are_mixed_through_the_block():
    town = _load("town.json")
    houses = [building for building in town["buildings"] if building["kind"] in {"house", "stilt", "wood_house"}]
    raised = [building for building in houses if building["kind"] in {"stilt", "wood_house"}]
    assert houses
    assert 1 / 3 <= len(raised) / len(houses) <= 0.5
    variants = {building.get("stilt") for building in town["buildings"] if building["kind"] == "stilt"}
    assert variants == {"teak", "dark", "amber"}
    for building in town["buildings"]:
        if building["kind"] != "stilt":
            continue
        assert building["roof"] == "brown"
        assert building["wall"] == "wood"
        assert not building.get("landmark")


def test_town_copy_uses_sukhumvit_names_and_logo_colours():
    town = _load("town.json")
    by_id = {building["id"]: building for building in town["buildings"]}
    for building_id, label in LANDMARKS.items():
        building = by_id[building_id]
        assert building["name_th"] == building["name_en"] == label
        assert THAI_SCRIPT.search(label) is None
    names = {row["resource_id"]: row["name"] for row in town["resources"]}
    assert names["boat-fictional-01"] == "Rescue boat"
    assert names["amb-fictional-01"] == "Clinic ambulance"
    assert names["shelter-fictional-01"] == "Evacuation shelter"
    assert names["welfare-fictional-01"] == "Water desk"
    labels = {route["id"]: route["label"] for route in town["routes"]}
    assert labels["route-f06-evac"] == "F06 walk to the evacuation shelter"
    assert labels["route-f10-rescue"] == "F10 boat from the jetty"
    visible = []
    for name in ("town.json", "streets.json", "flood.json", "responses.json", "prompts.json", "rulebook.json", "replies.json"):
        for text in _strings(_load(name)):
            if RESOURCE_ID.fullmatch(text):
                continue
            visible.append(text)
    readme = (ROOT / "ui" / "sim" / "README.md").read_text(encoding="utf-8")
    page = (ROOT / "ui" / "sim" / "index.html").read_text(encoding="utf-8")
    page = page.replace('placeholder="Message"', "")
    source = (ROOT / "ui" / "sim" / "sim.js").read_text(encoding="utf-8")
    for text in visible + [readme, page, source]:
        assert BANNED_COPY.search(text) is None, text
    css = (ROOT / "ui" / "sim" / "sim.css").read_text(encoding="utf-8")
    for colour in ("#ED7401", "#0076D8", "#014855", "#012246", "#0b1220", "#e6edf5", "#9aa8bb", "#d1241a"):
        assert colour in css
    assert ".bubble.caller { margin-left: auto; background: #0076D8;" in css
    assert ".bubble.operator { margin-right: auto; background: #014855;" in css
    assert "#side-stack #op-reject { background: #d1241a;" in css


def test_town_files_do_not_look_like_personal_data():
    for name in ("town.json", "streets.json", "flood.json", "responses.json", "sim_events.json", "prompts.json", "rulebook.json", "replies.json"):
        body = _load(name)
        for text in _strings(body):
            assert PHONE.search(text) is None, text
            assert NATIONAL_ID.search(text) is None, text
            assert "promptpay" not in text.lower()
