"""Score a callable against fixture expected labels.

The harness reports accuracy on priority, route, and system. It does not
decide those labels.
"""

from __future__ import annotations

from collections.abc import Callable

from contracts.models import CaseState, Outcome
from fixtures.load import load_case, load_fixture


def replay(
    system: Callable[[CaseState], Outcome],
    fixture_ids: list[str],
) -> dict:
    rows = []
    for fixture_id in fixture_ids:
        payload = load_fixture(fixture_id)
        case = load_case(fixture_id)
        outcome = system(case)
        expected = payload["expected"]
        rows.append(
            {
                "id": fixture_id,
                "priority_match": outcome.priority.value == expected["priority"],
                "route_match": outcome.route.value == expected["route"],
                "system_match": outcome.system.value == expected["system"],
                "latency_ms": outcome.latency_ms,
            }
        )
    count = len(rows) or 1
    latencies = [row["latency_ms"] for row in rows if row["latency_ms"] is not None]

    def accuracy(key: str) -> float:
        if not rows:
            return 0.0
        return sum(1 for row in rows if row[key]) / count

    return {
        "n": len(rows),
        "priority_accuracy": accuracy("priority_match"),
        "route_accuracy": accuracy("route_match"),
        "system_accuracy": accuracy("system_match"),
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        "rows": rows,
    }
