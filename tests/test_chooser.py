"""The field precheck routes fixtures the same way as their labels."""

from __future__ import annotations

from fixtures.load import load_case, load_fixture
from gateway.chooser import choose
from contracts.models import System

SCENARIO_IDS = [f"F{n:02d}" for n in range(1, 19)] + ["C01-a", "C01-b"]


def test_chooser_agrees_with_expected_system():
    for fixture_id in SCENARIO_IDS:
        case = load_case(fixture_id)
        system, triggers = choose(case)
        expected = load_fixture(fixture_id)["expected"]["system"]
        assert system.value == expected, fixture_id
        if expected == "system_2":
            assert triggers, fixture_id
        else:
            assert triggers == [], fixture_id


def test_graduation_fixtures_route_to_system_2():
    """G01–G04 are labelled system_1 for after graduation. rescue is a
    needs_any trigger, so the precheck sends them to System 2 until
    correction_loop.graduation_threshold is set."""
    for fixture_id in ("G01", "G02", "G03", "G04"):
        system, triggers = choose(load_case(fixture_id))
        assert system is System.system_2
        assert "need:rescue" in triggers


def test_non_fixture_ids_route_by_the_precheck():
    case = load_case("F01")
    case.case_id = "live-case-1"
    system, triggers = choose(case)
    assert system is System.system_1
    assert triggers == []

    case = load_case("F10")
    case.case_id = "live-case-2"
    system, triggers = choose(case)
    assert system is System.system_2
    assert "medical" in triggers
    assert "vulnerable:oxygen_dependent" in triggers
    assert "need:rescue" in triggers


def test_empty_fields_route_to_system_2():
    case = load_case("F01")
    case.case_id = "live-case-3"
    case.fields = case.fields.model_copy(update={"location": None, "location_confidence": None})
    system, triggers = choose(case)
    assert system is System.system_2
    assert "location_missing" in triggers
