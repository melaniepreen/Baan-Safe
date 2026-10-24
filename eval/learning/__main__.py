"""Write the stub held-out report. `make eval-learning`."""

from __future__ import annotations

from eval.learning.harness import run
from eval.learning.metrics import ArmScore


def _line(score: ArmScore) -> str:
    ut = "n/a" if score.under_triage is None else f"{score.under_triage:.3f}"
    return f"accuracy {score.accuracy:.3f}, under-triage {ut}"


def main() -> int:
    result = run()
    print(result["report_path"])
    print("stub scoreboard; not a measured learning result")
    for seed in result["seeds"]:
        arms = seed["arms"]
        print(
            f"seed {seed['seed']}: A {_line(arms['A'])}; "
            f"C {_line(arms['C'])}; shuffled accuracy−A {arms['shuffled'].paired_accuracy:.3f}"
        )
    print(
        f"recommend={result['recommend']} promoted={result['promoted']} "
        f"learning_eval.promotion={result['promotion']} "
        f"learning_eval.freeze_mubit_auto_adapters={result['freeze_mubit_auto_adapters']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
