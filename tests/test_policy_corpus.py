"""Policy corpus and the Sapling adapter. Stubs only. No GPU."""

import re

import pytest

from config.settings import DecisionRequired
from contracts.models import MemoryItem, Need, Outcome, Priority, Route, System
from fixtures.load import load_case
from policies.corpus import corpus_counts, get_rule, load_labels, load_rules
from system2.sapling import verify_before_router
from system2.sapling_client import MAX_INPUT_TOKENS, estimate_tokens, verify
from system2.sapling_policy import (
    build_sapling_input,
    policy_text_for_case,
    require_authoritative_ids,
)

UNVERIFIED = {
    "MOF-2568-REGULATION-TEXT",
    "MOF-2569-TEMP-SHELTER-CAP",
    "MOF-2569-TOILET-BLOCK-COST",
    "MOF-2569-PM25",
    "CBD-RESPONSE-MINUTES",
    "FLOOD-BOAT-ORDER",
}
BANNED_HOSTS = ("reliefweb.int", "disaster.go.th", "ddpm.go.th")
AMOUNT = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:baht|litres|minutes|cm)\b", re.I)


def _aid_outcome() -> Outcome:
    return Outcome(
        system=System.system_2,
        outcome="reasoned_recommendation",
        priority=Priority.P3,
        needs=[Need.aid_payment],
        route=Route.aid_caseworker,
        confidence=0.4,
        reason="Synthetic household H-204 is eligible for a flood assistance review.",
        reasoning="Nemotron proposed the eligibility review.",
        requires_human=False,
        escalate=False,
        latency_ms=4,
    )


def test_corpus_counts_and_keeps_placeholders_unverified():
    counts = corpus_counts()
    rules = load_rules()
    assert counts["rules"] == len(rules)
    assert counts["verified"] + counts["unverified"] == counts["rules"]
    assert set(rule_id for rule_id, rule in rules.items() if not rule.verified) == UNVERIFIED
    assert counts["verified"] > counts["unverified"]
    for rule in rules.values():
        assert rule.retrieved == "2026-10-24"
        assert rule.license_note
        assert rule.source_excerpt
        lowered = rule.source_url.lower()
        for host in BANNED_HOSTS:
            assert host not in lowered
        if rule.verified:
            assert rule.source_url.startswith("https://")
            assert "TODO_HUMAN" not in rule.text_en
        else:
            assert "TODO_HUMAN" in rule.text_en
            assert AMOUNT.search(rule.text_en) is None
            assert AMOUNT.search(rule.text_th) is None


def test_verified_meal_cap_is_the_printed_figure():
    rule = get_rule("MOF-2569-FOOD")
    assert rule.verified
    assert "๘๐" in rule.source_excerpt
    assert "80" in rule.text_en
    assert "ceiling" in rule.text_en
    assert "๑,๐๐๐" not in rule.source_excerpt


def test_unverified_shelter_cap_does_not_pick_a_number():
    rule = get_rule("MOF-2569-TEMP-SHELTER-CAP")
    blob = rule.text_en + rule.source_excerpt
    assert "3,000" not in blob
    assert "31,000" not in blob
    assert "3000" not in blob
    assert "31000" not in blob


def test_unknown_rule_is_refused():
    with pytest.raises(ValueError, match="Unknown policy rule"):
        get_rule("MOF-2569-NOT-A-RULE")


def test_flood_rules_quote_their_own_depths_and_do_not_assign_a_colour():
    depth = get_rule("FLOOD-WATER-DEPTH")
    ready = get_rule("READY-FLOOD-DEPTH")
    agency = get_rule("EA-FLOOD-DEPTH")
    ifrc = get_rule("IFRC-FLOOD-DEPTH")
    trapped = get_rule("FLOOD-TRAPPED-DISPATCH")
    for rule in (depth, ready, agency, ifrc, trapped):
        assert rule.verified
    assert "does not map" in trapped.text_en
    assert "1669" in trapped.text_en
    assert "6 inches" in depth.source_excerpt
    assert "12 inches" in depth.source_excerpt
    assert "18 inches" in depth.source_excerpt
    assert "one foot" in ready.source_excerpt
    assert "60cm" in agency.source_excerpt
    assert "15 centimetres" in ifrc.source_excerpt
    assert "20 centimetres" in ifrc.source_excerpt
    assert "50 centimetres" in ifrc.source_excerpt
    assert "สีแดง" in trapped.source_excerpt
    assert "น้ำท่วม" not in trapped.source_excerpt
    boat = get_rule("FLOOD-BOAT-ORDER")
    assert not boat.verified
    assert "Team assumption" in boat.text_en
    assert "withdrawn" in boat.source_excerpt
    minutes = get_rule("CBD-RESPONSE-MINUTES")
    assert not minutes.verified
    assert "ทันที" in minutes.source_excerpt
    announcement = get_rule("NIEMS-ANNOUNCEMENT-2554")
    assert announcement.verified
    assert "ทันที" in announcement.text_th
    labels = load_labels()
    assert labels["flood_water_depth"].status == "verified"
    assert "FLOOD-WATER-DEPTH" in labels["flood_water_depth"].derived_from
    assert "EA-FLOOD-WARNINGS" in labels["flood_trapped"].derived_from
    assert "CDC-FLOOD-CHILDREN" in labels["safeguarding_child"].derived_from
    assert "READY-NOT-ALONE" in labels["safeguarding_older_person"].derived_from
    assert "READY-MEDICAL-NEEDS" in labels["safeguarding_disability"].derived_from
    assert "CDC-INSULIN-OUTAGE" in labels["safeguarding_serious_health"].derived_from
    assert labels["flood_water_depth"].thai_is_quotation is False
    assert labels["flood_trapped"].thai_is_quotation is False


def test_labels_are_bilingual_and_point_at_real_rules():
    labels = load_labels()
    assert "niems_red_critical" in labels
    assert "flood_water_depth" in labels
    rules = load_rules()
    for label in labels.values():
        assert label.hypothesis_en.strip()
        assert label.hypothesis_th.strip()
        assert label.label_en and label.label_th
        for rule_id in label.derived_from:
            assert rule_id in rules
        if label.status == "unverified":
            assert "TODO_HUMAN" in label.hypothesis_en
            assert AMOUNT.search(label.hypothesis_en) is None
        else:
            assert "TODO_HUMAN" not in label.hypothesis_en


def test_adapter_loads_a_rule_and_the_stub_does_not_call_a_model():
    built = build_sapling_input(
        ["MOF-2569-FOOD"],
        "Synthetic household H-204 reported a flooded kitchen.",
        "Synthetic household H-204 should be paid the meal ceiling automatically.",
    )
    assert built["included_rule_ids"] == ["MOF-2569-FOOD"]
    assert built["omitted_rule_ids"] == []
    assert "๘๐" in built["policy"] or "80" in built["policy"]
    assert built["estimated_tokens"] <= MAX_INPUT_TOKENS
    verdict = verify(built["policy"], built["evidence"], built["claim"], check="denial")
    assert verdict.stub is True
    assert verdict.verdict == "unsure"
    assert verdict.action == "human_handoff"


def test_adapter_drops_whole_rules_instead_of_cutting_them():
    evidence = "Synthetic household H-204 reported floodwater in the kitchen."
    claim = "The meal ceiling applies to synthetic household H-204."
    first = build_sapling_input(["MOF-2569-FOOD"], evidence, claim)
    # The omission line is short. The second rule is not. Keep the first body whole.
    both = build_sapling_input(
        ["MOF-2569-FOOD", "MOF-2569-HOUSE-REPAIR"],
        evidence,
        claim,
        max_tokens=first["estimated_tokens"] + 80,
    )
    assert both["included_rule_ids"] == ["MOF-2569-FOOD"]
    assert both["omitted_rule_ids"] == ["MOF-2569-HOUSE-REPAIR"]
    assert "88,600" not in both["policy"]
    assert "๘๘,๖๐๐" not in both["policy"]
    assert both["estimated_tokens"] <= first["estimated_tokens"] + 80
    food = get_rule("MOF-2569-FOOD")
    assert food.source_excerpt in both["policy"]


def test_evidence_over_the_checkpoint_limit_is_refused():
    with pytest.raises(ValueError, match="16384"):
        build_sapling_input(
            ["MOF-2569-FOOD"],
            "synthetic " * 40000,
            "A claim about synthetic household H-204.",
        )


def test_authoritative_set_stays_a_human_decision():
    with pytest.raises(DecisionRequired, match="policies.authoritative_set"):
        require_authoritative_ids()


def test_verifier_uses_the_corpus_only_when_the_case_names_a_rule():
    case = load_case("F17")
    outcome = _aid_outcome()
    assert policy_text_for_case(case, "Synthetic evidence.", "Synthetic claim.") is None
    untouched = verify_before_router(case, outcome)
    assert "MOF-2569-FOOD" not in (untouched.reasoning or "")
    named = case.model_copy(
        update={
            "policy_flags": ["MOF-2569-FOOD", "aid_denial"],
            "memory_context": [
                MemoryItem(
                    memory_id="mem-policy",
                    kind="policy",
                    summary="Also see MOF-2569-HOUSE-REPAIR for synthetic household H-204.",
                    relevance=0.5,
                )
            ],
        }
    )
    handed = verify_before_router(named, outcome)
    assert handed.requires_human is True
    assert "sapling_unsure" in handed.missing_evidence
    assert "sapling_check=denial" in (handed.reasoning or "")
    built = build_sapling_input(
        ["MOF-2569-FOOD", "MOF-2569-HOUSE-REPAIR"],
        "x",
        "y",
    )
    assert estimate_tokens(built["policy"], "x", "y") <= MAX_INPUT_TOKENS
