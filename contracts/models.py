"""Pydantic v2 contracts shared by System 1, System 2, the gateway, and the API.

These models are the data shapes only. They do not decide priority or route.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Priority(str, Enum):
    P1 = "P1"  # immediate life-safety risk
    P2 = "P2"  # urgent, hours
    P3 = "P3"  # welfare, same day
    P4 = "P4"  # information / non-urgent


class Route(str, Enum):
    rescue_coordination = "rescue_coordination"
    medical_response = "medical_response"
    welfare_distribution = "welfare_distribution"
    shelter_placement = "shelter_placement"
    aid_caseworker = "aid_caseworker"
    information_only = "information_only"
    duplicate_merge = "duplicate_merge"
    supervisor_escalation = "supervisor_escalation"


class Need(str, Enum):
    rescue = "rescue"
    medical = "medical"
    water = "water"
    food = "food"
    shelter = "shelter"
    evacuation = "evacuation"
    power = "power"
    information = "information"
    aid_payment = "aid_payment"


class System(str, Enum):
    system_1 = "system_1"
    system_2 = "system_2"


class NextAction(str, Enum):
    ask_next_question = "ask_next_question"
    create_provisional_dispatch = "create_provisional_dispatch"
    escalate_to_supervisor = "escalate_to_supervisor"
    finalize_case = "finalize_case"
    request_more_evidence = "request_more_evidence"


class TranscriptTurn(_Model):
    t_ms: int = Field(ge=0)
    speaker: Literal["caller", "operator"]
    text: str = Field(min_length=1)


class ExtractedFields(_Model):
    location: str | None = None
    location_confidence: float | None = Field(default=None, ge=0, le=1)
    people_count: int | None = Field(default=None, ge=0)
    vulnerable: list[str] = Field(default_factory=list)
    medical: bool = False
    danger: list[str] = Field(default_factory=list)
    needs: list[Need] = Field(default_factory=list)


class MemoryItem(_Model):
    memory_id: str = Field(min_length=1)
    kind: Literal["similar_case", "prior_failure", "policy", "correction"]
    summary: str = Field(min_length=1)
    relevance: float = Field(ge=0, le=1)
    source_case_id: str | None = None


class CaseState(_Model):
    case_id: str = Field(min_length=1)
    caller_id_hash: str = Field(min_length=1)
    transcript: list[TranscriptTurn]
    fields: ExtractedFields
    memory_context: list[MemoryItem] = Field(default_factory=list)
    policy_flags: list[str] = Field(default_factory=list)
    resources: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime


class Outcome(_Model):
    """One shape for both systems. reasoning is set by System 2 only."""

    system: System
    outcome: Literal["fast_route", "reasoned_recommendation", "escalate"]
    priority: Priority
    needs: list[Need]
    route: Route
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    reasoning: str | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    next_question: str | None = None
    requires_human: bool
    escalate: bool
    latency_ms: int | None = Field(default=None, ge=0)


class Dispatch(_Model):
    """One provisional resource assignment for one need (CR-003)."""

    need: Need
    resource_kind: Literal["boat", "ambulance", "shelter", "welfare_point"]
    resource_id: str | None = None
    status: Literal["provisional", "unfilled"]
    same_district: bool = False
    note: str | None = None


class RouterDecision(_Model):
    case_id: str = Field(min_length=1)
    next_action: NextAction
    final_priority: Priority
    final_route: Route
    requires_human: bool
    source_outcomes: list[Outcome]
    policy_notes: list[str] = Field(default_factory=list)
    dispatches: list[Dispatch] = Field(default_factory=list)


class Correction(_Model):
    """Operator correction. v1 fields are optional so older JSONL rows still load.

    `field`, `old_value`, and `new_value` stay the memory record. When a row
    is copied into the training log, `contracts.training.adapt_correction`
    reads the v1 fields and, if they are absent, infers the task from `field`.
    Task names match `contracts.training.Task`.
    """

    correction_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    corrected_by: Literal["operator", "supervisor", "caseworker"]
    field: str = Field(min_length=1)
    old_value: Any = None
    new_value: Any = None
    reason: str = Field(min_length=1)
    created_at: datetime
    schema_version: Literal[1] | None = None
    task: Literal["s1_triage", "s2_action", "sapling_verdict"] | None = None
    group_id: str | None = None
    turn_ids: list[str] = Field(default_factory=list)
    lang: Literal["th", "en", "mixed"] | None = None
    policy_ids: list[str] = Field(default_factory=list)
    memory_ref: str | None = None
    output_model: str | None = None
    output_correct: str | None = None
    source: Literal["human", "coach", "sim"] | None = None
    weight: float | None = Field(default=None, ge=0)
    model_version: str | None = None
    policy_version: str | None = None


class MemoryRecord(_Model):
    record_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_summary: str
    evidence: ExtractedFields
    decision: RouterDecision
    outcome_label: str | None = None
    failure: str | None = None
    corrections: list[Correction] = Field(default_factory=list)


class TraceEvent(_Model):
    case_id: str = Field(min_length=1)
    stage: Literal["gateway", "system_1", "system_2", "router", "memory_write"]
    started_at: datetime
    latency_ms: int = Field(ge=0)
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    model: str | None = None
    model_version: str | None = None
    outcome: Outcome | None = None
    notes: str | None = None


class Person(_Model):
    """A synthetic participant. No name, phone, or national id."""

    person_id: str = Field(min_length=1)
    household_id: str | None = None
    role: Literal["caller", "household_member", "operator", "caseworker", "supervisor"] = "caller"
    vulnerability_tags: list[str] = Field(default_factory=list)


class Household(_Model):
    """A synthetic household. location_label is a district, not a street address."""

    household_id: str = Field(min_length=1)
    member_ids: list[str] = Field(default_factory=list)
    location_label: str | None = None
    people_count: int | None = Field(default=None, ge=0)


class Hazard(_Model):
    hazard_id: str = Field(min_length=1)
    kind: Literal["flood", "rain", "medical", "safeguarding", "other"]
    summary: str = Field(min_length=1)
    location_label: str | None = None


class Evidence(_Model):
    evidence_id: str = Field(min_length=1)
    request_id: str | None = None
    source: Literal["transcript", "operator", "public_data", "correction"]
    summary: str = Field(min_length=1)
    fields: ExtractedFields | None = None


class Request(_Model):
    request_id: str = Field(min_length=1)
    person_id: str = Field(min_length=1)
    case_id: str | None = None
    summary: str = Field(min_length=1)
    needs: list[Need] = Field(default_factory=list)


class Resource(_Model):
    resource_id: str = Field(min_length=1)
    kind: Literal["boat", "ambulance", "shelter", "welfare_point", "other"]
    name: str = Field(min_length=1)
    district: str | None = None
    available: int | None = Field(default=None, ge=0)


class AidPolicy(_Model):
    """A policy summary. Baht amounts are not stored here."""

    policy_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    needs: list[Need] = Field(default_factory=list)


class Failure(_Model):
    failure_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    kind: Literal[
        "wrong_priority",
        "wrong_route",
        "missed_safeguarding",
        "wrong_aid",
        "other",
    ]


class AidEligibility(_Model):
    """Stub result. status is never an approval."""

    case_id: str = Field(min_length=1)
    status: Literal["unset", "needs_human"] = "unset"
    policy_id: str | None = None
    notes: str | None = None


class TrainingJob(_Model):
    job_id: str = Field(min_length=1)
    status: Literal["stub", "queued", "running", "failed", "completed"]
    dataset_path: str = Field(min_length=1)
    base_model: str = Field(min_length=1)
    target_version_id: str = Field(min_length=1)
    notes: str | None = None


class ModelVersion(_Model):
    version_id: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    role: Literal["system_1", "system_2", "orchestrator"]
    parent_version_id: str | None = None
    training_job_id: str | None = None
    notes: str | None = None


MODEL_TYPES: list[type[_Model] | type[Enum]] = [
    Priority,
    Route,
    Need,
    System,
    NextAction,
    TranscriptTurn,
    ExtractedFields,
    MemoryItem,
    CaseState,
    Outcome,
    Dispatch,
    RouterDecision,
    Correction,
    MemoryRecord,
    TraceEvent,
    Person,
    Household,
    Hazard,
    Evidence,
    Request,
    Resource,
    AidPolicy,
    Failure,
    AidEligibility,
    TrainingJob,
    ModelVersion,
]
