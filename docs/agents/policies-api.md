---
title: Policies and aid API
tags: [aid, eligibility, exceptions, escalation, policy]
files:
  - api/routes/policies.py
  - policies/service.py
  - api/routes/endpoints.py
  - config/escalation.yaml
---

## Purpose

The policy corpus is served from `policies/service.py`. Aid eligibility and exception endpoints stay stubs and do not approve a payment or an exception. Escalation rules are listed for humans and are not evaluated by the gateway.

## Key files

- `policies/service.py` — load, list, match, pin. `local_yaml` is the only live adapter (`policies/sources/local_yaml.py`).
- `policies/*.yaml` — rule text. Provenance: `policies/SOURCES.md`.
- `api/routes/policies.py` — prefix `/policies`. Mounted from `api/main.py`.
- `api/routes/endpoints.py` — `GET /aid/eligibility`, `POST /aid/exceptions`. Both return HTTP 501.
- `system1/aid_eligibility.py` — `check`. Owner: Melanie. No baht amount.
- `system2/aid_exceptions.py` — `propose`. Owner: Melanie.
- `system1/labels.py`, `system2/sapling_policy.py` — read the service.
- `config/escalation.yaml` — `route_to_system_2_if_any`, `system_1_min_confidence`, `always_requires_human`, enrichment flag numbers.
- `gateway/policy.py` — one note: safeguarding and escalation rules were not evaluated.

## Interfaces/contracts

- `GET /policies`, `GET /policies/labels`, `GET /policies/sources`, `GET /policies/{rule_id}`, `POST /policies/match`, `POST /policies/pins`.
- Domains: `aid_eligibility`, `safeguarding`, `triage`. Jurisdiction: `TH` or `intl`. `lang` is `en` or `th`.
- `POST /policies/pins` stores a corpus snapshot under `var/policy-pins/` (gitignored). Later reads pass `version` or `run_id`.
- `GET /aid/eligibility?case_id=` loads a fixture or a stored case, calls `check`, and maps `NotImplementedError` to 501 (`not_ready`, owner Melanie).
- `POST /aid/exceptions` takes a `CaseState` and calls `propose`. Same 501 path.
- `AidEligibility` in `contracts/models.py` is the return shape. `check` does not return one yet.
- `always_requires_human` includes `aid denial or exception` and `route == supervisor_escalation`.

## Invariants

- Loading a rule by id does not make it authoritative. `policies.authoritative_set` is `TODO_HUMAN`.
- ReliefWeb and DDPM were not used as corpus sources (`policies/SOURCES.md`).
- Neither aid endpoint approves a payment or an exception.
- `gateway/chooser.py` evaluates `route_to_system_2_if_any` to pick a system for every case; `router/merge.py` implements `always_requires_human`.
- Enrichment thresholds attach data flags. They do not change priority or route.

## How to test

- `tests/test_policies_api.py`, `tests/test_policy_corpus.py`.
- `tests/test_architecture.py` — `test_aid_stubs_return_501`.
- `make validate` — `policies.authoritative_set` stays `TODO_HUMAN`.

## Common pitfalls

- Hardcoding a relief amount. `system1/aid_eligibility.py` does not read a baht figure. Regulations move.
- Implementing escalation by editing `gateway/route.py`. Validate fails if that file contains `fields.medical` or `oxygen_dependent`.
- Returning HTTP 200 from the aid routes before `check` / `propose` exist.
- Treating a corpus match as an approval. Match only retrieves rule text.

## Open TODO_HUMAN keys

- `system1.extraction_method` (named by `check`)
- `system2.orchestrator_model`, `system2.max_latency_ms` (named by `propose`; hosting is already set)
- `policies.authoritative_set`
