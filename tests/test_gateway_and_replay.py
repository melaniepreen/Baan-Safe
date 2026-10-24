from contracts.models import RouterDecision
from eval.replay import replay
from fixtures.load import all_ids, load_case, load_fixture
from gateway.route import handle
from mocks.loader import load_s1_stub, load_s2_stub
import pytest
from router.merge import merge
from system1.decide import decide as decide1
from system2.decide import decide as decide2


def test_stub_gateway_matches_expected_labels():
    for fixture_id in ("F01", "F10", "C01-b"):
        case = load_case(fixture_id)
        decision = handle(case, use_stubs=True)
        expected = load_fixture(fixture_id)["expected"]
        assert isinstance(decision, RouterDecision)
        assert decision.final_priority.value == expected["priority"]
        assert decision.final_route.value == expected["route"]
        assert len(decision.source_outcomes) == 1
        assert decision.source_outcomes[0].system.value == expected["system"]
        assert case.memory_context == [] or decision.policy_notes


def test_graduation_fixture_routes_to_system_2():
    # G01 is labelled system_1 ("after graduation"), but rescue is a
    # needs_any trigger, so the field precheck sends it to System 2 whatever
    # correction_loop.graduation_threshold is. mocks/s2_stub/G01.json answers.
    decision = handle(load_case("G01"), use_stubs=True)
    assert len(decision.source_outcomes) == 1
    assert decision.source_outcomes[0].system.value == "system_2"


def test_correction_memory_is_visible_on_decision():
    case = load_case("C01-b")
    decision = handle(case, use_stubs=True)
    assert any("correction" in note for note in decision.policy_notes)


def test_real_interfaces_raise():
    case = load_case("F01")
    assert decide1(case).system.value == "system_1"
    assert merge(case, decide1(case)).case_id == "F01"
    # The decisions are set, so a real System 2 call reaches the Mubit
    # client, which refuses before any socket: the key is unset in tests.
    with pytest.raises(RuntimeError, match="MUBIT_API_KEY is not set"):
        decide2(case)
    with pytest.raises(RuntimeError, match="MUBIT_API_KEY is not set"):
        handle(load_case("F10"), use_stubs=False)


def test_replay_stubs_are_accurate():
    s1_ids = [fid for fid in all_ids() if load_fixture(fid)["expected"]["system"] == "system_1"]
    s2_ids = [fid for fid in all_ids() if load_fixture(fid)["expected"]["system"] == "system_2"]
    s1 = replay(lambda case: load_s1_stub(case.case_id), s1_ids)
    s2 = replay(lambda case: load_s2_stub(case.case_id), s2_ids)
    assert s1["priority_accuracy"] == 1
    assert s1["route_accuracy"] == 1
    assert s1["system_accuracy"] == 1
    assert s2["priority_accuracy"] == 1
    assert s2["route_accuracy"] == 1
    assert s2["system_accuracy"] == 1
