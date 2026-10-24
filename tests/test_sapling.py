"""Sapling verifier: stub client, gate, and the live refusal. No GPU."""

import pytest

from config.settings import DecisionRequired
from contracts.models import Need, Outcome, Priority, Route, System
from eval.sapling_replay import replay_sapling_stubs
from fixtures.load import load_case
from infra.modal.common import UnsetDecision, resolve
from infra.modal.sapling_gpu import require_sapling_gpu
from infra.modal.vram import gpu_memory_gib, sapling_footprint
from mocks.loader import load_s1_stub, load_s2_stub
from system2.decide import decide
from system2.sapling import apply_verdict, detect_check, verify_before_router
from system2.sapling_client import make_verdict, verdict_from_model_output, verify


def _aid_outcome(**updates) -> Outcome:
    fields = dict(
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
    fields.update(updates)
    return Outcome(**fields)


def test_stub_replay_matches_every_verdict():
    report = replay_sapling_stubs()
    assert report["n"] == 5
    assert report["verdict_accuracy"] == 1
    assert report["action_accuracy"] == 1
    assert {row["id"] for row in report["rows"]} == {"S01", "S02", "S03", "S04", "S05"}
    assert all(row["stub"] for row in report["rows"])


def test_unknown_triple_is_unsure_and_not_supported():
    verdict = verify(
        "A synthetic policy with no stub row.",
        "Synthetic household H-204 asked for a review.",
        "Synthetic household H-204 is eligible for a flood assistance review.",
        check="aid_eligibility",
    )
    assert verdict.stub is True
    assert verdict.verdict == "unsure"
    assert verdict.action == "human_handoff"
    assert verdict.probabilities_are_calibrated is False
    assert verdict.probabilities["unsure"] == 1.0


def test_model_labels_map_onto_baansafe_verdicts():
    missing = verdict_from_model_output(
        {
            "status": "insufficient_information",
            "model": "banyan-sapling",
            "probabilities": {
                "supported": 0.05,
                "violation": 0.05,
                "insufficient_information": 0.8,
                "inconsistent_context": 0.1,
            },
        },
        check="aid_eligibility",
    )
    assert missing.verdict == "missing"
    assert missing.action == "human_handoff"
    assert missing.probabilities["missing"] == 0.8
    assert missing.probabilities_are_calibrated is True
    assert missing.stub is False
    contradicted = verdict_from_model_output(
        {
            "status": "inconsistent_context",
            "probabilities": {
                "supported": 0.0,
                "violation": 0.0,
                "insufficient_information": 0.25,
                "inconsistent_context": 0.75,
            },
        }
    )
    assert contradicted.verdict == "contradicted"
    assert contradicted.action == "human_handoff"
    unsure = verdict_from_model_output(
        {
            "status": "unsure",
            "probabilities": {
                "supported": 0.4,
                "violation": 0.4,
                "insufficient_information": 0.1,
                "inconsistent_context": 0.1,
            },
        }
    )
    assert unsure.verdict == "unsure"
    assert unsure.action == "human_handoff"
    assert unsure.probabilities["unsure"] == 0.0


def test_supported_lets_the_action_proceed_and_violation_blocks_it():
    proposed = _aid_outcome()
    supported = apply_verdict(
        proposed,
        make_verdict("supported", check="aid_eligibility", stub=True),
    )
    assert supported.requires_human is False
    assert supported.route is Route.aid_caseworker
    assert supported.reason == proposed.reason
    assert "sapling_action=proceed" in (supported.reasoning or "")
    blocked = apply_verdict(
        proposed,
        make_verdict("violation", check="denial", stub=True),
    )
    assert blocked.requires_human is True
    assert blocked.route is Route.supervisor_escalation
    assert blocked.reason.startswith("Sapling blocked this action.")


@pytest.mark.parametrize("verdict", ["unsure", "missing", "contradicted"])
def test_uncertain_verdicts_hand_off_to_a_human(verdict):
    handed = apply_verdict(
        _aid_outcome(),
        make_verdict(verdict, check="aid_eligibility", stub=True),
    )
    assert handed.requires_human is True
    assert handed.route is Route.aid_caseworker
    assert f"sapling_{verdict}" in handed.missing_evidence
    assert handed.reason.startswith("Sapling handed this to a human.")
    assert "sapling_action=human_handoff" in (handed.reasoning or "")


def test_system_1_fast_path_never_calls_sapling(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("Sapling ran on the fast path")

    monkeypatch.setattr("system2.sapling.verify", boom)
    case = load_case("F01")
    outcome = load_s1_stub("F01")
    assert verify_before_router(case, outcome) is outcome
    assert verify_before_router(case, outcome, check="aid_eligibility") is outcome
    aid_shaped = outcome.model_copy(
        update={"route": Route.aid_caseworker, "needs": [Need.aid_payment]}
    )
    assert detect_check(case, aid_shaped) is None
    assert verify_before_router(case, aid_shaped, check="denial") is aid_shaped


def test_system_2_medical_path_skips_sapling(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("Sapling ran on a non-aid outcome")

    monkeypatch.setattr("system2.sapling.verify", boom)
    case = load_case("F10")
    outcome = load_s2_stub("F10")
    assert detect_check(case, outcome) is None
    assert verify_before_router(case, outcome) is outcome


def test_aid_case_is_eligibility_and_a_denial_flag_is_a_denial():
    eligibility = load_case("F17")
    assert detect_check(eligibility, _aid_outcome()) == "aid_eligibility"
    denial = eligibility.model_copy(update={"policy_flags": ["aid_denial"]})
    assert detect_check(denial, _aid_outcome()) == "denial"


def test_verifier_runs_after_reasoning_and_before_the_router(monkeypatch):
    order = []

    def fake_orchestrate(case):
        del case
        order.append("reason")
        return _aid_outcome()

    def fake_verify(policy, evidence, claim, check=None, language="en"):
        del policy, evidence, claim, language
        order.append("sapling")
        return make_verdict("supported", check=check, stub=True)

    monkeypatch.setattr("system2.decide.orchestrate", fake_orchestrate)
    monkeypatch.setattr("system2.sapling.verify", fake_verify)
    outcome = decide(load_case("F17"))
    assert order == ["reason", "sapling"]
    assert "sapling_verdict=supported" in (outcome.reasoning or "")
    assert outcome.requires_human is False


def test_over_limit_input_is_refused_and_the_gate_hands_it_off():
    with pytest.raises(ValueError, match="16384"):
        verify("policy " * 20000, "evidence text", "a claim")
    with pytest.raises(ValueError, match="policy"):
        verify("  ", "evidence text", "a claim")
    case = load_case("F17")
    huge = case.model_copy(
        update={
            "transcript": [
                case.transcript[0].model_copy(update={"text": "synthetic " * 20000})
            ]
        }
    )
    handed = verify_before_router(huge, _aid_outcome())
    assert handed.requires_human is True
    assert "sapling_unsure" in handed.missing_evidence


def test_live_client_refuses_while_hosting_is_unset(monkeypatch):
    monkeypatch.setenv("SAPLING_IMPL", "live")
    monkeypatch.setenv("MUBIT_API_KEY", "mbt_should_not_appear")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    with pytest.raises(DecisionRequired, match="sapling.hosting") as caught:
        verify("A policy.", "Some evidence.", "A claim.", check="aid_eligibility")
    message = str(caught.value)
    assert "mbt_should_not_appear" not in message
    assert "api.mubit.ai" not in message


def test_thai_handling_is_not_guessed():
    with pytest.raises(DecisionRequired, match="sapling.thai_handling"):
        verify("A policy.", "Some evidence.", "A claim.", language="th")


def test_sapling_gpu_and_model_stay_unset(monkeypatch):
    monkeypatch.delenv("SAPLING_GPU", raising=False)
    monkeypatch.delenv("SAPLING_MODEL_ID", raising=False)
    with pytest.raises(UnsetDecision, match="TODO_HUMAN"):
        resolve("sapling.model_id", "SAPLING_MODEL_ID")
    with pytest.raises(UnsetDecision, match="TODO_HUMAN"):
        resolve("sapling.gpu", "SAPLING_GPU")


def test_sapling_gpu_accepts_l40s_and_refuses_smaller_or_a6000_on_modal():
    assert require_sapling_gpu("L40S") == "L40S"
    assert require_sapling_gpu("H200") == "H200"
    with pytest.raises(UnsetDecision, match="A6000"):
        require_sapling_gpu("A6000")
    with pytest.raises(UnsetDecision, match="48GB"):
        require_sapling_gpu("T4")
    with pytest.raises(UnsetDecision, match="48GB"):
        require_sapling_gpu("A100-40GB")
    assert gpu_memory_gib("A6000") is None


def test_sapling_bf16_footprint_fits_a_48gb_board_at_the_input_limit():
    row = sapling_footprint()
    assert row["weights"] == pytest.approx(42.92, abs=0.01)
    assert row["kv"] == pytest.approx(1.50, abs=0.01)
    assert row["total"] == pytest.approx(46.42, abs=0.01)
    assert 0 < row["slack_on_48"] < 4
    assert sapling_footprint(4096)["total"] > 16


def test_sapling_app_imports_when_a_human_exports_the_env(monkeypatch):
    pytest.importorskip("modal")
    monkeypatch.setenv("SAPLING_GPU", "L40S")
    monkeypatch.setenv("SAPLING_MODEL_ID", "MubitLabs/banyan-sapling")
    import sys

    sys.modules.pop("infra.modal.sapling_app", None)
    import infra.modal.sapling_app as app

    assert app.GPU == "L40S"
    assert app.MODEL_ID == "MubitLabs/banyan-sapling"
    sys.modules.pop("infra.modal.sapling_app", None)
