"""Recorded public-data snapshots. These tests send no network request."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from contracts.models import ExtractedFields, Need, TranscriptTurn
from enrich.context import within_flood_buffer
from fixtures.load import load_case
from gateway.route import handle
from ingest import demo_sources
from ingest.snapshots import SNAPSHOT_DIR, read_snapshot
from mocks.loader import load_dispatch_resources, load_resources, load_s1_stub
from shapely.geometry import Polygon
from system1.extract import extract

PHONE = re.compile(r"(?:\+66|0)[\s-]?\d[\d\s-]{7,}")
NATIONAL_ID = re.compile(r"\b\d{13}\b")
NAME_KEYS = {"name", "name_th", "name_en", "district", "province", "province_en", "province_th"}


def _names(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in NAME_KEYS and isinstance(item, str):
                yield item
            else:
                yield from _names(item)
    elif isinstance(value, list):
        for item in value:
            yield from _names(item)


def test_snapshots_keep_public_names_only():
    assert SNAPSHOT_DIR.is_dir()
    for path in SNAPSHOT_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert "awsaccesskeyid" not in text
        assert "api_key=" not in text
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name in _names(payload):
            assert PHONE.search(name) is None, name
            assert NATIONAL_ID.search(name) is None, name


def test_gazetteer_matches_thai_and_english_mae_mo():
    payload = read_snapshot("gazetteer")
    assert payload and len(payload["districts"]) > 800
    mae = [row for row in payload["districts"] if row["name_en"] == "Mae Mo" and row["province_en"] == "Lampang"]
    assert mae and mae[0]["name_th"] == "แม่เมาะ"
    thai = extract([TranscriptTurn(t_ms=0, speaker="caller", text="We are in อำเภอแม่เมาะ and the rice is finished.")])
    assert thai[0].location == "Mae Mo District, Lampang Province"
    assert thai[0].location_confidence == 0.85
    english = extract([TranscriptTurn(t_ms=0, speaker="caller", text="Mae Mo District, we need rice.")])
    assert english[0].location == "Mae Mo District, Lampang Province"
    song = extract([TranscriptTurn(t_ms=0, speaker="caller", text="Song District, four people.")])
    assert song[0].location == "Song District, Phrae Province"
    assert song[0].location_confidence == 0.85


def test_buffer_is_metres_and_does_not_change_priority(monkeypatch):
    lat, lon = 18.0, 99.0
    # About 220 m north of the point.
    polygon = Polygon(
        [
            (lon - 0.01, lat + 0.002),
            (lon + 0.01, lat + 0.002),
            (lon + 0.01, lat + 0.01),
            (lon - 0.01, lat + 0.01),
        ]
    )
    near, metres = within_flood_buffer(lat, lon, [polygon], 500)
    assert near is True
    assert metres is not None and metres < 500
    far, _distance = within_flood_buffer(lat, lon, [polygon], 50)
    assert far is False

    def fake(*_args, **_kwargs):
        return {
            "near_flood_extent": True,
            "rainfall_forecast_24h_mm": 40,
            "rainfall_last_24h_mm": 35,
        }

    monkeypatch.setattr("gateway.route.location_context", fake)
    case = load_case("F01")
    decision = handle(case, use_stubs=True)
    assert decision.final_priority == load_s1_stub("F01").priority
    assert "near_flood_extent" in case.policy_flags
    assert "heavy_rain_forecast" in case.policy_flags
    assert "heavy_rain_observed" in case.policy_flags


def test_dispatch_snapshot_prefers_a_public_shelter():
    fictional = load_resources()
    assert fictional.shelters[0].id == "shelter-fictional-01"
    snapshot = load_dispatch_resources()
    assert any(unit.kind == "shelter" and unit.id.startswith("shelter-") and unit.id != "shelter-fictional-01" for unit in snapshot.shelters)
    assert any(unit.kind == "ambulance" and "โรงพยาบาล" in unit.name for unit in snapshot.ambulances)
    from contracts.models import CaseState, Outcome, Priority, Route, System
    from router.merge import merge

    case = CaseState(
        case_id="live-shelter",
        caller_id_hash="synthetic:live-shelter",
        transcript=[],
        fields=ExtractedFields(
            location="Mueang Lampang District, Lampang Province",
            location_confidence=0.9,
            people_count=2,
            needs=[Need.shelter],
        ),
        received_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
    )
    outcome = Outcome(
        system=System.system_1,
        outcome="fast_route",
        priority=Priority.P3,
        needs=[Need.shelter],
        route=Route.shelter_placement,
        confidence=0.9,
        reason="test outcome",
        requires_human=False,
        escalate=False,
        latency_ms=1,
    )
    decision = merge(case, outcome, resources=snapshot)
    chosen = decision.dispatches[0]
    assert chosen.resource_kind == "shelter"
    assert chosen.same_district is True
    assert chosen.resource_id != "shelter-fictional-01"
    assert decision.final_priority == Priority.P3


def test_offline_loader_does_not_call_the_network(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(demo_sources, "_fetch_places", boom)
    monkeypatch.setattr(demo_sources, "_fetch_open_meteo", boom)
    monkeypatch.setattr(demo_sources, "_fetch_gazetteer", boom)
    payload, origin = demo_sources.load_places(refresh=False)
    assert origin == "snapshot"
    assert payload["places"]
    kinds = {row["kind"] for row in payload["places"]}
    assert {"hospital", "school", "temple", "fire_station", "ferry_terminal"} <= kinds
    failed, how = demo_sources.load_places(refresh=True)
    assert how.startswith("snapshot")
    assert failed["places"]
    report = demo_sources.status_report()
    assert "gistda_open_api: blocked" in report
    assert "tmd: failed" in report
    assert "open_meteo: ok" in report
    assert "hdx_cod_ab: ok" in report
