"""Markdown report for one stub run. Numbers are the arm rule, not a measurement."""

from __future__ import annotations

from eval.learning.loop import SeedScore
from eval.learning.metrics import ArmScore
from eval.learning.split import Split


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _names(items: tuple[str, ...] | list[str]) -> str:
    return ", ".join(items) if items else "none"


def render(
    splits: list[tuple[Split, dict[str, ArmScore], dict[str, int]]],
    decision: dict,
    current: list[SeedScore],
    candidate: list[SeedScore],
    external: str = "",
    traits: str = "",
) -> str:
    lines = [
        "# Held-out correction eval (stub)",
        "",
        "This is a stub scoreboard. The figures come from the pattern rule in",
        "`eval/learning/arms.py`. No model was called, no weights were trained,",
        "and nothing was promoted. Do not read this file as a measured learning result.",
        "",
        "Design: each fixed seed splits call groups into a correction side and a",
        "held-out side. English and Thai variants of the same call stay together.",
        "Arms are scored only on the held-out side. The shape is no feedback,",
        "feedback, and a shuffled control, so a pile of extra context is not",
        "counted as learning. No external benchmark source was copied.",
        "",
        "Seeds: " + ", ".join(str(split.seed) for split, _, _rows in splits) + ".",
        "",
        "## Arms",
        "",
        "| Arm | What the stub does |",
        "| --- | --- |",
        "| A | Base labels. No feedback. |",
        "| B | Human correction patterns in memory. Memory is non-empty. No network call. |",
        "| C | Human correction JSONL only. Memory stays empty. |",
        "| C_coach | Human and coach JSONL. Sim rows stay out. Memory stays empty. |",
        "| shuffled | Correction labels are permuted. The permutation is not a matched pattern. |",
        "",
        "## Headline: under-triage of critical calls",
        "",
        "Under-triage is the fraction of held-out critical calls whose predicted",
        "priority is less urgent than the label. P1 is the most urgent rank.",
        "`n/a` means that seed held out no critical call. `n/a` is not zero.",
        "A higher under-triage rate blocks a promotion recommendation. The",
        "paired column is candidate minus A. For under-triage, negative is safer.",
        "",
        "Compared version: `" + str(decision["version_id"]) + "` against arm A.",
        "The held-out split is by `group_id`. Thai, English, and paraphrases of one",
        "call stay together. The candidate in the loop is arm C, human sources",
        "only. `C_coach` is the same rule with coach rows added. It is not the",
        "candidate, and it does not read `source=sim`.",
        "",
    ]
    for split, scores, row_counts in splits:
        lines.extend(
            [
                f"## Seed {split.seed}",
                "",
                "Correction groups: " + ", ".join(split.correction) + ".",
                "",
                "Held-out groups: " + ", ".join(split.held_out) + ".",
                "",
                "Feedback rows written for B / C / C_coach / shuffled: "
                + " / ".join(str(row_counts[name]) for name in ("B", "C", "C_coach", "shuffled"))
                + ". Arm A writes none. JSONL is an artifact. Scoring does not train on it.",
                "",
                "| Arm | Accuracy | Macro-F1 | Under-triage | Route accuracy | Safe-action rate | Sapling unsure | Accuracy − A | Under-triage − A | Repeat errors | Regressions vs A |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for name in ("A", "B", "C", "C_coach", "shuffled"):
            score = scores[name]
            lines.append(
                "| {name} | {acc} | {f1} | {ut} | {route} | {safe} | {sap} | {dacc} | {dut} | {rep} | {reg} |".format(
                    name=name,
                    acc=_fmt(score.accuracy),
                    f1=_fmt(score.macro_f1),
                    ut=_fmt(score.under_triage),
                    route=_fmt(score.route_accuracy),
                    safe=_fmt(score.safe_action_rate),
                    sap=_fmt(score.sapling_unsure_rate),
                    dacc=_fmt(score.paired_accuracy),
                    dut=_fmt(score.paired_under_triage),
                    rep=_names(score.repeat_errors),
                    reg=_names(score.regressions),
                )
            )
        lines.append("")
    lines.extend(
        [
            "## Closed loop",
            "",
            f"Version `{decision['version_id']}` was scored as arm C on the held-out calls.",
            "Arm A is the current run.",
            "",
            "Recommend promotion: " + ("yes" if decision["recommend"] else "no") + ".",
            "",
            "Promoted: no.",
            "",
            f"`learning_eval.promotion`: {decision['promotion']}. "
            "The hook does not promote a version.",
            "",
            f"`learning_eval.freeze_mubit_auto_adapters`: {decision['freeze_mubit_auto_adapters']}. "
            "Auto-adapters were not frozen, and Mubit was not called.",
            "",
            "Per seed, arm A then arm C:",
            "",
        ]
    )
    current_by_seed = {item.seed: item for item in current}
    candidate_by_seed = {item.seed: item for item in candidate}
    for seed in sorted(current_by_seed):
        base = current_by_seed[seed]
        proposed = candidate_by_seed[seed]
        lines.append(
            f"- Seed {seed}: accuracy {_fmt(base.accuracy)} → {_fmt(proposed.accuracy)}, "
            f"under-triage {_fmt(base.under_triage)} → {_fmt(proposed.under_triage)}."
        )
    lines.extend(["", "Reasons:", ""])
    for reason in decision["reasons"]:
        lines.append(f"- {reason}")
    lines.append("")
    if traits.strip():
        lines.append(traits.strip())
        lines.append("")
    if external.strip():
        lines.append(external.strip())
        lines.append("")
    return "\n".join(lines)
