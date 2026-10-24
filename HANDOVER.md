# Handover

24 October 2026, evening. `main` is at `7004cee`. `make test` is 232 passed, 1 skipped (`tests/test_synthetic_calls.py` needs the `laya` module). `make validate` is ok. Every number below was measured on that commit.

## Main parts

One call goes through these parts in order. `gateway/route.py` `handle` is the entry for `POST /triage` and `POST /cases/{id}/turns`.

| Part | Where | State |
|---|---|---|
| Extraction | `system1/extract.py` | Runs only when a case arrives with empty fields. English keyword rules, the 108-district gazetteer (`admin_districts`), caller-confirmed operator facts. Thai matches district names only. |
| Enrichment | `enrich/context.py`, `data/snapshots/` | Adds flood, rain, and reservoir flags from SQLite and the public snapshots. Flags never change priority or route. |
| Memory | `memory/adapter.py` | `MEMORY_IMPL=mock` reads `mocks/memory_context/`. `memory/mubit.py` raises. |
| Graduation to System 2 | `gateway/graduation.py` | `correction_loop.escalation_threshold` 2. Two human `s1_triage` corrections with a high-risk label on one field pattern tag it `complex_situation` and send it to System 2 with a recommendation. Never sets a priority. `make demo-graduation`. |
| Route chooser | `gateway/chooser.py`, `config/escalation.yaml` | `field precheck`. `routing.yaml` is `mode: cascade`: a System 1 escalate hands the same turn to System 2. |
| System 1 | `system1/decide.py` | Rules-only needs table, duplicate check, confidence floor 0.80. Learned rules from the RL overlay apply only when `RL_OVERLAY` names a file. |
| System 2 | `system2/decide.py`, `system2/orchestrator.py` | Live Nemotron (`nvidia/nemotron-3-nano-30b-a3b`) through the Mubit compat route when `S2_IMPL=real`. Stub outcomes otherwise. Outages become a safe `system2_unavailable` escalation. |
| Sapling | `system2/sapling.py` | Aid eligibility and denial only. Stub client (`mocks/sapling_stub/`). |
| Router | `router/merge.py`, `router/ledger.py` | Next action, one provisional dispatch per need, in-process stock holds. |
| RL loop | `eval/rl/`, `gateway/overlay.py`, `ui/sim/rl_panel.js` | `correction_loop.graduation_threshold` 2. Graduates repeated System 2 decisions into System 1 rules, demotes coarse ones. `make rl-loop` (spends quota), `make rl-loop-replay` (cached). |
| Training export | `training/`, `infra/modal/finetune_job.py` | Event log to per-task datasets, SetFit for `s1_triage`, Laya export. No trained checkpoint is used at inference. |
| UI | `ui/sim/`, `ui/player.html`, `ui/correct.js` | Town, phone, RL panel, Correct this. |
| Hosting | `make serve`, `infra/modal/gateway_app.py` | Local API on port 8000. `make deploy-modal` serves one public URL with stub settings. |
| Evals | `eval/extract_eval.py` | `make extract-eval`: fixtures 24/24 routes, 0 unsafe. Held-out sim callers 4/7 routes, 0 unsafe. `EXTRACT_EVAL_SET=synthetic make extract-eval` scores the 240 synthetic calls. |

Owners stay as in `OWNERSHIP.md`. Contracts are `v0.3-contracts`.

## Gaps, in priority order

"Unsafe" means the true fields send the call to System 2, but System 1 answered with no human.

### Safety

1. **Plural children are missed.** "My two kids are alone at a shelter. They are unaccompanied." extracts no vulnerable person, because `VULNERABLE_PHRASES` in `system1/extract.py` matches `kid` and `child` but not `kids` or `children`. Without `child`, the safeguarding flag never fires. 6 synthetic safeguarding calls are unsafe: they get a P3 shelter dispatch from System 1 with no human (`syn-safeguarding-child-01/02/04/05-en`, `-01/05-mixed`). Fix: add the plurals, and treat "unaccompanied" alone as a child alone.
2. **The hosted write endpoints have no auth.** `gateway.auth` is `TODO_HUMAN`. On the public Modal URL, `POST /cases/{id}/corrections` writes human training events, so two posts graduate a pattern. This is accepted for the hackathon. Share the URL only with judges.

### Unused potential

3. **Thai callers get no fast path.** The extractor has no Thai keywords. On the 80 Thai synthetic calls: needs 0/80, routes 38/80. None are unsafe, only because empty needs escalate to a supervisor, so every Thai caller reaches a human. `research/glossary-and-risk-areas.md` already lists about 40 Thai flood words and caller phrases, and `admin_districts.name_th` already gives Thai location (72/80).
4. **The demo never runs the extractor.** `ui/sim/sim.js` posts `{ fixture_id: call.id }` to `POST /cases`, so spoken text never reaches extraction, the gazetteer, or caller-confirmed facts. `POST /cases` already accepts a transcript with empty fields.
5. **The hosted demo shows stubs.** `infra/modal/gateway_app.py` `STUB_ENV` sets `S1_IMPL=stub` and `ENRICH_IMPL=off`. The real System 1 needs no secret.
6. **Dispatches are invisible.** `sim.js` never reads `RouterDecision.dispatches`. With no district match, `mocks/loader.load_dispatch_resources` lists OpenStreetMap units first, so the router reserves a unit such as `shelter-way-{osm_id}` that the town cannot draw. `GET /resources` ignores the ledger and shows full stock.
7. **A human cannot confirm or cancel a dispatch.** There is no endpoint for it. Holds are released only when the same case is decided again. There is no case close.
8. **Mubit memory is not wired.** Mubit is used only as the LLM hop. `research/MUBIT.md` lists the `/v2/control/` ingest and query endpoints. Blocked on `memory.mubit_project`, `memory.retrieval_top_k`, and `memory.token_budget` (Melanie).
9. **Trained models are never used.** SetFit and Laya exports and the Modal System 1 classifier (`infra/modal/s1_app.py`) exist, but System 1 is rules-only and nothing loads a checkpoint. A classifier second opinion would help Thai most.

### Consistency

10. **Two graduation paths disagree.** Correction graduation (`gateway/graduation.py`) never moves a pattern into System 1. The RL loop (`eval/rl/learner.py` with `RL_OVERLAY`) writes System 1 rules. A person should confirm which story the demo tells. An agent also set `routing.yaml` `mode: cascade` and `system2.max_latency_ms`, and AGENTS.md invariant 2 says humans set decisions. Moly chose `system2.orchestrator_model` `nvidia/nemotron-3-nano-30b-a3b` on 24 Oct 2026.
11. **The town shows outdated text.** `sim.js` still says `gateway.route_chooser` and `system2.orchestrator_model` are `TODO_HUMAN`. `ui/sim/data/sim_events.json` `learning.promote_after` is 3 and tells a promote-into-System-1 story.
12. **`G01`–`G04` labels still say System 1.** `rescue` sends them to System 2. `mocks/s2_stub/G01.json` still says "pending correction_loop.graduation_threshold". Relabel them or change their need.
13. **Modal limits.** `GET /rl/run` is 404 there because `.dockerignore` excludes `eval/out`. Stock holds live in one container's memory.
14. **The map and the data are different places.** The town draws Sukhumvit, Watthana. Fixtures and `data/snapshots/places.json` are Lampang, Phrae, Nan, and Phayao. `data.demo_event` is `TODO_HUMAN`.
15. **Ownership.** `9da21c7` changed Melanie's `system2/orchestrator.py` and `system2/decide.py`. Melanie should review them.

## Live System 2

System 2 runs `nvidia/nemotron-3-nano-30b-a3b`, the paid tier, through Mubit. It replaced `nvidia/nemotron-3.5-lightning:free`. OpenRouter's 50-a-day free cap covers every `:free` model on the account, and today's cap was spent. On 24 Oct 2026, nano answered 6 fixture prompts in 1.1–1.7 s. 3 of the 6 matched the fixture priority and route. C01-a came back P2 welfare where P1 rescue was expected. A call costs about $0.0003 (the OpenRouter list price is $0.06 per million input tokens and $0.24 per million output tokens).

The RL replay cache (`eval/out/rl/s2_cache.jsonl`) is keyed by model. Until `make rl-loop` runs live with nano, `make rl-loop-replay` misses every entry and scores them as fallbacks. `run.json` now records `model`.

The full routing walk-through, the loops, and the Modal status are in `BaanSafe_Revised_Architecture.md` under "Routing in detail".

## Housekeeping

- **Markdown cleanup is approved but not done.**
  - Untrack and gitignore `MORNING_REPORT.md`, `research/DEMO_PLAN.md`, and `docs/agents/INDEX.md`.
  - Move `BaanSafe_Revised_Architecture.md` to `docs/architecture.md`, `OWNERSHIP.md` to `docs/OWNERSHIP.md`, and `research/` to `docs/research/`, then update every reference.
  - Add `.vscode/` and `*.log` to `.gitignore`.
  - Point the Cursor refresh agent at `docs/architecture.md` afterwards.
- The Cursor Agent refreshes `docs/PRD.md` after pushes, at most every 30 minutes. Rebase before a push.
- Several agents have worked in this folder at once. Check `git status` and `git stash list` before starting.
- The local `.env` has `S1_IMPL=real`. Restart `make serve` after changing it.
