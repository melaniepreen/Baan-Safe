---
title: Decision router
tags: [router, merge, next-action]
files:
  - router/merge.py
  - gateway/route.py
  - config/escalation.yaml
---

## Purpose

The Decision Router turns one system's outcome into the next action. The merge policy is not written. The stub gateway copies the single selected outcome.

## Key files

- `router/merge.py` — `merge(outcomes, policy_flags) -> RouterDecision`. Owner: Moly. Raises `NotImplementedError`.
- `gateway/route.py` — `_assemble` builds the `RouterDecision` the stub returns. Trace stage `router` says merge was not called.
- `config/escalation.yaml` — `stub_next_action_order` for that copy only.
- `contracts/models.py` — `RouterDecision`, `NextAction`.

## Interfaces/contracts

- `NextAction`: `ask_next_question`, `create_provisional_dispatch`, `escalate_to_supervisor`, `finalize_case`, `request_more_evidence`.
- `RouterDecision` carries `final_priority`, `final_route`, `source_outcomes` (length 1 on the stub path), and `policy_notes`.
- `merge` is not on the stub path. `use_stubs=False` still does not call it. Live `decide()` raises first.

## Invariants

- One outcome in, one decision out. Do not merge System 1 and System 2 on the same turn.
- `scripts/validate.py` rejects a `RouterDecision(` constructor in `router/merge.py`.
- `stub_next_action_order` is not a product merge policy. First match wins, and only for the stub copy.

## How to test

- `tests/test_gateway_and_replay.py` — `merge([], [])` raises, match `Moly`. Stub decisions match fixture labels for `F01`, `F10`, `C01-b`, `G01`.
- `make replay-stubs` — stub outcomes versus `expected` labels. This does not score `merge`.

## Common pitfalls

- Calling `merge` from `gateway/route.py` before a human writes the policy.
- Putting priority logic in the router copy. The stub echoes the selected system's stub outcome.
- Treating Sapling's `requires_human` as `Outcome.escalate`. Escalation to System 2 and a human handoff are different fields.

## Open TODO_HUMAN keys

- None are read inside `router/merge.py`. The live chooser that decides which outcome exists is `gateway.route_chooser`.
- Priority and route names in `config/priorities.yaml` and `config/routes.yaml` are still awaiting human sign-off (`contracts/CONTRACTS.md`).
