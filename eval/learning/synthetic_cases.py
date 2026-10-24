"""Call groups built from fixtures/synthetic for EVAL_LEARNING_SET=synthetic.

The split is the committed group_id split, not a fresh shuffle. English,
Thai, and code-switched variants of one scenario share a group and a pattern
(the primary label), so a correction on a sibling can move the held-out call.
"""

from __future__ import annotations

from eval.learning.cases import CallGroup
from eval.learning.split import Split
from fixtures.load import iter_synthetic, synthetic_split
from training.synthetic_export import call_text


def _base(priority: str, route: str) -> tuple[str, str, str]:
    if priority == "P4" and route == "information_only":
        return "P3", "welfare_distribution", "create_provisional_dispatch"
    return "P4", "information_only", "ask_next_question"


def load_groups() -> tuple[list[CallGroup], Split]:
    split_doc = synthetic_split()
    by_group: dict[str, dict[str, dict]] = {}
    for call in iter_synthetic():
        by_group.setdefault(call["group_id"], {})[call["lang"]] = call
    groups: list[CallGroup] = []
    for group_id in sorted(by_group):
        langs = by_group[group_id]
        if set(langs) != {"en", "th", "mixed"}:
            raise RuntimeError(f"{group_id} is missing a language")
        gold = langs["en"]["expected"]
        base_priority, base_route, base_action = _base(gold["priority"], gold["route"])
        groups.append(
            CallGroup(
                group_id=group_id,
                pattern=langs["en"]["primary_label"],
                critical=gold["priority"] == "P1",
                priority=gold["priority"],
                route=gold["route"],
                action=gold["action"],
                base_priority=base_priority,
                base_route=base_route,
                base_action=base_action,
                sapling="n/a",
                en=call_text(langs["en"]),
                th=call_text(langs["th"]),
                mixed=call_text(langs["mixed"]),
                source="human",
            )
        )
    split = Split(
        seed=int(split_doc["seed"]),
        correction=tuple(split_doc["train_groups"]),
        held_out=tuple(split_doc["held_out_groups"]),
    )
    return groups, split
