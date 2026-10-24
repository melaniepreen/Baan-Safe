# Handover

25 October 2026, early morning. `main` is at `61663d0`. `make test` is 271 passed, 1 skipped (`tests/test_synthetic_calls.py` needs the `laya` module). `make validate` is ok.

## Main parts

One call goes through these parts in order. `gateway/route.py` `handle` is the entry for `POST /triage` and `POST /cases/{id}/turns`.

| Part | Where | State |
|---|---|---|
| Extraction | `system1/extract.py` | Runs when fields are empty. English keyword rules (incl. kids/children/unaccompanied → safeguarding). Thai matches **district names only** (need/danger keywords were added then reverted). Gazetteer: `admin_districts` + `districts` + snapshot. |
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
| Hosting | `make serve`, `infra/modal/gateway_app.py` | Local 8000. Modal: S1 real + enrich auto; `baansafe-mubit` attached; S2 real only when creds present. **Redeploy required** for live URL. |
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

---

## Plan of action

Ordered for demo truth → hosted live → product depth. Each row is one work package.

### P0 — Make the public demo match git (ops)

| # | Action | Owner hint | How |
|---|---|---|---|
| A1 | **Redeploy Modal gateway** | shared | `make modal-secrets` (if keys changed) then `make deploy-modal`. Confirm `GET /hosting`: `backends` `s1-real` or `live`, `secrets` true when Mubit present, note starts with LLM via Mubit. |
| A2 | **Smoke Mubit on hosted URL** | shared | One S2 fixture turn; `GET /cases/{id}/trace` shows `mubit_chat`; `GET /metrics` `mubit_chat.call_count` > 0. Never log keys. |
| A3 | **Share URL only with judges** | shared | `gateway.auth` still unset — corrections can graduate patterns. |

### P1 — Align place and story (product + small code)

| # | Action | Why | How |
|---|---|---|---|
| B1 | **Pick one learning story and freeze copy** | Three paths still exist (correction→S2, RL→S1 rules, stub model versions) | Choose: (1) demo = correction escalation to S2 only, or (2) RL_OVERLAY graduation. Update `sim_events` / README / architecture note so they do not contradict. Human confirms cascade / latency already in yaml if needed. |
| B2 | **Move calls or town to Songkhla / Hat Yai** | `demo_event` is Hat Yai but fixtures/town often still north/Sukhumvit → enrich stays dry | Either relocate a demo fixture set + town pins to Songkhla, or change basemap; then flood polygons / facilities show in desk. |
| B3 | **Widen flood match or use district area** | Thepha-style false dry | Buffer / polygon-in-district in `enrich/context.py`; add a fixture that lights `near_flood_extent`. |
| B4 | **Weather for admin-only districts** | Gauges keyed to 50 `districts` ids | Map admin match → nearest `districts` location_id, or extend weather rows. |

### P2 — Hosted hardening

| # | Action | Why | How |
|---|---|---|---|
| C1 | **Decide `gateway.auth`** | Open write on public URL | Hackathon: keep open + judge-only URL. After: reject unauthenticated corrections. |
| C2 | **Persist ledger / cases across replicas** | In-process holds; Modal multi-container | Single container or volume/DB for ledger + case store (PRD open item). |
| C3 | **RL artifacts on Modal (optional)** | `GET /rl/run` 404 — `.dockerignore` drops `eval/out` | Bake a small `run.json` into image or serve from volume after `make rl-loop`. |

### P3 — Mubit depth (beyond chat hop)

| # | Action | Blocked on | How |
|---|---|---|---|
| D1 | **Wire Mubit memory** | `memory.mubit_project`, `retrieval_top_k`, `token_budget` (Melanie) | Implement `memory/mubit.py` against `/v2/control/`; `MEMORY_IMPL=mubit` on demo when ready. |
| D2 | **Live Sapling** | `sapling.*` decisions + GPU app | `make modal-deploy-sapling`; `SAPLING_IMPL=live`; keep scope aid/denial only. |
| D3 | **STT live** | `modal.stt_*` | `make modal-deploy-stt`; set `STT_UPSTREAM` at gateway deploy. |

### P4 — Learning / models (not required for triage demo)

| # | Action | Notes |
|---|---|---|
| E1 | `make export-laya` / `LAYA_TRAIN=1 make laya-train` | GPU or Modal task; does not change rules-only S1 by itself |
| E2 | Decide classifier second opinion | Product: load Laya/SetFit into cascade or keep rules-only |
| E3 | `make modal-finetune` | Event-log SetFit/LoRA — **not** Laya; needs `modal.finetune_base_model` |
| E4 | Refresh RL cache for nano | `make rl-loop` live once so `rl-loop-replay` hits |

### P5 — Thai (only if product reopens)

| # | Action | Notes |
|---|---|---|
| F1 | Re-add Thai need/danger/vulnerable keywords | Was reverted on purpose; use glossary + synthetic eval; watch false friends (`ยา`) |
| F2 | Thai UI labels | `name_th` / facility names when `lang` is th/mixed |

### P6 — Data / cleanup (backlog)

| # | Action |
|---|---|
| G1 | UI or S2 consumer for `/map/flood` + `/map/facilities` (province-filtered) |
| G2 | Runtime reader for `disaster_report` (“past floods here”) |
| G3 | Flag stale Open-Meteo / snapshot age at point of use |
| G4 | Resolve `routes.yaml` vs `NEEDS_TABLE` (delete or generate from code) |
| G5 | Single district list story (document or merge `districts` / `admin_districts` / gazetteer) |
| G6 | Aid endpoints still 501 — implement or hide from demo |
| G7 | `countries/` loader or drop from demo narrative |
| G8 | Housekeeping: gitignore `.vscode/` `*.log`; move architecture/OWNERSHIP/research under `docs/`; untrack approved junk markdown |

### P7 — Doc sync

| # | Action |
|---|---|
| H1 | Keep this file’s tip SHA and “Done recently” updated after each push |
| H2 | PRD / architecture refresh agents: rebase before push (docs-only commits collide) |

---

## Remaining gaps (short index)

Maps to the plan above. Struck items are done.

~~1. Plural children~~ · **2. Hosted auth** → C1 · **3. Thai keywords** → F1 (opt-in) · ~~4. Demo skips extract~~ · ~~5. Hosted S1 stub~~ (redeploy A1) · ~~6–7. Dispatches / confirm API~~ · **8. Mubit memory** → D1 · **9. Trained models unused** → E* · **10. Two graduation paths** → B1 · ~~11. Stale TODO town copy~~ · ~~12. G01–G04~~ · **13. Modal RL / stock** → C2–C3 · ~~14. demo_event~~ (calls still north → B2) · **15. Melanie review orchestrator** · **16. routes.yaml** → G4 · ~~17. Town ignores backend~~ (mostly fixed; chooser still demo-only for pins) · **18. Three learning stories** → B1 · **19. always_requires_human text** · **20–21. Duplicated lists** → G5 · **22–26. Unused scrape** → G1–G7 · **27–28. Dead code** (opportunistic) · ~~29. location_context UI~~ · **30–31. Flood geography** → B2–B3 · ~~32. admin_districts enrich~~ · **33–37. Unused history/map/Thai UI** → G1–G2, F2

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
