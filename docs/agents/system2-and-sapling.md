---
title: System 2 and Sapling
tags: [system2, nemotron, sapling, verifier, openrouter]
files:
  - system2/decide.py
  - system2/orchestrator.py
  - system2/sapling.py
  - system2/sapling_client.py
---

## Purpose

Nemotron reasons. Sapling then checks System 2 aid-eligibility and denial claims. The Decision Router sees the result. The orchestrator still raises, so the live verifier does not run.

## Key files

- `system2/decide.py` — `orchestrate`, then `verify_before_router`. Owner: Melanie.
- `system2/orchestrator.py` — raises while model id or `max_latency_ms` is unset. Does not build an `Outcome`.
- `system2/sapling.py` — scope, verdict application.
- `system2/sapling_client.py` — stub client. `SAPLING_IMPL=live` refuses before any socket.
- `mocks/sapling_stub/` — `S01`–`S05`.
- `system2/aid_exceptions.py` — separate stub. See `docs/agents/policies-api.md`.

## Interfaces/contracts

- `decide(case) -> Outcome`. `NotImplementedError` from `orchestrate` is re-raised. Sapling does not run in that case.
- Scope is `system2.sapling_scope`: `aid_eligibility,denial`. System 1 is skipped.
- Verdicts: `supported` leaves the action. `violation` sets `requires_human` and route `supervisor_escalation`. `unsure`, `missing`, `contradicted` set `requires_human`, keep the route, and append `sapling_<verdict>` to `missing_evidence`.
- Checkpoint labels: `insufficient_information` → `missing`, `inconsistent_context` → `contradicted`.
- Input cap 16,384 tokens. Over-limit and empty inputs become an unsure handoff. The client does not truncate.
- Published checkpoint id in code: `MubitLabs/banyan-sapling`. `sapling.model_id` in yaml is still unset.

## Invariants

- `system2.hosting` is `openrouter via mubit gateway`. The orchestrator does not call OpenRouter. A future `llm.complete` call still refuses non-Mubit hosts.
- `system2.use_banyan_sapling` is `true`. `sapling.client` is `stub`. Tests do not load a GPU.
- `scripts/validate.py` rejects an `Outcome(` constructor in `system2/decide.py`.
- Unknown policy/evidence/claim triples from the stub client are `unsure`, not `supported`.
- Thai text refuses while `sapling.thai_handling` is unset. Do not guess translate-versus-send.

## How to test

- `make test` — `tests/test_sapling.py`, `tests/test_gateway_and_replay.py` (System 2 raise names Melanie).
- `make replay-stubs` — includes `S01`–`S05`.
- `make validate` — five stub files, every verdict, both checks.

## Common pitfalls

- Running Sapling inside `orchestrate`. `decide` runs it after an outcome exists.
- Setting `sapling.model_id` in git. The Modal app stays refused until a human exports `SAPLING_MODEL_ID`.
- Treating `Outcome.escalate` as the Sapling handoff. That field means System 1 to System 2. Sapling sets `requires_human`.

## Open TODO_HUMAN keys

- `system2.orchestrator_model`, `system2.max_latency_ms`
- `sapling.hosting`, `sapling.gpu`, `sapling.thai_handling`, `sapling.model_id`
