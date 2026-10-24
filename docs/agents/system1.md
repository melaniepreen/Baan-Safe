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

- `system1/extract.py` — `extract(transcript, districts=None) -> (ExtractedFields, flags)`. English and Thai keyword rules (glossary-backed).
- `system1/decide.py` — `decide(case, overlay=None) -> Outcome`. Owner: Moly. Real rules.
- `gateway/chooser.py` — `system_2_triggers(case)` shared by the gateway and `decide` (defence in depth).
- `system1/aid_eligibility.py` — `check(case) -> AidEligibility`. Owner: Melanie. Raises.
- `config/escalation.yaml` — `route_to_system_2_if_any`, `system_1_min_confidence`.
- `ingest/admin_districts.py` — builds the gazetteer the extractor reads.
- `mocks/` — S1 stub outcomes the gateway copies when `use_stubs=True`.

## Interfaces/contracts

- `extract` reads caller turns plus operator turns the caller confirmed with an affirmative first sentence ("yes", "that's right") to a "?" question. Confirmed operator text counts for vulnerable, people_count, and danger only — never needs or flags. Aid and minimising phrases are negation-exempt; everything else drops a match when a negator sits within the three words before it (English) or a Thai negator prefix sits immediately before the hit. Thai need/danger/vulnerable phrases are substring-matched. It suggests `conflicting_evidence`, `safeguarding`, and `aid_exception` flags; the gateway attaches them plus `keyword_extraction`.
- When `districts` is None the extractor reads `admin_districts` and `districts` (English and Thai names), then the committed HDX COD-AB snapshot `data/snapshots/gazetteer.json`. The longest matching name wins. A Thai name is a substring of at least 5 characters, or an `อำเภอ` prefix. An English snapshot name matches as "X District", or bare when it has two or more words that are not all `COMMON_ENGLISH` (so "Mae Mo" matches and "Than To" does not). `DISTRICT_ALIASES` maps caller spellings to the HDX name (`Watthana` → `Vadhana`, `Sathorn` → `Sathon`, …); aliases match bare. A matched name in more than one province returns confidence 0.6 unless the caller named the province. Location is "X District, Province" when the province is known. Tests that pass an explicit list keep that list's order.
- People count understands "N of us", "there are N", "we are N", "a family of N", "me and my <word>" (2), bare-number answers, and "N adults and M children" breakdowns (N+M).
- `decide` order: demoted overlay signature → escalate ("learned demotion") → System 2 triggers → duplicate (`similar_case` memory at relevance ≥ `DUPLICATE_RELEVANCE` 0.9 → `duplicate_merge`) → needs table (`NEEDS_TABLE`; empty or unmatched needs escalate) → `location_confidence` below `system_1_min_confidence` (0.80) escalates → missing `people_count` asks "How many people are with you?" → `fast_route`. Where `decide` would escalate for no needs or low confidence, and only there, a `graduated` overlay rule for the narrow signature returns `fast_route` with the rule's priority, route, needs, and `requires_human`.
- `check` must return `AidEligibility`. Today it raises. It does not approve a payment and it does not read a baht amount.
- `gateway/route.py` does not call `aid_eligibility.check`. The HTTP stub is `GET /aid/eligibility` (see `docs/agents/policies-api.md`).

## Invariants

- System 1 does not call Sapling.
- With `mode: cascade`, a System 1 escalate continues to System 2 in the same turn; the no-stub fallback never cascades. Graduated `fast_route` outcomes do not cascade.
- `system1.extraction_method` is `rules-only` (in `DECIDED`). `system1.extraction_model` stays `TODO_HUMAN`; the rules path does not read it.
- Escalation rules live in `config/escalation.yaml`, evaluated in `gateway/chooser.py` — never inline in `gateway/route.py` (validate checks).

## How to test

- `make test` — `tests/test_system1.py`, `tests/test_extract.py`, `tests/test_chooser.py`.
- `S1_IMPL=real` replays the rules through `gateway.handle`; `make replay-stubs` still scores the stub files.
- `make validate` — `system1/decide.py` is no longer in the stub check.

## Common pitfalls

- Auto-approving aid. `check` must not approve a payment.
- Calling Sapling from System 1. The verifier is System 2 only.
- Assuming Thai needs/danger/vulnerable still escalate empty. Glossary Thai phrases are in the same tables as English; Thai uses substring match plus negator prefixes (`ไม่มีใคร`, `ไม่ได้`, …). Bare `ยา` is intentionally omitted (collides with `พะเยา` / `ยาย` / `อยาก`).
- Operator turns count as evidence. They are ignored by the extractor.

## Open TODO_HUMAN keys

- `system1.extraction_model`
