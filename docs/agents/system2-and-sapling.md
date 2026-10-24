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

Nemotron reasons. Sapling then checks System 2 aid-eligibility and denial claims. The Decision Router sees the result. `system2.orchestrator_model` and `system2.max_latency_ms` are decided, so `orchestrate` calls the model through `llm.complete`.

## Key files

- `system2/decide.py` — `orchestrate(case, handoff, recommendation)`, then `verify_before_router`. Owner: Melanie.
- `system2/orchestrator.py` — prompts Nemotron, parses one JSON object into `reasoned_recommendation`, falls back to a safe `system2_unavailable` outcome on timeout, HTTP error, empty content, or parse/enum failure. `use_completer(fn)` swaps the model call for tests and the RL loop. The call sends `reasoning={"enabled": false}` and `max_tokens=700`: the model otherwise spends its whole budget on `<think>`.
- `system2/sapling.py` — scope, verdict application.
- `system2/sapling_client.py` — stub client. `SAPLING_IMPL=live` refuses before any socket.
- `mocks/sapling_stub/` — `S01`–`S05`.
- `system2/aid_exceptions.py` — separate stub. See `docs/agents/policies-api.md`.

## Interfaces/contracts

- `decide(case, handoff=None, recommendation=None) -> Outcome`. The handoff is the System 1 outcome on a cascade; the recommendation is a learned rule System 2 may weigh. `NotImplementedError` from `orchestrate` is re-raised; Sapling does not run in that case.
- Scope is `system2.sapling_scope`: `aid_eligibility,denial`. System 1 is skipped.
- Verdicts: `supported` leaves the action. `violation` sets `requires_human` and route `supervisor_escalation`. `unsure`, `missing`, `contradicted` set `requires_human`, keep the route, and append `sapling_<verdict>` to `missing_evidence`.
- Checkpoint labels: `insufficient_information` → `missing`, `inconsistent_context` → `contradicted`.
- Input cap 16,384 tokens. Over-limit and empty inputs become an unsure handoff. The client does not truncate.
- Published checkpoint id in code: `MubitLabs/banyan-sapling`. `sapling.model_id` in yaml is still unset.

## Invariants

- `system2.hosting` is `openrouter via mubit gateway`. The orchestrator does not call OpenRouter; `llm.complete` refuses non-Mubit hosts and never prints the key. Hard post-rules force `requires_human` on a `safeguarding` flag, an aid need, or aid flags.
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

- `sapling.hosting`, `sapling.gpu`, `sapling.thai_handling`, `sapling.model_id`
