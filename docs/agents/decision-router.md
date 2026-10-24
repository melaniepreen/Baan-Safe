---
title: Decision router
tags: [router, merge, next-action, dispatch]
files:
  - router/merge.py
  - gateway/route.py
  - config/escalation.yaml
---

## Purpose

The Decision Router turns one system's outcome into the next action and, when dispatching, one provisional `Dispatch` per dispatchable need. `router/merge.py` is the real implementation, called by `gateway/route.py` for every case.

## Key files

- `router/merge.py` — `merge(case, outcome, extra_notes=(), resources=None) -> RouterDecision`. Owner: Moly.
- `gateway/route.py` — calls `router.merge.merge` and traces `router.merge ran`.
- `contracts/models.py` — `RouterDecision`, `NextAction`, `Dispatch` (CR-003).
- `mocks/resources.json` — fictional resource snapshot (`load_resources()`).

## Interfaces/contracts

- `NextAction`: `ask_next_question`, `create_provisional_dispatch`, `escalate_to_supervisor`, `finalize_case`, `request_more_evidence`.
- Next-action order, first match wins: `supervisor_escalation` route or `safeguarding` flag → escalate; `aid_caseworker` → escalate; `outcome.escalate` → escalate; `duplicate_merge` → finalize; `missing_evidence`, `next_question`, or no `fields.location` → ask next question; `information_only` → finalize; otherwise → `create_provisional_dispatch`.
- Dispatch fan-out (only for `create_provisional_dispatch`): rescue→boat, medical→ambulance, water/food→welfare_point, shelter/evacuation→shelter. Same-district units win (district name inside `fields.location`, case-insensitive), else first available anywhere, else `unfilled` with `resource_id` None and a note. Stock is never decremented.
- `requires_human` = outcome's, or `supervisor_escalation`/`aid_caseworker` route, or `safeguarding` flag, or any unfilled dispatch. `final_priority`/`final_route` echo the outcome.
- `RouterDecision` carries `final_priority`, `final_route`, `source_outcomes` (length 1), `policy_notes`, `dispatches`.

## Invariants

- One outcome in, one decision out. Do not merge System 1 and System 2 on the same turn.
- P1/P2 with missing evidence asks first — no provisional dispatch.
- `always_requires_human` in `config/escalation.yaml` is implemented here.

## How to test

- `tests/test_router.py` — each next-action rule, fan-out, same-district preference, unfilled stock.
- `make demo-stub` — prints `next_action` per fixture through the real router.
- `make replay-stubs` — stub outcomes versus `expected` labels. It does not score `merge`.

## Common pitfalls

- Putting priority logic in the router. It echoes the selected system's outcome.
- Treating Sapling's `requires_human` as `Outcome.escalate`. Escalation to System 2 and a human handoff are different fields.
- Reserving or decrementing `mocks/resources.json`. Dispatches are provisional only.
- `needs` not in the kind map (power, information, aid_payment) produce no dispatch.

## Open TODO_HUMAN keys

- None read inside `router/merge.py`. The chooser is decided (`gateway.route_chooser` = `field precheck`).
- Priority and route names in `config/priorities.yaml` and `config/routes.yaml` are still awaiting human sign-off (`contracts/CONTRACTS.md`).
