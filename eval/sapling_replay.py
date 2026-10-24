"""Score the Sapling stub triples. No GPU.

The harness checks verdict and action against mocks/sapling_stub. It does
not decide aid eligibility.
"""

from __future__ import annotations

from system2.sapling_client import load_stub_cases, verify


def replay_sapling_stubs() -> dict:
    rows = []
    for case in load_stub_cases():
        verdict = verify(
            case["policy"],
            case["evidence"],
            case["claim"],
            check=case["check"],
        )
        rows.append(
            {
                "id": case["id"],
                "check": case["check"],
                "verdict_match": verdict.verdict == case["expected_verdict"],
                "action_match": verdict.action == case["expected_action"],
                "stub": verdict.stub,
            }
        )
    count = len(rows) or 1

    def accuracy(key: str) -> float:
        if not rows:
            return 0.0
        return sum(1 for row in rows if row[key]) / count

    return {
        "n": len(rows),
        "verdict_accuracy": accuracy("verdict_match"),
        "action_accuracy": accuracy("action_match"),
        "rows": rows,
    }
