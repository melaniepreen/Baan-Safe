# BaanSafe contracts (v0.2)

These Pydantic v2 models are the only shared language between Moly (System 1, gateway, router, UI) and Melanie (System 2, memory, eval). JSON Schemas in `contracts/schemas/` are exported for a TypeScript or JavaScript UI. The schemas describe shapes. They do not choose a priority or a route.

Priority names, route names, and escalation rules live in `config/` and are waiting for human sign-off. `system2.hosting` is `openrouter via mubit gateway`. The Nemotron model id, speech-to-text, the demo flood event, and the production database are `TODO_HUMAN` in `config/decisions.yaml`.

## Priority

Produced by both systems on an `Outcome`, and again by the router as `final_priority`. Consumed by the call agent and the eval harness.

`P1` immediate life-safety. `P2` urgent, hours. `P3` welfare, same day. `P4` information or non-urgent. The words are defined in `config/priorities.yaml`.

## Route

Produced by both systems and by the router. Consumed by dispatch and the UI. The allowed values and the starting need map are in `config/routes.yaml`.

## Need

Produced as extracted fields and on outcomes. Consumed by the router and the UI. Values: rescue, medical, water, food, shelter, evacuation, power, information, aid_payment.

## System

`system_1` (Moly) or `system_2` (Melanie). Stamped on every `Outcome`.

## NextAction

Produced only by the router. Consumed by the call agent. Values: ask_next_question, create_provisional_dispatch, escalate_to_supervisor, finalize_case, request_more_evidence.

## TranscriptTurn

Produced by the call agent (or by a fixture's scripted stream). Consumed by extraction and by both systems as `CaseState.transcript`. A turn is a millisecond offset, a speaker (`caller` or `operator`), and text. Callers in fixtures are synthetic.

## ExtractedFields

Produced by the extraction step (method is `TODO_HUMAN`; the field list is not). Consumed by both systems inside `CaseState`. Holds location text, location confidence, people count, vulnerability tags, a medical flag, danger tags, and needs. This scaffold does not extract fields from text.

## MemoryItem

Produced by Mubit retrieval (Melanie). Consumed by both systems as `memory_context`. Kind is `similar_case`, `prior_failure`, `policy`, or `correction`.

## CaseState

Produced by the gateway after enrichment and memory retrieval. Consumed by System 1 and System 2 as their input. Carries the case id, a caller hash (never a raw phone number), the transcript, extracted fields, memory, policy flags, a resources object, and `received_at`.

### Example: CaseState

```json
{
  "case_id": "EXAMPLE-CASE",
  "caller_id_hash": "synthetic:example-caller",
  "transcript": [
    {
      "t_ms": 0,
      "speaker": "caller",
      "text": "We need drinking water. The ground is dry."
    },
    {
      "t_ms": 4200,
      "speaker": "operator",
      "text": "Which district are you in?"
    },
    {
      "t_ms": 8000,
      "speaker": "caller",
      "text": "Mueang Lampang District, near the blue temple."
    }
  ],
  "fields": {
    "location": "Mueang Lampang District, Lampang",
    "location_confidence": 0.93,
    "people_count": 3,
    "vulnerable": [],
    "medical": false,
    "danger": [],
    "needs": ["water"]
  },
  "memory_context": [],
  "policy_flags": [],
  "resources": {},
  "received_at": "2026-10-23T08:00:00Z"
}
```

## Outcome

Produced by System 1 and by System 2. One shape for both. Consumed by the router. `outcome` is `fast_route`, `reasoned_recommendation`, or `escalate`. `reasoning` is for System 2; System 1 leaves it null. `confidence` is 0–1. `escalate` means System 1 is handing the case to System 2.

### Example: System 1 Outcome

```json
{
  "system": "system_1",
  "outcome": "fast_route",
  "priority": "P3",
  "needs": ["water"],
  "route": "welfare_distribution",
  "confidence": 0.94,
  "reason": "Clear same-day water request with a complete district and no danger signs.",
  "reasoning": null,
  "missing_evidence": [],
  "next_question": null,
  "requires_human": false,
  "escalate": false,
  "latency_ms": 20
}
```

### Example: System 2 Outcome

```json
{
  "system": "system_2",
  "outcome": "reasoned_recommendation",
  "priority": "P1",
  "needs": ["rescue", "medical"],
  "route": "rescue_coordination",
  "confidence": 0.86,
  "reason": "Oxygen-dependent elderly person with rising water is an immediate life-safety risk.",
  "reasoning": "The caller is not asking for welfare supplies. An oxygen-dependent elderly person cannot safely wait if the water keeps rising, so this is a rescue plus medical case and a human must confirm the dispatch.",
  "missing_evidence": ["water_depth"],
  "next_question": "Is the water still outside, or has it entered the room?",
  "requires_human": true,
  "escalate": false,
  "latency_ms": 90
}
```

## RouterDecision

Produced by the decision router (Moly). Consumed by the call agent. Points at `next_action`, the final priority and route, whether a human is required, the outcomes that were merged, and policy notes. `router/merge.py` is still a stub. The stub gateway only copies a stub outcome into this shape.

## Correction

Produced by an operator, supervisor, or caseworker. Consumed by memory (`write_correction`) and, on the paired fixture, retrieved as a `MemoryItem` of kind `correction`.

## MemoryRecord

Produced by the gateway after a decision. Consumed by Mubit's write path (Melanie). Bundles a summary, the evidence, the router decision, an optional outcome label, an optional failure note, and corrections.

## TraceEvent

Produced by the Mubit gateway at each stage (`gateway`, `system_1`, `system_2`, `router`, `memory_write`). Consumed by audit and `GET /metrics`. Appended to `traces.jsonl` by `trace.py`. `outcome` is optional. When System 1 or System 2 runs, that stage's event carries the outcome on its own. Older lines without `outcome` still validate. `model_version` is set by the correction-loop replay stub.

## Ontology (v0.2)

These shapes were added so Moly and Melanie can pass the same objects. They do not decide a case. `Need` was already the need entity (the enum above). `CaseState` is the case. No model stores a name, a phone number, or a street address.

- `Person` — synthetic id, household id, role, vulnerability tags.
- `Household` — members and a district label.
- `Request` — a person asks for something; needs use the `Need` enum.
- `Evidence` — transcript, operator, public data, or a correction.
- `Hazard` — flood, rain, medical, safeguarding, or other.
- `Resource` — a boat, ambulance, shelter, welfare point, or other unit.
- `AidPolicy` — a policy summary. Baht amounts are not a field.
- `Failure` — what a later correction is about.
- `AidEligibility` — `status` is only `unset` or `needs_human`. It cannot record an approval.
- `TrainingJob` and `ModelVersion` — the stub correction loop. A job status of `stub` means no weights were trained.

`MemoryRecord` still describes a case, holds evidence, records the decision, and can note a failure and corrections. Mubit retrieves and writes it. The gateway is the caller.
