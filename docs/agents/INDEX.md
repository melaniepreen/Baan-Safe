# Agent topic index

Machine-readable list: `docs/agents/index.json`. `AGENTS.md` is the always-loaded core. This file is not a copy of it.

| Doc | Summary |
|---|---|
| `docs/agents/gateway-and-llm-client.md` | Exclusive System 1 or System 2 route, memory adapter, and the Mubit-only chat client. |
| `docs/agents/system1.md` | Fast-path stubs: triage `decide()` raises, and aid eligibility does not approve a payment. |
| `docs/agents/system2-and-sapling.md` | Nemotron orchestrator stub, then the Sapling verifier on aid eligibility and denial. |
| `docs/agents/policies-api.md` | Policy corpus is GET/POST `/policies`. Aid eligibility and exceptions still return 501. |
| `docs/agents/decision-router.md` | `merge()` raises. The stub gateway copies one outcome and does not call it. |
| `docs/agents/correction-loop-and-evals.md` | Stub correction loop, held-out learning scoreboard, and latte-bench by reference. |
| `docs/agents/data-ingest.md` | Public sources into SQLite. ReliefWeb sends no request. DDPM was not added. |
| `docs/agents/modal-infra.md` | Modal apps refuse while GPU and model ids are `TODO_HUMAN`. No secrets in git. |
| `docs/agents/config-and-decisions.md` | `decisions.yaml` fails loud on `TODO_HUMAN`. Four leaves are allowlisted in `DECIDED`. |
| `docs/agents/testing.md` | `make test` is pytest. `make validate` scans fixtures, decisions, stubs, and these docs. |
| `docs/agents/frontend.md` | `ui/transcript_player.py` plays fixtures. `frontend-prototype/` is static and left alone. |
