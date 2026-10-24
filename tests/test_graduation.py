"""Correction graduation: patterns graduate into System 2 only."""

from __future__ import annotations

from api.store import StoredCase, put
from contracts.training import (
    LEGACY_MODEL_VERSION,
    InputRef,
    S1Label,
    TrainingEvent,
    current_policy_version,
)
from fixtures.load import load_case
from gateway.graduation import apply, graduated_patterns
from gateway.route import handle, choose_system
from contracts.models import System
from training.log import append_event


def _event(case_id: str, label: S1Label = S1Label.safeguarding_child, source: str = "human") -> TrainingEvent:
    return TrainingEvent(
        task="s1_triage",
        group_id=case_id,
        input_ref=InputRef(case_id=case_id, lang="en"),
        output_model=S1Label.sphere_food_short,
        output_correct=label,
        reason="operator correction on a synthetic case",
        source=source,
        corrected_by="operator" if source == "human" else None,
        model_version=LEGACY_MODEL_VERSION,
        policy_version=current_policy_version(),
    )


def _twin(fixture_id: str, new_id: str) -> None:
    case = load_case(fixture_id).model_copy(update={"case_id": new_id})
    put(StoredCase(state=case, fixture_id=None))


def test_one_correction_does_not_graduate():
    append_event(_event("F02"))
    assert graduated_patterns() == []
    case = load_case("F02")
    assert choose_system(case) is System.system_1


def test_new_correction_refreshes_the_cached_result():
    _twin("F02", "TEST-F02-b")
    append_event(_event("F02"))
    assert graduated_patterns() == []
    append_event(_event("TEST-F02-b"))
    assert [g.count for g in graduated_patterns()] == [2]


def test_two_corrections_graduate_the_pattern():
    _twin("F02", "TEST-F02-b")
    append_event(_event("F02"))
    append_event(_event("TEST-F02-b"))
    case = load_case("F02")
    matches = apply(case)
    assert matches and matches[0].label == "safeguarding_child"
    assert matches[0].count == 2
    assert "complex_situation" in case.policy_flags
    item = next(m for m in case.memory_context if m.memory_id.startswith("graduated-"))
    assert item.kind == "correction"
    assert item.source_case_id == "F02"
    assert "sets no priority" in item.summary
    # Re-applying does not duplicate the recommendation.
    apply(case)
    assert sum(m.memory_id.startswith("graduated-") for m in case.memory_context) == 1


def test_graduated_case_routes_system_2_via_flag():
    _twin("F02", "TEST-F02-b")
    append_event(_event("F02"))
    append_event(_event("TEST-F02-b"))
    case = load_case("F02")
    decision = handle(case, use_stubs=True)
    assert "complex_situation" in case.policy_flags
    assert decision.source_outcomes[0].system.value == "system_2"
    # The fallback escalation's P2 is not a graduated priority.
    assert decision.source_outcomes[0].reason.startswith("No stub outcome")


def test_same_case_twice_does_not_graduate():
    append_event(_event("F02"))
    append_event(_event("F02", label=S1Label.safeguarding_older_person))
    assert graduated_patterns() == []


def test_non_human_sources_do_not_count():
    _twin("F02", "TEST-F02-b")
    append_event(_event("F02", source="coach"))
    append_event(_event("TEST-F02-b", source="sim"))
    assert graduated_patterns() == []


def test_routine_label_never_graduates():
    _twin("F02", "TEST-F02-b")
    append_event(_event("F02", label=S1Label.sphere_food_short))
    append_event(_event("TEST-F02-b", label=S1Label.sphere_food_short))
    assert graduated_patterns() == []


def test_other_pattern_is_unaffected():
    _twin("F02", "TEST-F02-b")
    append_event(_event("F02"))
    append_event(_event("TEST-F02-b"))
    case = load_case("F01")
    assert apply(case) == []
    assert "complex_situation" not in case.policy_flags


def test_demo_graduation_exits_zero():
    from eval.graduation_demo import main

    assert main() == 0
