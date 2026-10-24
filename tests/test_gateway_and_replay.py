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
    for fixture_id in ("F01", "F10", "C01-b", "G01"):
        case = load_case(fixture_id)
        decision = handle(case, use_stubs=True)
        expected = load_fixture(fixture_id)["expected"]
        assert isinstance(decision, RouterDecision)
        assert decision.final_priority.value == expected["priority"]
        assert decision.final_route.value == expected["route"]
        assert len(decision.source_outcomes) == 1
        assert decision.source_outcomes[0].system.value == expected["system"]
        assert case.memory_context == [] or decision.policy_notes


def test_correction_memory_is_visible_on_decision():
    case = load_case("C01-b")
    decision = handle(case, use_stubs=True)
    assert any("correction" in note for note in decision.policy_notes)


def test_real_interfaces_raise():
    case = load_case("F01")
    with pytest.raises(NotImplementedError, match="Moly"):
        decide1(case)
    with pytest.raises(NotImplementedError, match="Melanie"):
        decide2(case)
    with pytest.raises(NotImplementedError, match="Moly"):
        merge([], [])
    with pytest.raises(NotImplementedError, match="Moly"):
        handle(case, use_stubs=False)


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
