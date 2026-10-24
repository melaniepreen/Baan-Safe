# Agent topic index

Machine-readable list: `docs/agents/index.json`. `AGENTS.md` is the always-loaded core. This file is not a copy of it.

| Doc | Summary |
|---|---|
| `docs/agents/gateway-and-llm-client.md` | Exclusive System 1 or System 2 route, memory adapter, and the Mubit-only chat client. |
| `docs/agents/system1.md` | Fast-path stubs: triage `decide()` raises, and aid eligibility does not approve a payment. |
| `docs/agents/system2-and-sapling.md` | Nemotron orchestrator stub, then the Sapling verifier on aid eligibility and denial. |
| `docs/agents/policies-api.md` | Policy corpus is GET/POST `/policies`. Aid eligibility and exceptions still return 501. |
| `docs/agents/decision-router.md` | `merge()` raises. The stub gateway copies one outcome and does not call it. |
| `docs/agents/correction-loop-and-evals.md` | Held-out eval splits on group_id. Arm C reads human rows. C_coach also reads coach. |
| `docs/agents/rl-loop.md` | Reward loop over the cascade: graduation, recommendations, demotion, shadow bandit. |
| `docs/agents/training-schema.md` | TrainingEvent v1. Corrections, coach, and sim append to one log. export-training reads it. |
| `docs/agents/caller-simulation.md` | Scripted callers. Coach and the simulator append TrainingEvents with source coach and sim. |
| `docs/agents/data-ingest.md` | Public sources into SQLite. ReliefWeb sends no request. DDPM was not added. |
| `docs/agents/modal-infra.md` | Fine-tune takes one dataset per task. s1_triage uses SetFit. Other tasks use LoRA. |
| `docs/agents/config-and-decisions.md` | `decisions.yaml` fails loud on `TODO_HUMAN`. Ten leaves are allowlisted in `DECIDED`. |
| `docs/agents/testing.md` | `make test` is pytest. `make validate` scans fixtures, decisions, stubs, and these docs. |
| `docs/agents/frontend.md` | Correct this fills task and input_ref. The operator picks the closed label and a reason. |
