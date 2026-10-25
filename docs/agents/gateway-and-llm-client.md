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
  - memory/local.py
  - memory/mubit.py
  - config/routing.yaml
---

## Purpose

One turn: enrich, retrieve memory, record a policy pre-check, route by the field precheck. `mode: cascade` continues a System 1 escalate to System 2 in the same turn. Mubit does not reason. Chat completions go only to a Mubit host.

## Key files

- `gateway/route.py` — `handle`, `choose_system`, `_extract`. Owner: Moly.
- `gateway/chooser.py` — `choose`, `system_2_triggers`. The decided `gateway.route_chooser` (`field precheck`).
- `gateway/graduation.py` — `apply(case)` tags graduated patterns (`complex_situation`) and adds a recommendation MemoryItem after memory retrieval. Sets no priority; nothing moves to System 1.
- `gateway/auth.py` — records the auth scheme. Does not reject the request.
- `gateway/policy.py` — `precheck_notes(triggers)`: records which `config/escalation.yaml` System 2 triggers fired. Does not read medical fields or change priority.
- `memory/adapter.py` — `MEMORY_IMPL=mock` (default), `local` (hosted default), or `mubit`. `memory_mode`, `retrieve`, `store_correction`, `store_record` (no-op in mock mode, returns `False`), `last_retrieve_error`.
- `memory/local.py` — BaanSafe's own store when `MEMORY_IMPL=local`: append-only JSONL at `MEMORY_LOCAL_PATH` (default `var/memory.jsonl`), written under an exclusive file lock, scored on read. Lanes: `baansafe-case` → `similar_case`, `baansafe-correction` → `correction`, `baansafe-policy` → `policy`.
- `memory/mubit.py` — control-plane client (`/v2/control/query`, `/v2/control/ingest`) when `MEMORY_IMPL=mubit`. `MUBIT_CONTROL_URL` (a `mubit.ai` host) overrides the origin. Dormant: current Mubit is an LLM gateway and returns 404 `unknown_route` for `/v2/control/*`, so this backend returns no items until Mubit exposes a memory API. Same lanes as local.
- `scripts/seed_memory.py` — `make seed-memory` writes 10 corpus-derived items tagged `[policy:<rule_id>]` into lane `baansafe-policy` through the adapter (`MEMORY_IMPL=local` seeds the JSONL file; `mubit` ingests); items already present by tag are skipped. `SEED_ARGS='--dry-run'` prints without writing; `--case-fact CASE_ID` adds one synthetic fact; `--path FILE` overrides `MEMORY_LOCAL_PATH`.
- `scripts/mubit_traffic.py` — `make mubit-traffic COUNT=n SEED=s` (needs `.env`) builds `n` deterministic variants of the synthetic fixtures (invented name, Watthana soi, people count, depth, floor), runs each through `gateway.route.handle` with `S1_IMPL=real S2_IMPL=real MEMORY_IMPL=mock`, and prints a JSON summary of Mubit hops (`mubit_chat`, status counts, `distinct_sessions`). Each case gets its own `metadata.session_id`, so Mubit's task gains distinct examples and distinct held-out sessions. `TRAFFIC_ARGS='--dry-run'` prints the variants and opens no socket.
- `llm/client.py` — `complete` (httpx). Owner: Melanie wires the call.
- `llm/openai_client.py` — registered OpenAI SDK client (`MUBIT_BASE_URL` + `MUBIT_API_KEY`).
- `gateway/overlay.py` — learned overlay (`RL_OVERLAY` opt-in): signatures, `Overlay`, `load`, `save`, `load_from_env`.
- `config/routing.yaml` — `mode: cascade` (or `exclusive`).
- `api/routes/endpoints.py` — `POST /triage`, `POST /cases/{id}/turns`.

## Interfaces/contracts

- In: `CaseState`, optional `overlay`. Out of `handle`: `RouterDecision` with `source_outcomes` = [deciding outcome, *prior]. A cascade puts `[system_2, system_1]`.
- `choose_system` returns the entry-point system via the field precheck (`route_to_system_2_if_any` in `config/escalation.yaml`). An `learned:demoted` overlay entry adds a demotion trigger. Trigger names land on the gateway trace note.
- Before enrichment, `_extract` runs `system1/extract.py` when fields are empty or `keyword_extraction` is already in `policy_flags`. Fixture cases carry hand-filled fields and are never extracted.
- `complete(messages, model, max_tokens, *, timeout, temperature, seed, reasoning, case_id)` posts to the Mubit chat URL only after the host check and `llm.provider_route` (`mubit`). Compat prefix `…/compat/openrouter/v1` maps to `…/chat/completions`. `temperature`, `seed`, and `reasoning` are sent only when set. When `case_id` is set the body carries `metadata.session_id=<case_id>`: Mubit groups a conversation's calls into one session by that field and holds adapter test cases out by session, so a case's turns stay together and held-out tests are other cases. Every call sends `x-middleware-record: full` so Mubit keeps the request and the answer (the default, made explicit). Never send `x-middleware-store: false` or `x-middleware-record: metadata|off`; a call recorded without request and reply is never a kept example. Every socket attempt emits TraceEvent stage `mubit_chat` (model, `latency_ms`, `notes` with `status=ok` / `status=http_429` / other). Config refusals before a socket do not emit.
- `make_client()` returns `OpenAI(base_url=MUBIT_BASE_URL, api_key=MUBIT_API_KEY)`. `openai_client.chat` is the SDK path with the same `mubit_chat` emit.
- `handle` emits `enrich`, `memory`, `gateway`, system stage(s), `router`, and (local or mubit mode) `memory_write`. S2 real path: `mubit_chat` from `llm.complete`, then `system_2`. The `memory` note is `memory via adapter mode=<impl>; items=N`, plus `; retrieve_error=<type: text>` when a local or mubit retrieve soft-failed to `[]` (never the key).
- Memory write path: after `router.merge`, `handle` → `_write_memory` builds a `MemoryRecord` (`evidence=case.fields`, `decision`, `corrections` passed in by the API from `StoredCase.corrections`; no transcript, no `resources`) and calls `store_record`. Not in mock mode; skipped for the no-stub fallback. Soft-fails: the stage note is `status=ok|error; kind=case_record; mode=<impl>; lane=baansafe-case; corrections=N` (`error=<ExceptionType>` on failure, never the message or key). A correction's `memory_write` note from `store_correction` is `status=ok|error; kind=correction; mode=<impl>; id=<id>; <detail>`; on a failed local or mubit write the correction is kept in the local correction log.
- Record content is `"Case <id>: needs=…; location=…; people=…; decision=…; route=…; priority=…"` (`memory.content.record_content`). `memory/local.py` appends `{id, kind, lane, content, source_case_id, location, needs, vulnerable, danger, priority, route, next_action, created_at, metadata}`; `memory.mubit.write` ingests `{type: fact, content, lane: baansafe-case, source_case_id, metadata: {source_case_id, lane, record_id, location, needs, route, priority, next_action}}`. On read `source_case_id` comes from the top-level field, then `metadata`, then the `Case <id>:` prefix; `run_id` is never used. A `similar_case` row for the case being triaged is dropped so turn 2 cannot duplicate-merge on itself.
- Local scoring per row: +3 when a normalised location token overlaps (lower-case, punctuation stripped), +2 per overlapping need, +1 per overlapping vulnerable or danger token, +1 for a `baansafe-policy` or `baansafe-correction` row whose content mentions one of the case's needs or flags; rows with `source_case_id == case.case_id` are excluded. Rows scoring 0 are dropped. `relevance = max(0.5, min(1, score / 6))`; a same-location row with one overlapping need scores 5 and is clamped to `DUPLICATE_RELEVANCE` (0.9) so a repeat caller duplicate-merges. Top `memory.retrieval_top_k` (5) returned.
- `GET /metrics` includes `mubit_chat.call_count`, `ok_count`, `error_count`, `avg_latency_ms`, and `models` so a judge can see hops through Mubit, and a `memory` block from the same traces: `mode`, `retrieve_count`, `hit_count` (memory stage with `items>=1`), `item_total`, `hit_rate`, `write_count`, `write_error_count`, `avg_write_latency_ms`, `duplicate_merge_count` (`system_1` outcomes routed `duplicate_merge`).
- What Mubit does with those calls (docs.mubit.ai, read 25 Oct 2026): records each as a Request, groups calls with the same model + system instructions + tools + output format into one Task, keeps eligible examples, trains a per-task adapter at ~25 kept examples, tests each version against the provider model's answers on held-out sessions, and exposes a `Passed` version in the console's Try models. System 2's system prompt is static and all per-case data is in the user message, so every System 2 call lands in one Task. There is no Mubit model id: an adapter cannot be called from the live path. Mubit has no memory API in the current product; see the memory section.

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
- Live smoke: `python scripts/smoke_mubit.py` with `.env` set (lists models; never prints the key). Optional connectivity check only; chat tracing is covered by unit tests that mock httpx.
- Mubit chat traces: `tests/test_mubit_trace.py` (mocked httpx; no live network).
- Memory client and the write path: `tests/test_mubit_memory.py` (mocked httpx: ingest shape, lane → kind, self-case exclusion, mock no-op), `tests/test_memory_write.py` (API turn with `MEMORY_IMPL=mubit`, `memory_write` stage, `/metrics` `memory` block), and `tests/test_memory_local.py` (JSONL round trip, scoring order, own-case exclusion, repeat-caller `duplicate_merge` through the API with `MEMORY_IMPL=local`).

## Common pitfalls

- Expecting `expected.system` to drive routing. The precheck runs for fixtures too; G01–G04 are labelled `system_2` because `rescue` is a `needs_any` trigger.
- Adding a second HTTP client for OpenRouter. `system2.hosting` is already `openrouter via mubit gateway`.
- Evaluating `config/escalation.yaml` inside `gateway/route.py`. `scripts/validate.py` fails if `fields.medical` or `oxygen_dependent` appears there.
- Printing the bearer token in an exception.

## Open TODO_HUMAN keys

- `gateway.auth`
- `llm.token_price_usd`

`memory.mubit_project` (`baansafe-demo`), `memory.retrieval_top_k` (`5`), and `memory.token_budget` (`400`) are decided. Override the project with `MUBIT_PROJECT_ID` when the console id differs. Developer default `MEMORY_IMPL` stays `mock`. The Modal gateway sets `MEMORY_IMPL=local` and `MEMORY_LOCAL_PATH=/data/memory.jsonl` on the `baansafe-demo` volume (next to `TRACE_PATH`); `/hosting` reports `memory: local`. Run `MEMORY_IMPL=local make seed-memory` so the store holds the policy lessons, and read the `memory` trace note: `items=0` with a `retrieve_error` means the store was not read, not that it is empty.

See also `docs/agents/rl-loop.md` for the overlay and the cascade learner.
