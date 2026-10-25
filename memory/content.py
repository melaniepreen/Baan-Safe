"""Lane names and the text each memory backend stores for a record.

Shared by `memory/local.py` (BaanSafe's own JSONL store) and
`memory/mubit.py` (control-plane client, dormant until Mubit exposes a
memory API) so both write the same content and read it back the same way.
The content is built from `ExtractedFields` and the `RouterDecision` only:
no transcript text and no `CaseState.resources` (that dict carries
`caller_ip`).
"""

from __future__ import annotations

import re
from typing import Literal

from contracts.models import Correction, MemoryRecord

LANE_CASE = "baansafe-case"
LANE_CORRECTION = "baansafe-correction"
LANE_POLICY = "baansafe-policy"

MemoryKind = Literal["similar_case", "prior_failure", "policy", "correction"]
KIND_BY_LANE: dict[str, MemoryKind] = {
    LANE_CASE: "similar_case",
    LANE_CORRECTION: "correction",
    LANE_POLICY: "policy",
}

# `record_content` prefixes every case fact with "Case <id>: " so the id
# survives even if a backend drops the metadata object.
CASE_PREFIX = re.compile(r"^\s*Case\s+([A-Za-z0-9][A-Za-z0-9._:-]*)\s*:")

MAX_CONTENT_CHARS = 800


def record_content(record: MemoryRecord) -> str:
    """One line summarising a routed turn: fields plus the router's decision."""
    fields = record.evidence
    needs = [need.value for need in fields.needs]
    decision = record.decision
    summary = (
        f"Case {record.case_id}: "
        f"needs={','.join(needs) or 'none'}; "
        f"location={fields.location or 'unknown'}; "
        f"people={fields.people_count if fields.people_count is not None else 'unknown'}; "
        f"decision={decision.next_action.value}; "
        f"route={decision.final_route.value}; "
        f"priority={decision.final_priority.value}"
    )
    if record.case_summary:
        summary += f". {record.case_summary}"
    if record.corrections:
        summary += f". corrections={len(record.corrections)}"
    return summary[:MAX_CONTENT_CHARS]


def correction_task(correction: Correction) -> str:
    return correction.task or correction.field


def correction_content(correction: Correction) -> str:
    reason = (correction.reason or "").strip() or "no reason given"
    task = correction_task(correction)
    output = correction.output_correct or correction.new_value
    summary = (
        f"Human correction on {correction.case_id} "
        f"task={task} output={output}: {reason}"
    )
    return summary[:MAX_CONTENT_CHARS]


def source_case_id_from(content: str) -> str | None:
    """The `Case <id>:` prefix, or None."""
    match = CASE_PREFIX.match(content or "")
    return match.group(1) if match else None
