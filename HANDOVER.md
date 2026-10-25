# Handover

25 October 2026. `main` tip at write time: check `git rev-parse --short HEAD` (policy change landed as `bbde2f0`; this doc ships on a follow-up PR). `make test` is **272 passed, 1 skipped** (`tests/test_synthetic_calls.py` needs the `laya` module). `make validate` is ok.

`requirements.txt` includes `openai>=1.40` (audit note that it was missing is stale unless a deploy image omits the file).

## Main parts

One call goes through these parts in order. `gateway/route.py` `handle` is the entry for `POST /triage` and `POST /cases/{id}/turns`.

| Part | Where | State |
|---|---|---|
| Extraction | `system1/extract.py` | Runs when fields are empty. English keyword rules (kids/children; bare `unaccompanied` → child unless `adult` named). Thai matches **district names only**. Demo in English or code-switched. |
| Enrichment | `enrich/context.py`, `data/processed/`, snapshots | JSON/GeoJSON via `ingest.store` (SQLite is ingest cache only). Matches `districts` then `admin_districts`. Flags never change priority. |
| Memory | `memory/adapter.py` | `MEMORY_IMPL=mock`. `memory/mubit.py` raises. |
| Graduation to System 2 | `gateway/graduation.py` | Escalation threshold 2. Tags `complex_situation`; does not write System 1 rules. |
| Route chooser | `gateway/chooser.py` | `field precheck`. `routing.yaml` `mode: cascade`. |
| System 1 | `system1/decide.py` | Rules-only. Overlay only if `RL_OVERLAY` set. |
| System 2 | `system2/orchestrator.py` | Nemotron via Mubit when `S2_IMPL=real`. Stub otherwise. |
| Sapling | `system2/sapling.py` | Aid eligibility / denial. Stub client. |
| Router / ledger | `router/merge.py`, `router/ledger.py` | Provisional dispatches; confirm/cancel API; `/resources` ledger-aware. |
| Traces / metrics | `llm/client.py`, `trace.py`, `GET /metrics` | Every Mubit chat emits `mubit_chat`. RL live/cache hits too. |
| RL loop | `eval/rl/`, `ui/sim/rl_panel.js` | Live = Mubit; replay = cache; panel labels honestly. |
| UI | `ui/sim/`, `ui/correct.js` | Transcript create, dispatches, `location_context`, Mubit hop, confirm/cancel. |
| Hosting | `make serve`, `infra/modal/gateway_app.py` | Local 8000. Git has S1 real + enrich auto + `baansafe-mubit`; **hosted URL does not match git until redeploy**. No auth on corrections — judges only. |
| Training | `training/`, Modal finetune / Laya export | Exports exist. No checkpoint at inference. |

Owners: `OWNERSHIP.md`. Contracts: `v0.3-contracts`. Detail plan: `docs/wire-frontend.md` (mostly landed).

---

## Done recently (do not re-open)

| Item | Notes |
|---|---|
| Safeguarding plurals / bare unaccompanied | `0fdc34e` |
| Thai need keywords | Explicitly **reverted** — leave off unless product reopens |
| PR 9 town landmarks / pace / session | Merged |
| Town wire P0 | Transcript `POST /cases`, `ruleFromDispatches`, `location_context`, stale TODO copy fixed (`f65ab55`) |
| Dispatch confirm/cancel + ledger stock | API + town Accept/Reject wired |
| Mubit `mubit_chat` traces + enrich/memory stages + `/metrics` | `96bef6e`, `7d1eddc` |
| RL Mubit/cache traces + RL panel | `c996c35` / related; panel `f243e2b` |
| Modal S1 real + enrich auto + mubit secret / S2 gate | `b2275c6`, `c996c35` |
| `data.demo_event` = Hat Yai / Songkhla; G01–G04 → system_2 | `110e370` |
| Correct this Mubit→Nemotron line | `61663d0` |
| Enrich `admin_districts` fallback | Hat Yai resolves |
| Unaccompanied adult ≠ child | Bare `unaccompanied` still implies child; `adult` named does not |

---

## Judge audit (25 Oct) — context for both owners

External pass did **not** boot the API or make live Mubit calls; endpoints on the hosted URL are unchecked until A1–A2.

### Still true / hold the line
- Every LLM call goes through Mubit (`llm/client.py`); no ReliefWeb / DDPM; synthetic people only.
- Architecture still *promises* Mubit memory, Sapling verifier, and model-based System 1 — runtime today: **memory stub**, **Sapling stub**, **S1 rules-only**. Pitch Mubit as **gateway + traces**, not memory, unless Melanie lands the three `memory.*` decisions tonight.
- `config/decisions.yaml` still has many `TODO_HUMAN` leaves (~33 outside `DECIDED`).
- High churn on `ui/sim/sim.js` in the last hours — prefer one writer per PR (branch → PR → merge).

### Risks called out
| Risk | Mitigation |
|---|---|
| Hosted URL ≠ git | Redeploy Modal; smoke `/metrics` |
| Hat Yai event vs Sukhumvit town vs northern calls | No flood in demo until place lines up |
| Live Nemotron: ~3/6 fixtures, rate limits | Script S2 with rules safety gate; keep `make rl-loop-replay` cache ready |
| Two learning stories | Freeze **corrections escalate to System 2** |
| Unaccompanied adult → child | Treat as bug; do not imply child when `adult` is named |
| Thai extract = districts only | Demo English / code-switched |
| Stock holds | Pin Modal to **one** container |
| Aid 501 + RL panel noise | **Hide** from demo UI for the script |

### Next 5 (in order) — both owners

1. **Redeploy Modal** and run a Mubit check on the live URL (`GET /hosting`, one System 2 turn, `GET /metrics` → `mubit_chat`). Share the link **only with judges** (no auth).
2. **Line up place on Hat Yai** — move town pins + one fixture set to Songkhla/Hat Yai, *or* change `data.demo_event` back if the basemap stays Sukhumvit.
3. **Freeze the ~3-minute script:** English System 1 call → System 2 escalation through Mubit (rules safety gate visible) → human confirm dispatch → graduation (correction path to S2). Keep RL replay cache warm; do not depend on live nano for the scripted beat.
4. **Settle Mubit memory** (Melanie: `memory.mubit_project`, `retrieval_top_k`, `token_budget` + wire) **or** reword all pitch/docs to “gateway + traces”.
5. **Keep HANDOVER tip SHA / test counts fresh** after each merge; confirm deploy image installs `requirements.txt` (includes `openai>=1.40`).

### Same-night smaller fixes
- Hide aid eligibility UI and RL panel for the demo path.
- Pin Modal concurrency / replicas to 1 for ledger holds.
- Unaccompanied adult must not get `vulnerable: child` (see extract fix on this PR if merged).

## Plan of action (full backlog)

### After the Next 5
| # | Action |
|---|---|
| B3 | Widen flood buffer / district-area match |
| B4 | Weather for admin-only district matches |
| C1 | Post-hackathon: `gateway.auth` |
| C3 | Optional: ship `eval/out/rl/run.json` on Modal volume |
| D2–D3 | Live Sapling / STT when decisions set |
| E1–E4 | Laya train / classifier product decision / finetune / refresh nano RL cache |
| F1–F2 | Thai keywords / Thai UI labels only if product reopens |
| G1–G8 | Map consumers, disaster_report, snapshot age, routes.yaml, district lists, aid 501, countries, markdown housekeeping |

### Branch policy
Branch → PR → merge to `main` when `make test` / `make validate` green. Do not push feature work straight to `main`.

---

## Live System 2

Model: `nvidia/nemotron-3-nano-30b-a3b` via Mubit (`system2.hosting` = openrouter via mubit gateway). Local: `S2_IMPL=real` + `.env` keys. Hosted: real only when Modal secret injects `MUBIT_API_KEY` + `MUBIT_BASE_URL`. Traces: stage `mubit_chat` on `TRACE_PATH` / case trace / `GET /metrics`.

RL: `make rl-loop` (live, spends quota) · `make rl-loop-replay` (cache; misses = fallbacks until cache rebuilt for current model).

Architecture walk-through: `BaanSafe_Revised_Architecture.md`.

## Laya Model Training Pipeline

Export + skip-safe train wrapper ready. System 1 stays **rules-only** until a product decision wires a checkpoint.

| Action | Command |
|---|---|
| Export | `make export-laya` → ~168 train / 72 held |
| Train | `LAYA_TRAIN=1 make laya-train` (GPU or Modal task + `laya-train` on PATH) |
| Not Laya | `make modal-finetune` = event-log SetFit/LoRA (`modal.finetune_base_model`) |

Open: `modal.s1_model_id`, `modal.s1_gpu`, `modal.finetune_base_model`.

## latte-bench

Submodule present; `bun` often missing → `make latte-bench` skips. Live mode needs Mubit keys. License confirmation still `TODO_HUMAN`.

## Housekeeping

- Markdown moves / gitignore (`.vscode/`, `*.log`) approved, not fully done → G8.
- PRD auto-refresh: rebase before push.
- Multi-agent thrash happened on 24–25 Oct; prefer one writer on `ui/sim/sim.js` and `llm/client.py` at a time.
- **Repo policy (updated):** branch → PR → merge to `main` when `make test` / `make validate` are green. Do not push feature work straight to `main`. Delete merged remote branches (e.g. leftover `origin/cursor/*`).
- Local `.env`: `S1_IMPL=real`. Restart `make serve` after env changes.
