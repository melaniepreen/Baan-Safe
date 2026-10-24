"""TrainingEvent schema v1.

One JSONL line in the append-only log. Ontology, the gateway, routing,
the policies API, and the Mubit-only rule are unchanged. Other agents
import these types. They do not redefine them.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.models import Correction, NextAction

SCHEMA_VERSION = 1

Task = Literal["s1_triage", "s2_action", "sapling_verdict"]
Source = Literal["human", "coach", "sim"]
CorrectedBy = Literal["operator", "supervisor", "caseworker"]
Lang = Literal["th", "en", "mixed"]

# Defaults. Override with TRAINING_WEIGHT_HUMAN / _COACH / _SIM, or pass a table
# into adapt_correction. An explicit weight on the event wins over both.
DEFAULT_WEIGHTS: dict[str, float] = {
    "human": 1.0,
    "coach": 0.5,
    "sim": 0.25,
}

# Legacy Correction.field values. The task is inferred. The output still has
# to be a closed label for that task.
_FIELD_TO_TASK: dict[str, Task] = {
    "s1_triage": "s1_triage",
    "s1": "s1_triage",
    "s1_label": "s1_triage",
    "label": "s1_triage",
    "triage": "s1_triage",
    "priority": "s1_triage",
    "route": "s1_triage",
    "s2_action": "s2_action",
    "s2": "s2_action",
    "action": "s2_action",
    "next_action": "s2_action",
    "sapling_verdict": "sapling_verdict",
    "sapling": "sapling_verdict",
    "verdict": "sapling_verdict",
}

LEGACY_MODEL_VERSION = "legacy@unversioned"


class AdaptError(ValueError):
    """A correction cannot be copied into a TrainingEvent."""


class _TrainingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class S1Label(str, Enum):
    """Closed s1_triage labels. The ids are the policies API label ids."""

    niems_red_critical = "niems_red_critical"
    niems_yellow_urgent = "niems_yellow_urgent"
    niems_green_not_severe = "niems_green_not_severe"
    niems_white_general = "niems_white_general"
    niems_black_not_a_patient = "niems_black_not_a_patient"
    niems_not_conscious_or_breathing = "niems_not_conscious_or_breathing"
    sphere_water_short = "sphere_water_short"
    sphere_food_short = "sphere_food_short"
    sphere_shelter_crowded = "sphere_shelter_crowded"
    safeguarding_child = "safeguarding_child"
    safeguarding_older_person = "safeguarding_older_person"
    safeguarding_disability = "safeguarding_disability"
    safeguarding_serious_health = "safeguarding_serious_health"
    safeguarding_protection_referral = "safeguarding_protection_referral"
    flood_water_depth = "flood_water_depth"
    flood_trapped = "flood_trapped"


class S2Action(str, Enum):
    """Closed s2_action labels. The same set as RouterDecision.next_action."""

    ask_next_question = "ask_next_question"
    create_provisional_dispatch = "create_provisional_dispatch"
    escalate_to_supervisor = "escalate_to_supervisor"
    finalize_case = "finalize_case"
    request_more_evidence = "request_more_evidence"


class SaplingVerdict(str, Enum):
    """Closed sapling_verdict labels.

    This is the label set. `system2.sapling_client.SaplingVerdict` is the
    runtime result object and is a different type.
    """

    supported = "supported"
    violation = "violation"
    missing = "missing"
    contradicted = "contradicted"
    unsure = "unsure"


TaskOutput = S1Label | S2Action | SaplingVerdict

_ENUM_FOR_TASK: dict[str, type[S1Label] | type[S2Action] | type[SaplingVerdict]] = {
    "s1_triage": S1Label,
    "s2_action": S2Action,
    "sapling_verdict": SaplingVerdict,
}


def enum_for_task(task: Task) -> type[S1Label] | type[S2Action] | type[SaplingVerdict]:
    try:
        return _ENUM_FOR_TASK[task]
    except KeyError as exc:
        raise ValueError(f"unknown task {task!r}") from exc


def _task_for_output(value: TaskOutput) -> Task:
    if isinstance(value, S1Label):
        return "s1_triage"
    if isinstance(value, S2Action):
        return "s2_action"
    if isinstance(value, SaplingVerdict):
        return "sapling_verdict"
    raise ValueError(f"not a closed training label: {value!r}")


class InputRef(_TrainingModel):
    case_id: str = Field(min_length=1)
    turn_ids: list[str] = Field(default_factory=list)
    lang: Lang
    policy_ids: list[str] = Field(default_factory=list)
    memory_ref: str | None = None


def content_hash_for(
    task: str,
    input_ref: InputRef | Mapping[str, Any],
    output_correct: str | TaskOutput,
) -> str:
    """Dedup key over task + input_ref + output_correct.

    SHA-256 hex of UTF-8 JSON with sorted keys and compact separators.
    `input_ref` is the InputRef object. `output_correct` is the label value.
    """

    if isinstance(input_ref, InputRef):
        ref = input_ref.model_dump(mode="json")
    else:
        ref = InputRef.model_validate(dict(input_ref)).model_dump(mode="json")
    if isinstance(output_correct, Enum):
        correct = str(output_correct.value)
    else:
        correct = str(output_correct)
    payload = {"task": task, "input_ref": ref, "output_correct": correct}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_weight(
    source: str,
    weight: float | None = None,
    *,
    table: Mapping[str, float] | None = None,
) -> float:
    if weight is not None:
        chosen = float(weight)
    elif table is not None and source in table:
        chosen = float(table[source])
    else:
        env = os.environ.get(f"TRAINING_WEIGHT_{source.upper()}", "").strip()
        if env:
            chosen = float(env)
        else:
            try:
                chosen = float(DEFAULT_WEIGHTS[source])
            except KeyError as exc:
                raise ValueError(f"unknown source {source!r}") from exc
    if chosen < 0:
        raise ValueError("weight must be >= 0")
    return chosen


def current_policy_version() -> str:
    """Corpus pin from the policies API. This does not call Mubit."""

    from policies.service import get_service

    version = get_service().current().version
    if not isinstance(version, str) or not version:
        raise RuntimeError("policies API returned no corpus version")
    return version


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class TrainingEvent(_TrainingModel):
    """One append-only training row. schema v1."""

    schema_version: Literal[1] = SCHEMA_VERSION
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task: Task
    group_id: str = Field(min_length=1)
    input_ref: InputRef
    output_model: TaskOutput | None = None
    output_correct: TaskOutput
    reason: str = Field(min_length=1)
    source: Source
    corrected_by: CorrectedBy | None = None
    weight: float | None = Field(default=None, ge=0)
    model_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    content_hash: str = ""

    @model_validator(mode="after")
    def _close(self) -> TrainingEvent:
        parsed = uuid.UUID(self.event_id)
        self.event_id = str(parsed)
        self.created_at = _as_utc(self.created_at)
        if self.source == "human" and self.corrected_by is None:
            raise ValueError("corrected_by is required when source is human")
        self.weight = resolve_weight(self.source, self.weight)
        _expect(self.output_model, self.task, "output_model", allow_none=True)
        _expect(self.output_correct, self.task, "output_correct", allow_none=False)
        digest = content_hash_for(self.task, self.input_ref, self.output_correct)
        if self.content_hash not in ("", digest):
            raise ValueError(
                "content_hash does not match task, input_ref, and output_correct"
            )
        self.content_hash = digest
        return self


def _expect(value: TaskOutput | None, task: str, field: str, *, allow_none: bool) -> None:
    if value is None:
        if allow_none:
            return
        raise ValueError(f"{field} is required")
    actual = _task_for_output(value)
    if actual != task:
        raise ValueError(f"{field} {value.value!r} is a {actual} label, not {task}")


def _coerce(task: Task, value: object, *, required: bool) -> TaskOutput | None:
    if value is None:
        if required:
            raise AdaptError(f"{task} needs a closed output_correct")
        return None
    if isinstance(value, Enum):
        token = str(value.value).strip()
    elif isinstance(value, str):
        token = value.strip()
    else:
        if required:
            raise AdaptError(
                f"{task} output must be a closed label, got {type(value).__name__}"
            )
        return None
    if not token:
        if required:
            raise AdaptError(f"{task} needs a closed output_correct")
        return None
    try:
        return enum_for_task(task)(token)
    except ValueError as exc:
        raise AdaptError(f"{token!r} is not a {task} label") from exc


def adapt_correction(
    correction: Correction,
    *,
    weights: Mapping[str, float] | None = None,
) -> TrainingEvent:
    """Copy a Correction into a TrainingEvent.

    Pre-v1 rows set `source` to human and take the task from `field`.
    `output_correct` is the v1 field when it is set, otherwise `new_value`.
    `output_model` is the v1 field when it is set. A legacy `old_value` is
    kept only when it is already a closed label for that task. Route names
    and priority names are not labels, so those rows raise AdaptError and
    stay on corrections.jsonl.
    """

    task: Task | None = correction.task
    if task is None:
        task = _FIELD_TO_TASK.get(correction.field.strip())
    if task is None:
        raise AdaptError(f"cannot infer task from field {correction.field!r}")

    if correction.output_correct is not None:
        output_correct = _coerce(task, correction.output_correct, required=True)
    else:
        output_correct = _coerce(task, correction.new_value, required=True)
    if output_correct is None:
        raise AdaptError(f"{task} needs a closed output_correct")

    if correction.output_model is not None:
        output_model = _coerce(task, correction.output_model, required=True)
    else:
        try:
            raw_old = correction.old_value if isinstance(correction.old_value, str) else None
            output_model = _coerce(task, raw_old, required=False)
        except AdaptError:
            output_model = None

    source: Source = correction.source or "human"
    group_id = (correction.group_id or "").strip() or correction.case_id
    model_version = (correction.model_version or "").strip() or LEGACY_MODEL_VERSION
    policy_version = (correction.policy_version or "").strip() or current_policy_version()
    weight = resolve_weight(source, correction.weight, table=weights)
    return TrainingEvent(
        created_at=correction.created_at,
        task=task,
        group_id=group_id,
        input_ref=InputRef(
            case_id=correction.case_id,
            turn_ids=list(correction.turn_ids),
            lang=correction.lang or "en",
            policy_ids=list(correction.policy_ids),
            memory_ref=correction.memory_ref,
        ),
        output_model=output_model,
        output_correct=output_correct,
        reason=correction.reason,
        source=source,
        corrected_by=correction.corrected_by,
        weight=weight,
        model_version=model_version,
        policy_version=policy_version,
    )


def correction_is_v1(correction: Correction) -> bool:
    """True when the caller sent a v1 field and a failed adapt is their error."""

    return any(
        (
            correction.schema_version is not None,
            correction.task is not None,
            bool(correction.group_id),
            bool(correction.turn_ids),
            correction.lang is not None,
            bool(correction.policy_ids),
            correction.memory_ref is not None,
            correction.output_model is not None,
            correction.output_correct is not None,
            correction.source is not None,
            correction.weight is not None,
            correction.model_version is not None,
            correction.policy_version is not None,
        )
    )


TRAINING_SCHEMA_TYPES: list[type[_TrainingModel] | type[Enum]] = [
    S1Label,
    S2Action,
    SaplingVerdict,
    InputRef,
    TrainingEvent,
]


def _s2_matches_router() -> None:
    """Import-time guard so S2Action cannot drift from NextAction unnoticed.

    A mismatch raises here, before a caller writes an event. The fix is a
    schema change, recorded under Proposed changes, not a silent widening.
    """

    router = {member.value for member in NextAction}
    closed = {member.value for member in S2Action}
    if router != closed:
        raise RuntimeError(
            "S2Action is out of step with RouterDecision.next_action: "
            f"router={sorted(router)} training={sorted(closed)}"
        )


_s2_matches_router()
