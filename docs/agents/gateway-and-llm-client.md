---
title: Gateway and LLM client
tags: [gateway, mubit, llm, routing, memory, auth]
files:
  - gateway/route.py
  - gateway/auth.py
  - gateway/policy.py
  - llm/client.py
  - memory/adapter.py
  - config/routing.yaml
---

## Purpose

One turn: enrich, retrieve memory, record a policy pre-check, route to System 1 or System 2. Mubit does not reason. Chat completions go only to a Mubit host.

## Key files

- `gateway/route.py` — `handle`, `choose_system`. Owner: Moly.
- `gateway/auth.py` — records the auth scheme. Does not reject the request.
- `gateway/policy.py` — `precheck_notes`. Does not read medical fields or change priority.
- `memory/adapter.py` — `MEMORY_IMPL=mock` (default) or `mubit`.
- `memory/mubit.py` — raises. No network client yet.
- `llm/client.py` — `complete`. Owner: Melanie wires the call.
- `config/routing.yaml` — `mode: exclusive`.
- `api/routes/endpoints.py` — `POST /triage`, `POST /cases/{id}/turns`.

## Interfaces/contracts

- In: `CaseState`. Out of `handle`: `RouterDecision` with one `source_outcomes` entry.
- `choose_system` returns `system_1` or `system_2`. Fixture ids use `expected.system`. That lookup is a harness stand-in, not a product rule.
- `complete(messages, model, max_tokens)` posts to `{MUBIT_BASE_URL}/openai/v1/chat/completions` only after the host check and `llm.provider_route`.

## Invariants

- Exclusive route. `mode` other than `exclusive` raises. The gateway does not call both systems.
- `use_stubs=False`, or `S1_IMPL=real` / `S2_IMPL=real` on the chosen system, calls `decide()` and lets `NotImplementedError` through.
- A case id that is not a fixture raises while `gateway.route_chooser` is unset. The API returns HTTP 501.
- `router/merge.py` is not called. The trace note says so.
- `MUBIT_BASE_URL` must be `api.mubit.ai` or a subdomain of `mubit.ai`. `openrouter.ai` is refused.
- The client does not read `OPENROUTER_API_KEY` and does not print `MUBIT_API_KEY`.
- A set URL still does not leave the process while `llm.provider_route` is `TODO_HUMAN`.

## How to test

- `make test` — `tests/test_gateway_and_replay.py`, `tests/test_architecture.py`.
- `make demo-stub` — `python -m gateway`.
- Host refusal: `tests/test_architecture.py` (`test_llm_refuses_openrouter_and_ignores_its_key`).

## Common pitfalls

- Treating `expected.system` as the live router. It is fixture-only.
- Adding a second HTTP client for OpenRouter. `system2.hosting` is already `openrouter via mubit gateway`.
- Evaluating `config/escalation.yaml` inside `gateway/route.py`. `scripts/validate.py` fails if `fields.medical` or `oxygen_dependent` appears there.
- Printing the bearer token in an exception.

## Open TODO_HUMAN keys

- `gateway.route_chooser`
- `gateway.auth`
- `memory.mubit_project`, `memory.retrieval_top_k`, `memory.token_budget`
- `llm.provider_route`, `llm.token_price_usd`
