"""Run the four arms on every fixed seed and write the stub report."""

from __future__ import annotations

from pathlib import Path

from eval.learning.arms import ARMS, feedback_rows, score_variant, write_feedback
from eval.learning.cases import GROUPS, group_by_id, variants
from eval.learning.loop import SeedScore, close_loop, freeze_gate
from eval.learning.metrics import score_arm
from eval.latte.section import external_section
from eval.learning.report import render
from eval.learning.simulators import render_trait_section
from eval.learning.split import SEEDS, split_groups
from paths import ROOT

CANDIDATE_VERSION = "stub-candidate"
CANDIDATE_ARM = "C"
CURRENT_ARM = "A"


def run(out_dir: Path | None = None, version_id: str = CANDIDATE_VERSION) -> dict:
    """Score stubs, then apply the closed-loop hook. Writes `learning.md`.

    `freeze_gate` runs before scoring. While it is TODO_HUMAN the stub
    continues and does not call Mubit.
    """
    freeze_note = freeze_gate()
    out = out_dir or (ROOT / "eval" / "out")
    out.mkdir(parents=True, exist_ok=True)
    by_id = group_by_id()
    group_ids = [group.group_id for group in GROUPS]
    calls = variants()
    rendered: list = []
    seed_payloads: list[dict] = []
    current_scores: list[SeedScore] = []
    candidate_scores: list[SeedScore] = []

    for seed in SEEDS:
        split = split_groups(group_ids, seed)
        correction = [by_id[group_id] for group_id in split.correction]
        held_out = [call for call in calls if call.group_id in split.held_out]
        rows_by_arm = {}
        row_counts: dict[str, int] = {}
        for arm in ARMS:
            rows_by_arm[arm.name] = [
                score_variant(arm, call, correction, seed) for call in held_out
            ]
            rows = feedback_rows(arm, correction, seed)
            row_counts[arm.name] = len(rows)
            if rows:
                write_feedback(out / f"arm_{arm.name}_seed{seed}.jsonl", rows)
        baseline = rows_by_arm[CURRENT_ARM]
        scores = {
            name: score_arm(name, rows, baseline) for name, rows in rows_by_arm.items()
        }
        rendered.append((split, scores, row_counts))
        current_scores.append(
            SeedScore(
                seed=seed,
                accuracy=scores[CURRENT_ARM].accuracy,
                under_triage=scores[CURRENT_ARM].under_triage,
            )
        )
        candidate_scores.append(
            SeedScore(
                seed=seed,
                accuracy=scores[CANDIDATE_ARM].accuracy,
                under_triage=scores[CANDIDATE_ARM].under_triage,
            )
        )
        seed_payloads.append(
            {
                "seed": seed,
                "correction": list(split.correction),
                "held_out": list(split.held_out),
                "arms": {name: scores[name] for name in scores},
            }
        )

    decision = close_loop(version_id, current_scores, candidate_scores)
    decision["freeze_mubit_auto_adapters"] = freeze_note
    text = render(
        rendered,
        decision,
        current_scores,
        candidate_scores,
        external=external_section(out),
        traits=render_trait_section(),
    )
    path = out / "learning.md"
    path.write_text(text, encoding="utf-8")
    return {
        "report_path": str(path),
        "version_id": version_id,
        "recommend": decision["recommend"],
        "promoted": decision["promoted"],
        "promotion": decision["promotion"],
        "freeze_mubit_auto_adapters": decision["freeze_mubit_auto_adapters"],
        "reasons": decision["reasons"],
        "seeds": seed_payloads,
    }
