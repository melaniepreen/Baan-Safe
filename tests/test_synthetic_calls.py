"""Seeded flood-call set, the group split, and both training exports.

The original 24 fixtures stay on ``all_ids()``. Laya is optional: the row
shape is checked without it, and ``to_internal`` runs only when the package
is installed.
"""

import json
import re

import pytest

from contracts.models import CaseState, MemoryItem
from fixtures.load import all_ids, iter_synthetic, synthetic_split
from fixtures.synthetic_build import KINSHIP_TH, NUMBER_TH, build_catalog
from fixtures.synthetic_gold import COLOUR_TO_LABEL, NOUL_LABELS, derive_expected
from training.laya_export import laya_row, questions, write_laya
from training.synthetic_export import setfit_row, split_calls, write_setfit

PHONE = re.compile(r"(?:\+66|0)[\s-]?\d[\d\s-]{7,}")
LABELS = list(COLOUR_TO_LABEL.values()) + list(NOUL_LABELS)


def _caller(call: dict) -> str:
    return " ".join(
        turn["text"] for turn in call["transcript_stream"] if turn["speaker"] == "caller"
    )


def test_original_fixture_index_is_unchanged():
    ids = all_ids()
    assert len(ids) == 24
    assert all(not item.startswith("syn-") for item in ids)


def test_catalog_counts_split_and_kinship():
    calls = iter_synthetic()
    assert len(calls) == 240
    fresh = build_catalog()
    assert [call["id"] for call in calls] == [call["id"] for call in fresh["calls"]]

    counts = {label: 0 for label in LABELS}
    for call in calls:
        assert "TODO_HUMAN" not in json.dumps(call, ensure_ascii=False)
        spoken = " ".join(turn["text"] for turn in call["transcript_stream"])
        assert PHONE.search(spoken) is None
        assert not re.search(r"\b\d{13}\b", spoken)
        assert call["case_state"]["caller_id_hash"].startswith("synthetic:")
        assert not (set(call["hard_negatives"]) & set(call["labels"]))
        for label in call["labels"]:
            counts[label] += 1
    short = {label: count for label, count in counts.items() if count < 12}
    assert short == {}

    split = synthetic_split()
    assert len(split["train_groups"]) == 56
    assert len(split["held_out_groups"]) == 24
    assert split["train_calls"] == 168
    assert split["held_out_calls"] == 72
    assert set(split["train_groups"]).isdisjoint(split["held_out_groups"])
    assert split["train_groups"] == fresh["train_groups"]
    assert split["held_out_groups"] == fresh["held_out_groups"]

    thai = "\n".join(_caller(call) for call in calls if call["lang"] == "th")
    english = "\n".join(_caller(call) for call in calls if call["lang"] == "en")
    for word in KINSHIP_TH:
        assert word in thai
    for word in NUMBER_TH:
        assert f"{word}คน" in thai or f"{word} คน" in thai
    assert "three of us" in english
    assert "my two kids" in english


def test_grandmother_is_critical_and_grandchildren_are_lan():
    call = next(item for item in iter_synthetic() if item["id"] == "syn-niems-red-critical-05-th")
    body = " ".join(turn["text"] for turn in call["transcript_stream"])
    assert "เด็ก" not in body
    for word in ("ยาย", "หลาน", "หายใจไม่ออก"):
        assert word in body
    assert call["colour"] == "red"
    assert call["expected"]["system"] == "system_2"
    assert call["expected"]["priority"] == "P1"
    assert call["expected"]["route"] == "rescue_coordination"
    for label in (
        "niems_red_critical",
        "safeguarding_child",
        "safeguarding_older_person",
        "niems_not_conscious_or_breathing",
    ):
        assert label in call["labels"]


def test_expected_matches_chooser_and_rescue_stays_on_system_2():
    for call in iter_synthetic():
        case = CaseState.model_validate(call["case_state"])
        memory = [MemoryItem.model_validate(item) for item in call["memory_context"]]
        got = derive_expected(case, memory, colour=call["colour"], labels=call["labels"])
        expected = call["expected"]
        for key in (
            "system",
            "priority",
            "route",
            "needs",
            "requires_human",
            "missing_evidence",
            "acceptable_next_questions",
            "action",
        ):
            assert got[key] == expected[key], call["id"]
        if "rescue" in call["case_state"]["fields"]["needs"]:
            assert expected["system"] == "system_2"
            assert expected["route"] == "rescue_coordination"
    duplicates = [call for call in iter_synthetic() if call["memory_context"]]
    assert duplicates
    assert any(call["expected"]["route"] == "duplicate_merge" for call in duplicates)


def test_setfit_and_laya_share_the_group_split(tmp_path):
    train, held = split_calls()
    assert len(train) == 168
    assert len(held) == 72
    assert setfit_row(train[0]).keys() == {"text", "label", "group_id", "weight"}
    counts = write_setfit(tmp_path)
    assert counts == {"train": 168, "held_out": 72}
    setfit_line = json.loads((tmp_path / "s1_synthetic.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert setfit_line["label"]
    assert setfit_line["weight"] == 1.0

    asked = questions()
    named = set(re.findall(r"`(\w+)`", " ".join(q["instructions"] for q in asked.values())))
    assert named == {"body"}
    assert asked["priority"]["type"] == "choice"
    assert list(asked["priority"]["criteria"]) == ["red", "yellow", "green", "white", "black"]
    assert len(NOUL_LABELS) == 11
    for label in NOUL_LABELS:
        assert asked[label]["type"] == "noul"
    row = laya_row(train[0], asked)
    assert set(row["state"]) == {"body"}
    assert row["state"]["body"]
    assert row["expected"]["priority"] == train[0]["colour"]
    for label in NOUL_LABELS:
        assert row["expected"][label] is (label in train[0]["labels"])

    laya_counts = write_laya(tmp_path / "laya")
    assert laya_counts["train"] == 168
    assert laya_counts["held_out"] == 72
    assert laya_counts["questions"] == 12
    written = json.loads((tmp_path / "laya" / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert written["state"]["body"]
    assert written["questions"]["priority"]["type"] == "choice"

    pytest.importorskip("laya")
    from laya.train import target_from_expected, to_internal

    internal = to_internal("priority", written["questions"]["priority"])
    target = target_from_expected(internal, written["expected"]["priority"])
    keys = list(internal["crit"])
    assert target[keys.index(written["expected"]["priority"])] == 1.0
    noul_id = NOUL_LABELS[0]
    noul_q = to_internal(noul_id, written["questions"][noul_id])
    noul_target = target_from_expected(noul_q, written["expected"][noul_id])
    assert noul_target == ([0.0, 1.0] if written["expected"][noul_id] else [1.0, 0.0])
