---
title: Policies and aid API
tags: [aid, eligibility, exceptions, escalation, policy]
files:
  - api/routes/endpoints.py
  - system1/aid_eligibility.py
  - system2/aid_exceptions.py
  - config/escalation.yaml
---

## Purpose

Aid eligibility and exception endpoints are stubs. They do not approve a payment or an exception. Escalation rules are listed for humans and are not evaluated by the gateway.

## Key files

- `api/routes/endpoints.py` — `GET /aid/eligibility`, `POST /aid/exceptions`. Both return HTTP 501.
- `system1/aid_eligibility.py` — `check`. Owner: Melanie. No baht amount.
- `system2/aid_exceptions.py` — `propose`. Owner: Melanie.
- `config/escalation.yaml` — `escalate_to_system_2_if_any`, `always_requires_human`, enrichment flag numbers, `stub_next_action_order`.
- `gateway/policy.py` — one note: safeguarding and escalation rules were not evaluated.
- `config/priorities.yaml`, `config/routes.yaml` — names. Not a live scorer.

## Interfaces/contracts

- `GET /aid/eligibility?case_id=` loads a fixture or a stored case, calls `check`, and maps `NotImplementedError` to 501 (`not_ready`, owner Melanie).
- `POST /aid/exceptions` takes a `CaseState` and calls `propose`. Same 501 path.
- `AidEligibility` in `contracts/models.py` is the return shape. `check` does not return one yet.
- `always_requires_human` includes `aid denial or exception` and `route == supervisor_escalation`.

## Invariants

- Neither endpoint approves a payment or an exception.
- The gateway does not read the rule strings in `escalation.yaml` to pick a system. Fixture `expected.system` is the harness stand-in.
- Enrichment thresholds attach data flags. They do not change priority or route.
- `stub_next_action_order` is plumbing for `use_stubs=True` only. It is not a merge policy.

## How to test

- `tests/test_architecture.py` — `test_aid_stubs_return_501`.
- `tests/test_api.py` — route status codes.
- `make validate` — escalation file is not executed; personal-data scan still applies to fixtures.

## Common pitfalls

- Hardcoding a relief amount. `system1/aid_eligibility.py` does not read a baht figure. Regulations move.
- Implementing escalation by editing `gateway/route.py`. Validate fails if that file contains `fields.medical` or `oxygen_dependent`.
- Returning HTTP 200 from the aid routes before `check` / `propose` exist.

## Open TODO_HUMAN keys

- `system1.extraction_method` (named by `check`)
- `system2.orchestrator_model`, `system2.max_latency_ms` (named by `propose`; hosting is already set)
- `gateway.route_chooser` (live system choice, not the aid routes)
