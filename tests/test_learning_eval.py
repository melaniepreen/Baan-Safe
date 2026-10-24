"""One smoke test for the held-out correction skeleton."""

from __future__ import annotations

import re

from dataclasses import replace

from eval.learning.arms import arm_by_name, feedback_rows, predict
from eval.learning.cases import GROUPS, group_by_id, variants
from eval.learning.harness import run
from eval.learning.loop import SeedScore, recommend_promotion
from eval.learning.split import SEEDS, split_groups


def test_learning_eval_smoke(tmp_path):
    ids = [group.group_id for group in GROUPS]
    calls = variants()
    by_id = group_by_id()

    for seed in SEEDS:
        left = split_groups(ids, seed)
        right = split_groups(list(reversed(ids)), seed)
        assert left == right
        assert set(left.correction).isdisjoint(left.held_out)
        assert set(left.correction) | set(left.held_out) == set(ids)
        assert left.correction == tuple(sorted(left.correction))
        assert left.held_out == tuple(sorted(left.held_out))
        held_ids = set(left.held_out)
        correction_ids = set(left.correction)
        for group_id in ids:
            on_held = {call.language for call in calls if call.group_id == group_id and call.group_id in held_ids}
            on_correction = {
                call.language
                for call in calls
                if call.group_id == group_id and call.group_id in correction_ids
            }
            if group_id in held_ids:
                assert on_held == {"en", "th"}
                assert on_correction == set()
            else:
                assert on_correction == {"en", "th"}
                assert on_held == set()

    held = next(call for call in calls if call.group_id == "call-water-nan" and call.language == "en")
    correction = [by_id["call-water-lampang"]]
    base = predict(arm_by_name("A"), held, correction, seed=17)
    memory = predict(arm_by_name("B"), held, correction, seed=17)
    tuned = predict(arm_by_name("C"), held, correction, seed=17)
    shuffled = predict(arm_by_name("shuffled"), held, correction, seed=17)
    assert (base.priority, base.route) != (held.priority, held.route)
    assert (memory.priority, memory.route) == (held.priority, held.route)
    assert (tuned.priority, tuned.route) == (held.priority, held.route)
    assert arm_by_name("C").memory_empty is True
    assert (shuffled.priority, shuffled.route) == (base.priority, base.route)
    assert shuffled.learned is False

    coach = replace(by_id["call-water-lampang"], group_id="call-water-coach", source="coach")
    human_only = predict(arm_by_name("C"), held, [coach], seed=17)
    with_coach = predict(arm_by_name("C_coach"), held, [coach], seed=17)
    assert human_only.learned is False
    assert (human_only.priority, human_only.route) == (base.priority, base.route)
    assert with_coach.learned is True
    assert (with_coach.priority, with_coach.route) == (held.priority, held.route)
    human_rows = feedback_rows(arm_by_name("C"), [by_id["call-water-lampang"], coach], seed=17)
    both_rows = feedback_rows(arm_by_name("C_coach"), [by_id["call-water-lampang"], coach], seed=17)
    assert {row["source"] for row in human_rows} == {"human"}
    assert {row["source"] for row in both_rows} == {"human", "coach"}
    assert {row["group_id"] for row in both_rows} == {"call-water-lampang", "call-water-coach"}
    collapsed = split_groups(["call-water-nan", "call-water-nan", "call-water-lampang"], 17)
    assert set(collapsed.correction).isdisjoint(collapsed.held_out)
    assert set(collapsed.correction) | set(collapsed.held_out) == {"call-water-nan", "call-water-lampang"}

    current = (SeedScore(1, 0.5, 0.2), SeedScore(2, 0.4, 0.0))
    rose_and_safer = (SeedScore(1, 0.8, 0.2), SeedScore(2, 0.9, 0.0))
    under_rose = (SeedScore(1, 0.8, 0.4), SeedScore(2, 0.9, 0.0))
    blocked = recommend_promotion(current, under_rose)
    allowed = recommend_promotion(current, rose_and_safer)
    assert blocked["recommend"] is False
    assert blocked["promoted"] is False
    assert allowed["recommend"] is True
    assert allowed["promoted"] is False
    missing = (SeedScore(1, 0.8, None), SeedScore(2, 0.9, 0.0))
    assert recommend_promotion(current, missing)["recommend"] is False

    result = run(tmp_path)
    for seed in result["seeds"]:
        assert seed["arms"]["shuffled"].paired_accuracy == 0
    text = (tmp_path / "learning.md").read_text(encoding="utf-8")
    assert "Under-triage" in text
    for name in ("| A |", "| B |", "| C |", "| C_coach |", "| shuffled |"):
        assert name in text
    assert "group_id" in text
    assert "learning_eval.promotion" in text
    assert "learning_eval.freeze_mubit_auto_adapters" in text
    assert "Held-out caller simulators" in text
    assert "omits_location" in text
    assert "under_reports" in text
    assert "External sanity check: does the model learn from feedback" in text
    assert "latte_bench.license_confirmation" in text
    assert "TODO_HUMAN" in text
    assert result["promoted"] is False
    for secret in ("sk-", "api_key", "API_KEY", "Bearer ", "mbt_"):
        assert secret not in text
    assert re.search(r"\b\d{13}\b", text) is None
