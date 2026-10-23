"""Print stub RouterDecisions for every fixture. `make demo-stub`."""

from __future__ import annotations

from fixtures.load import all_ids, load_case
from gateway.route import handle


def main() -> int:
    failures = 0
    for fixture_id in all_ids():
        case = load_case(fixture_id)
        decision = handle(case, use_stubs=True)
        print(
            f"{fixture_id}\t{decision.next_action.value}\t"
            f"{decision.final_priority.value}\t{decision.final_route.value}\t"
            f"human={decision.requires_human}\t"
            f"sources={len(decision.source_outcomes)}"
        )
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
