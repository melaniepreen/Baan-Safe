---
title: System 1
tags: [system1, triage, aid, fast-path, extraction]
files:
  - system1/decide.py
  - system1/extract.py
  - system1/aid_eligibility.py
  - gateway/chooser.py
---

## Purpose

Fast path. Deterministic triage and keyword extraction are Moly's. The aid eligibility check is Melanie's and still raises.

## Key files

- `system1/extract.py` — `extract(transcript, districts=None) -> (ExtractedFields, flags)`. English-only keyword rules.
- `system1/decide.py` — `decide(case) -> Outcome`. Owner: Moly. Real rules.
- `gateway/chooser.py` — `system_2_triggers(case)` shared by the gateway and `decide` (defence in depth).
- `system1/aid_eligibility.py` — `check(case) -> AidEligibility`. Owner: Melanie. Raises.
- `config/escalation.yaml` — `route_to_system_2_if_any`, `system_1_min_confidence`.
- `mocks/` — S1 stub outcomes the gateway copies when `use_stubs=True`.

## Interfaces/contracts

- `extract` reads caller turns only, sentence-splits, and drops a match when a negator sits within the three words before it. It suggests `conflicting_evidence` and `safeguarding` flags; the gateway attaches them plus `keyword_extraction`.
- When `districts` is None the extractor loads names from the SQLite `districts` table; a missing DB means an empty list. Tests pass an explicit list.
- `decide` order: System 2 triggers → duplicate (`similar_case` memory at relevance ≥ `DUPLICATE_RELEVANCE` 0.9 → `duplicate_merge`) → needs table (`NEEDS_TABLE`; empty or unmatched needs escalate) → `location_confidence` below `system_1_min_confidence` (0.80) escalates → missing `people_count` asks "How many people are with you?" → `fast_route`.
- `check` must return `AidEligibility`. Today it raises. It does not approve a payment and it does not read a baht amount.
- `gateway/route.py` does not call `aid_eligibility.check`. The HTTP stub is `GET /aid/eligibility` (see `docs/agents/policies-api.md`).

## Invariants

- System 1 does not call Sapling.
- The gateway never runs System 1 and then System 2 on the same turn.
- `system1.extraction_method` is `rules-only` (in `DECIDED`). `system1.extraction_model` stays `TODO_HUMAN`; the rules path does not read it.
- Escalation rules live in `config/escalation.yaml`, evaluated in `gateway/chooser.py` — never inline in `gateway/route.py` (validate checks).

## How to test

- `make test` — `tests/test_system1.py`, `tests/test_extract.py`, `tests/test_chooser.py`.
- `S1_IMPL=real` replays the rules through `gateway.handle`; `make replay-stubs` still scores the stub files.
- `make validate` — `system1/decide.py` is no longer in the stub check.

## Common pitfalls

- Auto-approving aid. `check` must not approve a payment.
- Calling Sapling from System 1. The verifier is System 2 only.
- Expecting `extract` to understand Thai. It is English-only; Thai handling is undecided.
- Operator turns count as evidence. They are ignored by the extractor.

## Open TODO_HUMAN keys

- `system1.extraction_model`
