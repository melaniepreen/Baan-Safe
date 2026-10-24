---
title: System 1
tags: [system1, triage, aid, fast-path]
files:
  - system1/decide.py
  - system1/aid_eligibility.py
---

## Purpose

Fast path. Deterministic triage is Moly's. The aid eligibility check is Melanie's. Neither decides a case yet.

## Key files

- `system1/decide.py` — `decide(case) -> Outcome`. Owner: Moly.
- `system1/aid_eligibility.py` — `check(case) -> AidEligibility`. Owner: Melanie.
- `system1/__init__.py` — re-exports `decide`.
- `mocks/` — S1 stub outcomes the gateway copies when `use_stubs=True`.

## Interfaces/contracts

- `decide` must return `Outcome` once a human writes the rules. Today it raises `NotImplementedError` and names unset keys.
- `check` must return `AidEligibility`. Today it raises. It does not approve a payment and it does not read a baht amount.
- `gateway/route.py` does not call `aid_eligibility.check`. The HTTP stub is `GET /aid/eligibility` (see `docs/agents/policies-api.md`).
- `scripts/validate.py` `check_stubs_are_stubs` rejects an `Outcome(` constructor in `system1/decide.py`.

## Invariants

- System 1 does not call Sapling.
- The gateway never runs System 1 and then System 2 on the same turn.
- Do not invent an extraction method. `system1.extraction_method` and `system1.extraction_model` stay `TODO_HUMAN` until a human sets them and adds them to `DECIDED`.

## How to test

- `make test` — `tests/test_gateway_and_replay.py` (`test_real_interfaces_raise` expects `Moly`).
- `make replay-stubs` — scores S1 stub files against fixture labels.
- `make validate` — stub file still raises and does not construct `Outcome`.

## Common pitfalls

- Implementing rules by constructing `Outcome` inside `decide` before the decisions are set. Validate forbids the constructor in that file.
- Calling Sapling from System 1. The verifier is System 2 only.
- Auto-approving aid. `check` must not approve a payment.

## Open TODO_HUMAN keys

- `system1.extraction_method`
- `system1.extraction_model`
