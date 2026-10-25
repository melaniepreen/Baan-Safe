"""Mubit control-plane memory client. Owner: Melanie (wired for demo).

Uses POST /v2/control/query for retrieval and POST /v2/control/ingest for
writes. Chat completions stay in llm/client.py. Never prints the API key.

MEMORY_IMPL=mubit selects this module via memory.adapter. Default Modal and
local stays MEMORY_IMPL=mock so fixture memory still works without a project.
"""

from __future__ import annotations

import os
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from config.settings import require_decision
from contracts.models import CaseState, Correction, MemoryItem, MemoryRecord

_AGENT_ID = "baansafe-gateway"
MemoryKind = Literal["similar_case", "prior_failure", "policy", "correction"]
_KIND_BY_ENTRY: dict[str, MemoryKind] = {
    "lesson": "correction",
    "rule": "policy",
    "fact": "similar_case",
    "prior_failure": "prior_failure",
    "correction": "correction",
    "policy": "policy",
    "similar_case": "similar_case",
}


def _api_key() -> str:
    key = os.environ.get("MUBIT_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "MEMORY_IMPL=mubit requires MUBIT_API_KEY. Refusing the call."
        )
    return key


def _gateway_origin() -> str:
    """Control routes live on the Mubit host root, not the OpenAI compat prefix."""
    base = os.environ.get("MUBIT_BASE_URL", "").strip()
    if not base:
        raise RuntimeError(
            "MEMORY_IMPL=mubit requires MUBIT_BASE_URL. Refusing the call."
        )
    parsed = urlparse(base if "://" in base else f"https://{base}")
    host = (parsed.hostname or "").lower()
    if host not in {"api.mubit.ai"} and not host.endswith(".mubit.ai"):
        raise RuntimeError(
            f"MUBIT_BASE_URL host {host!r} is not a Mubit host. "
            "Memory traffic is not sent to any other provider."
        )
    return f"{parsed.scheme or 'https'}://{parsed.netloc}"


def _project_scope() -> str:
    """Logical run/project scope. Env overrides the decided leaf for console ids."""
    env = os.environ.get("MUBIT_PROJECT_ID", "").strip()
    if env:
        return env
    return str(require_decision("memory.mubit_project"))


def _scope_fields() -> dict[str, str]:
    """Attach console workspace/project ids when present; always set run_id."""
    scope = _project_scope()
    body = {"run_id": scope, "agent_id": _AGENT_ID}
    if scope.startswith("proj-"):
        body["project_id"] = scope
    elif scope.startswith("ws-"):
        body["workspace_id"] = scope
        body["project_id"] = scope
    return body


def _top_k() -> int:
    value = int(require_decision("memory.retrieval_top_k"))
    return max(1, min(value, 50))


def _token_budget() -> int:
    value = int(require_decision("memory.token_budget"))
    return max(64, min(value, 8000))


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }


def _case_query(case: CaseState) -> str:
    fields = case.fields
    bits = [
        f"case_id={case.case_id}",
        f"location={fields.location or 'unknown'}",
        f"needs={','.join(fields.needs) or 'none'}",
        f"vulnerable={','.join(fields.vulnerable) or 'none'}",
        f"danger={','.join(fields.danger) or 'none'}",
        f"medical={fields.medical}",
    ]
    if case.transcript:
        bits.append(f"last={case.transcript[-1].text[:160]}")
    return (
        "Flood triage memory for this household. "
        "Return similar cases, corrections, and policy lessons. "
        + "; ".join(bits)
    )


def _map_kind(entry_type: str | None, summary: str) -> MemoryKind:
    raw = (entry_type or "fact").strip().lower()
    if raw in _KIND_BY_ENTRY:
        return _KIND_BY_ENTRY[raw]
    lowered = summary.lower()
    if "correct" in lowered:
        return "correction"
    if "fail" in lowered or "miss" in lowered:
        return "prior_failure"
    if "policy" in lowered or "rule" in lowered:
        return "policy"
    return "similar_case"


def _evidence_to_items(payload: dict[str, Any], *, limit: int) -> list[MemoryItem]:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        evidence = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    items: list[MemoryItem] = []
    for index, row in enumerate(evidence[:limit]):
        if not isinstance(row, dict):
            continue
        summary = (
            row.get("content")
            or row.get("text")
            or row.get("summary")
            or row.get("final_answer")
            or ""
        )
        summary = str(summary).strip()
        if not summary:
            continue
        entry_type = row.get("origin_entry_type") or row.get("type") or row.get("entry_type")
        memory_id = str(
            row.get("id")
            or row.get("memory_id")
            or row.get("reference_id")
            or f"mubit-{index + 1}"
        )
        score = row.get("score")
        try:
            relevance = float(score) if score is not None else max(0.5, 1.0 - index * 0.05)
        except (TypeError, ValueError):
            relevance = max(0.5, 1.0 - index * 0.05)
        relevance = max(0.0, min(1.0, relevance))
        source = row.get("source_case_id") or row.get("run_id")
        items.append(
            MemoryItem(
                memory_id=memory_id[:120],
                kind=_map_kind(str(entry_type) if entry_type else None, summary),
                summary=summary[:500],
                relevance=relevance,
                source_case_id=str(source) if source else None,
            )
        )
    if not items:
        answer = payload.get("final_answer") or payload.get("context")
        if isinstance(answer, str) and answer.strip():
            items.append(
                MemoryItem(
                    memory_id="mubit-context",
                    kind="similar_case",
                    summary=answer.strip()[:500],
                    relevance=0.6,
                    source_case_id=None,
                )
            )
    return items


def retrieve(case: CaseState) -> list[MemoryItem]:
    """Query Mubit control plane for case-scoped memory items."""
    origin = _gateway_origin()
    limit = _top_k()
    body = {
        **_scope_fields(),
        "query": _case_query(case),
        "limit": limit,
        "entry_types": ["fact", "lesson", "rule"],
        "mode": "agent_routed",
        "max_token_budget": _token_budget(),
    }
    url = f"{origin}/v2/control/query"
    with httpx.Client(timeout=20.0) as client:
        response = client.post(url, headers=_headers(), json=body)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Mubit memory query failed HTTP {response.status_code}. "
            "Check MUBIT_PROJECT_ID / memory.mubit_project and key scope."
        )
    payload = response.json()
    if not isinstance(payload, dict):
        return []
    return _evidence_to_items(payload, limit=limit)


def _ingest(items: list[dict[str, Any]]) -> None:
    if not items:
        return
    origin = _gateway_origin()
    body = {
        **_scope_fields(),
        "items": items,
    }
    url = f"{origin}/v2/control/ingest"
    with httpx.Client(timeout=20.0) as client:
        response = client.post(url, headers=_headers(), json=body)
    if response.status_code >= 400:
        raise RuntimeError(
            f"Mubit memory ingest failed HTTP {response.status_code}."
        )


def write(record: MemoryRecord) -> None:
    summary = (
        f"Case {record.case.case_id}: "
        f"needs={','.join(record.case.fields.needs) or 'none'}; "
        f"decision={record.decision.next_action}; "
        f"priority={record.decision.final_priority}."
    )
    _ingest(
        [
            {
                "type": "fact",
                "content": summary[:800],
                "lane": "baansafe-case",
            }
        ]
    )


def write_correction(correction: Correction) -> None:
    reason = (correction.reason or "").strip() or "no reason given"
    task = correction.task or correction.field
    output = correction.output_correct or correction.new_value
    summary = (
        f"Human correction on {correction.case_id} "
        f"task={task} output={output}: {reason}"
    )
    _ingest(
        [
            {
                "type": "lesson",
                "content": summary[:800],
                "lane": "baansafe-correction",
            }
        ]
    )
