---
title: Gateway and LLM client
tags: [gateway, mubit, llm, routing, memory, auth]
files:
  - gateway/route.py
  - gateway/chooser.py
  - gateway/graduation.py
  - gateway/overlay.py
  - gateway/auth.py
  - gateway/policy.py
  - llm/client.py
  - llm/openai_client.py
  - memory/adapter.py
  - config/routing.yaml
---

## Purpose

One turn: enrich, retrieve memory, record a policy pre-check, route by the field precheck. `mode: cascade` continues a System 1 escalate to System 2 in the same turn. Mubit does not reason. Chat completions go only to a Mubit host.

## Key files

- `gateway/route.py` — `handle`, `choose_system`, `_extract`. Owner: Moly.
- `gateway/chooser.py` — `choose`, `system_2_triggers`. The decided `gateway.route_chooser` (`field precheck`).
- `gateway/graduation.py` — `apply(case)` tags graduated patterns (`complex_situation`) and adds a recommendation MemoryItem after memory retrieval. Sets no priority; nothing moves to System 1.
- `gateway/auth.py` — records the auth scheme. Does not reject the request.
- `gateway/policy.py` — `precheck_notes`. Does not read medical fields or change priority.
- `memory/adapter.py` — `MEMORY_IMPL=mock` (default) or `mubit`.
- `memory/mubit.py` — raises. No network client yet.
- `llm/client.py` — `complete` (httpx). Owner: Melanie wires the call.
- `llm/openai_client.py` — registered OpenAI SDK client (`MUBIT_BASE_URL` + `MUBIT_API_KEY`).
- `gateway/overlay.py` — learned overlay (`RL_OVERLAY` opt-in): signatures, `Overlay`, `load`, `save`, `load_from_env`.
- `config/routing.yaml` — `mode: cascade` (or `exclusive`).
- `api/routes/endpoints.py` — `POST /triage`, `POST /cases/{id}/turns`.

## Interfaces/contracts

- In: `CaseState`, optional `overlay`. Out of `handle`: `RouterDecision` with `source_outcomes` = [deciding outcome, *prior]. A cascade puts `[system_2, system_1]`.
- `choose_system` returns the entry-point system via the field precheck (`route_to_system_2_if_any` in `config/escalation.yaml`). An `learned:demoted` overlay entry adds a demotion trigger. Trigger names land on the gateway trace note.
- Before enrichment, `_extract` runs `system1/extract.py` when fields are empty or `keyword_extraction` is already in `policy_flags`. Fixture cases carry hand-filled fields and are never extracted.
- `complete(messages, model, max_tokens, *, timeout, temperature, seed, reasoning)` posts to the Mubit chat URL only after the host check and `llm.provider_route` (`mubit`). Compat prefix `…/compat/openrouter/v1` maps to `…/chat/completions`. `temperature`, `seed`, and `reasoning` are sent only when set.
- `make_client()` returns `OpenAI(base_url=MUBIT_BASE_URL, api_key=MUBIT_API_KEY)`.

## Invariants

- `mode` must be `exclusive` or `cascade`. On a cascade a System 1 escalate hands the turn to System 2 with the S1 outcome as `handoff` and `overlay.recommendations[narrow]` as `recommendation`. The no-stub fallback (`missing_evidence == ["fixture_stub"]`) never cascades.
- `use_stubs=False`, or `S1_IMPL=real` / `S2_IMPL=real` on the chosen system, calls `decide()`. Config errors from `llm.complete` (missing URL, key, host) propagate as `RuntimeError`; the API maps them to HTTP 503.
- Non-fixture ids route through the precheck; with `use_stubs=True` they get the fallback escalation outcome.
- `router/merge.py` builds the `RouterDecision`. The router trace note says `router.merge ran`.
- `MUBIT_BASE_URL` must be `api.mubit.ai` or a subdomain of `mubit.ai`. `openrouter.ai` is refused.
- The client does not read `OPENROUTER_API_KEY` and does not print `MUBIT_API_KEY`.
- `llm.provider_route` is `mubit`. `system2.orchestrator_model` is `nvidia/nemotron-3-nano-30b-a3b` and `system2.max_latency_ms` is 10000. The key is never printed.

## How to test

- `make test` — `tests/test_gateway_and_replay.py`, `tests/test_architecture.py`.
- `make demo-stub` — `python -m gateway`.
- Host refusal: `tests/test_architecture.py` (`test_llm_refuses_openrouter_and_ignores_its_key`).
- Live smoke: `python scripts/smoke_mubit.py` with `.env` set (lists models; never prints the key).

## Common pitfalls

- Expecting `expected.system` to drive routing. The precheck runs for fixtures too; G01–G04 therefore route to System 2 (`rescue` is a trigger) even though their labels say system_1.
- Adding a second HTTP client for OpenRouter. `system2.hosting` is already `openrouter via mubit gateway`.
- Evaluating `config/escalation.yaml` inside `gateway/route.py`. `scripts/validate.py` fails if `fields.medical` or `oxygen_dependent` appears there.
- Printing the bearer token in an exception.

## Open TODO_HUMAN keys

- `gateway.auth`
- `memory.mubit_project`, `memory.retrieval_top_k`, `memory.token_budget`
- `llm.token_price_usd`

See also `docs/agents/rl-loop.md` for the overlay and the cascade learner.
