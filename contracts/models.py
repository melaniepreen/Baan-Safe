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


class RouterDecision(_Model):
    case_id: str = Field(min_length=1)
    next_action: NextAction
    final_priority: Priority
    final_route: Route
    requires_human: bool
    source_outcomes: list[Outcome]
    policy_notes: list[str] = Field(default_factory=list)


class Correction(_Model):
    correction_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    corrected_by: Literal["operator", "supervisor", "caseworker"]
    field: str = Field(min_length=1)
    old_value: Any = None
    new_value: Any = None
    reason: str = Field(min_length=1)
    created_at: datetime


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
    RouterDecision,
    Correction,
    MemoryRecord,
    TraceEvent,
]
