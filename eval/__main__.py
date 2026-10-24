"""Replay stub outcomes. `make replay-stubs`."""

from __future__ import annotations

import json

from contracts.models import CaseState, Outcome
from eval.replay import replay
from eval.sapling_replay import replay_sapling_stubs
from fixtures.load import all_ids, load_fixture
from mocks.loader import has_s2_stub, load_s1_stub, load_s2_stub


def _s1(case: CaseState) -> Outcome:
    return load_s1_stub(case.case_id)


def _s2(case: CaseState) -> Outcome:
    return load_s2_stub(case.case_id)


def main() -> int:
    s1_ids = []
    s2_ids = []
    for fixture_id in all_ids():
        expected = load_fixture(fixture_id)["expected"]["system"]
        if expected == "system_1":
            s1_ids.append(fixture_id)
        if expected == "system_2" and has_s2_stub(fixture_id):
            s2_ids.append(fixture_id)
    s1_report = replay(_s1, s1_ids)
    s2_report = replay(_s2, s2_ids)
    sapling_report = replay_sapling_stubs()
    payload = {
        "system_1_stubs": s1_report,
        "system_2_stubs": s2_report,
        "sapling_stubs": sapling_report,
    }
    print(json.dumps(payload, indent=2))
    ok = (
        s1_report["n"] > 0
        and s2_report["n"] > 0
        and s1_report["priority_accuracy"] == 1
        and s1_report["route_accuracy"] == 1
        and s1_report["system_accuracy"] == 1
        and s2_report["priority_accuracy"] == 1
        and s2_report["route_accuracy"] == 1
        and s2_report["system_accuracy"] == 1
        and sapling_report["n"] == 5
        and sapling_report["verdict_accuracy"] == 1
        and sapling_report["action_accuracy"] == 1
        and all(row["stub"] for row in sapling_report["rows"])
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
