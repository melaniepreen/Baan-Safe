---
title: Decision router
tags: [router, merge, next-action, dispatch]
files:
  - router/merge.py
  - router/ledger.py
  - gateway/route.py
  - config/escalation.yaml
---

## Purpose

The Decision Router turns one system's outcome into the next action and, when dispatching, one provisional `Dispatch` per dispatchable need. `router/merge.py` is the real implementation, called by `gateway/route.py` for every case.

## Key files

- `router/merge.py` — `merge(case, outcome, extra_notes=(), resources=None, prior=()) -> RouterDecision`. Owner: Moly.
- `router/ledger.py` — in-process reservation ledger: `reserve`, `reserved_by_others`, `reserved_total`, `holds`, `confirmed`, `confirm_case`, `cancel_case`, `release_case`, `reset`. Nothing is written to disk; reservations reset on restart.
- `api/routes/endpoints.py` — `POST /cases/{case_id}/dispatches/confirm` and `.../cancel` wrap the ledger (API-only `DispatchActionResult`); `GET /resources` subtracts `reserved_total` from each unit's `available`.
- `gateway/route.py` — calls `router.merge.merge` and traces `router.merge ran`.
- `contracts/models.py` — `RouterDecision`, `NextAction`, `Dispatch` (CR-003). Dispatch status stays `provisional|unfilled`; confirm/cancel do not mutate `RouterDecision`.
- `mocks/resources.json` — fictional resource snapshot (`load_resources()`). Router tests keep this default.
- `mocks/loader.py` `load_dispatch_resources()` — fictional units plus public shelters, hospitals, and ferry terminals from `data/snapshots/places.json`. The gateway passes this snapshot. Real units are listed first.

## Interfaces/contracts

- `NextAction`: `ask_next_question`, `create_provisional_dispatch`, `escalate_to_supervisor`, `finalize_case`, `request_more_evidence`.
- Next-action order, first match wins: `supervisor_escalation` route or `safeguarding` flag → escalate; `aid_caseworker` → escalate; `outcome.escalate` → escalate; `duplicate_merge` → finalize; `missing_evidence`, `next_question`, or no `fields.location` → ask next question; `information_only` → finalize; otherwise → `create_provisional_dispatch`.
- Dispatch fan-out (only for `create_provisional_dispatch`): rescue→boat, medical→ambulance, water/food→welfare_point, shelter/evacuation→shelter. A unit this case already holds for that need wins (idempotent re-decision), then same-district units (district name inside `fields.location`, case-insensitive), then first with `available - reserved_by_others > 0`, else `unfilled` with `resource_id` None and a note. Every `merge` call releases the case's reservations that are no longer in its dispatches. Stock is reserved in-process only; the ledger resets on restart.
- Human confirm/cancel (HANDOVER #7 / wire P3): `POST /cases/{case_id}/dispatches/confirm` marks every current hold as confirmed; `POST /cases/{case_id}/dispatches/cancel` releases every hold for the case. Response shape: `{ case_id, action: "confirmed"|"cancelled", holds: [{ resource_id, need, status: "confirmed"|"released" }] }`. HTTP 422 when there is nothing to confirm/cancel; 404 if the case is unknown. Does not edit `Dispatch.status` on the stored `RouterDecision`.
- `GET /resources` returns `load_dispatch_resources()` with each unit's `available` reduced by `ledger.reserved_total(unit.id)` (floor 0), so the UI does not always show full stock.
- `requires_human` = outcome's, or `supervisor_escalation`/`aid_caseworker` route, or `safeguarding` flag, or any unfilled dispatch. `final_priority`/`final_route` echo the outcome.
- `RouterDecision` carries `final_priority`, `final_route`, `source_outcomes` = [deciding outcome, *prior] (length 2 on a cascade, `[system_2, system_1]`), `policy_notes`, `dispatches`. Readers of `source_outcomes[0]` always see the deciding system.

## Invariants

- One deciding outcome in, one decision out. Earlier-stage outcomes arrive as `prior` and change nothing but `source_outcomes` order and the selected-system note.
- P1/P2 with missing evidence asks first — no provisional dispatch.
- `always_requires_human` in `config/escalation.yaml` is implemented here.

## How to test

- `tests/test_router.py` — each next-action rule, fan-out, same-district preference, unfilled stock.
- `tests/test_ledger.py` — reserve, confirm, cancel, `reserved_total`, release pruning.
- `tests/test_api.py` — confirm/cancel routes and ledger-aware `GET /resources`.
- `make demo-stub` — prints `next_action` per fixture through the real router.
- `make replay-stubs` — stub outcomes versus `expected` labels. It does not score `merge`.

## Common pitfalls

- Putting priority logic in the router. It echoes the selected system's outcome.
- Treating Sapling's `requires_human` as `Outcome.escalate`. Escalation to System 2 and a human handoff are different fields.
- Treating a provisional dispatch as durable. Reservations live in `router/ledger.py` memory and are lost on restart.
- Extending `Dispatch.status` for confirm — contracts stay `provisional|unfilled`; use the confirm/cancel API instead.
- `needs` not in the kind map (power, information, aid_payment) produce no dispatch.

## Open TODO_HUMAN keys

- None read inside `router/merge.py`. The chooser is decided (`gateway.route_chooser` = `field precheck`).
- Priority and route names in `config/priorities.yaml` and `config/routes.yaml` are still awaiting human sign-off (`contracts/CONTRACTS.md`).
