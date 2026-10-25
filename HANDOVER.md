# Handover

25 October 2026. Tip: check `git rev-parse --short HEAD`. `make test` / `make validate` must stay green. `requirements.txt` has `openai>=1.40`.

**Judges-only URL (no auth):** `https://baansafe--baansafe-gateway-web.us-east.modal.run` — town at `/ui/sim/`. Do not broadcast.

## Main parts

One call: `gateway/route.py` `handle` ← `POST /triage` / `POST /cases/{id}/turns`.

| Part | Where | State |
|---|---|---|
| Extraction | `system1/extract.py` | English keywords; bare `unaccompanied` → child unless `adult` named. Thai = district names only. Demo English / code-switched. |
| Enrichment | `enrich/context.py`, `ingest.store` | Live when `districts.json` present. Flags never change priority. |
| Memory | `memory/adapter.py`, `memory/local.py` | Hosted **local** (`MEMORY_LOCAL_PATH=/data/memory.jsonl` on `baansafe-demo`). Case record written after every routed turn (`memory_write` stage); policy lessons seeded; repeat caller at same place + need → S1 `duplicate_merge`. `GET /metrics.memory`. `memory/mubit.py` is dormant: current Mubit has no memory API (`/v2/control/*` = 404). **Your local `.env` must say `MEMORY_IMPL=local`** — with `mubit` every turn 404s twice, memory is always empty, and F09 silently loses `duplicate_merge`. `GET /health.memory.dormant=true` and a startup warning now name it. |
| Graduation | `gateway/graduation.py` | Threshold 2 → `complex_situation` (not into S1 rules). |
| Chooser | `gateway/chooser.py` | `field precheck`; `routing.yaml` `mode: cascade`. |
| System 1 | `system1/decide.py` | Rules-only. |
| System 2 | `system2/orchestrator.py` | Hosted **real** when `baansafe-mubit` injects key+URL. |
| Sapling | `system2/sapling.py` | Stub. |
| Router / ledger | `router/merge.py`, `ledger.py` | Confirm/cancel; in-process holds. Modal **`max_containers=1`**. |
| Traces | `llm/client.py`, `GET /metrics` | `mubit_chat` on every hop (and RL cache hits). Each hop's note carries `request_id=mreq_…` (Mubit's `x-middleware-request-id`, also on 429/5xx) and the reply carries `mubit_request_id`; a cache hit replays the recorded id marked `(recorded)`. The Model Path panel shows it as a copyable code span: paste into the console's **Requests** page to show the same call on Mubit's side. Replies in `fixtures/s2_cache/demo.jsonl` predate this and have no id until re-recorded. Every call sends `metadata.session_id=case_id`; Mubit groups all S2 calls into one Task (static system prompt). ~850 distinct requests sent 25 Oct (RL loop + synthetic set + three `make mubit-traffic` batches: seed 3 → 160 hops, seed 11 → 204 hops, both `memory: []`; seed 23 → 200 hops **with memory in every prompt**). Top up with `TRAFFIC_MEMORY=local MEMORY_LOCAL_PATH=var/memory-traffic.jsonl make mubit-traffic COUNT=n SEED=s`. |
| UI | `ui/sim/` | Wired to transcript / dispatches / `location_context`. **Freeze until Melanie reviews.** |
| Hosting | Modal gateway | Redeployed at `82e68ac` (25 Oct 04:15 UTC). `/hosting` → `backends=live`, `memory=local`. Smoke: two callers on Sukhumvit Soi 22 → second one `finalize_case` with `duplicate_merge_count=1`, `write_error_count=0`. |
| Place | `data.demo_event` | **`Sukhumvit / Watthana (Bangkok)`** — matches basemap + `flood.json`. |

Owners: `OWNERSHIP.md`. Contracts: `v0.3-contracts` (TraceEvent stages grew; schema sync still backlog).

---

## Done recently (do not re-open)

| Item | Notes |
|---|---|
| Safeguarding / unaccompanied adult | `0fdc34e` + PR #11 adult fix |
| Thai need keywords | **Reverted** — leave off |
| PR #9 town + wire P0 | Transcript creates, dispatches, confirm/cancel |
| Mubit traces + `/metrics` + RL traces | `96bef6e`…`e1fc17d` |
| Modal S1 real + mubit secret / S2 gate | `c996c35` |
| G01–G04 → system_2 | `110e370` |
| Judge audit into HANDOVER | PR #11 |
| Place → Sukhumvit / Watthana | PR #12 |
| Modal `max_containers=1` | PR #12 |
| Modal `include_source=True` (crash-loop fix) | PR #13 |
| Hosted smoke | `/hosting` `backends=live`, S2 real; free-text oxygen → S2; `mubit_chat` ok |
| Memory: local store, write path, metrics | PRs #20 #22 (+ #23 session ids, #24 RL note). Mubit memory API does not exist in the current product; `MEMORY_IMPL=local` is the hosted default. Seed with `MEMORY_IMPL=local make seed-memory`, upload via `modal volume put baansafe-demo <file> memory.jsonl` |
| Fine-tune decisions + SetFit run | PR #19, version `ft-20261025T031241Z-e4ce5eb6` |
| Training surface: loss curves, `GET /training`, `ui/training.html` | PR #28 (+ #26 `make mubit-traffic`, #27). Hosted: `/training` and `/ui/training.html` read `baansafe-versions` (ro at `/vol`) and `/data/rl_run.json` |
| `GET /rl/run` honours `RL_RUN_PATH` | Hosted returned 404 while `/training` read `/data/rl_run.json`; `rl_panel.js` fetches `/rl/run` |

---

## Plan (25 Oct, 03:15 UTC)

Four tracks. Order tonight: 1 → 4 → 3 (backend half). Track 2 is done except the shadow label. Owners per `OWNERSHIP.md`: Moly = API / calls / flow / infra, Melanie = S2 / Sapling / decision brains / `ui/sim`.

### Track 1 — Memory: done (local store), Mubit memory API does not exist

Finding (25 Oct, verified live and in docs.mubit.ai): current Mubit is an LLM gateway that records calls and trains per-task adapters. `https://api.mubit.ai/v2/control/*` returns `404 unknown_route`; the `/v2/control` client came from the retired "Mubit Memory" SDK. The hosted `items=0` was a swallowed 404, and corrections were 500ing on the hosted demo.

| Step | What | Status |
|---|---|---|
| 1a | PR #22: honest `retrieve_error=` on the memory trace, correction kept locally (no more 500), `scripts/seed_memory.py` with 10 policy lessons from `policies/service.py`, `MUBIT_CONTROL_URL` override | merged, deployed |
| 1b | PR #20: `MEMORY_IMPL=local` (`memory/local.py`, JSONL, field-overlap scoring), `store_record()` after the router, `source_case_id` round-trip, own-case exclusion, `/metrics.memory`, 16 new tests | merged, deployed |
| 1c | Seeded `/data/memory.jsonl` on `baansafe-demo` with the 10 lessons | done |
| 1d | Hosted proof: caller A (water, Sukhumvit Soi 22) → `create_provisional_dispatch`, `items=2`; caller B next door, same need → `items=3`, `finalize_case`, `duplicate_merge_count=1` | done |
| 1e | Frozen script step 3 uses the two-caller merge | done below |

Known behaviour to say out loud: duplicate detection is district/street + need granularity (that's all the record carries), so two households on the same soi with the same need merge. The town's Reject button writes a correction lesson into the same store.

### Track 2 — Fine-tuning: decide, don't train (tier 1 done)

| Tier | What | Status |
|---|---|---|
| 1 | `modal.finetune_base_model = nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1`, `modal.finetune_gpu = T4`, both in `DECIDED`. Real SetFit run on T4: version **`ft-20261025T031241Z-e4ce5eb6`** on `baansafe-versions` (168 rows, 20 steps, `train_loss 0.3013`). `FINETUNE_S1_MODEL` stays env-only | **done, PR #19** |
| 1b | Loss curves + held-out eval in `finetune_job.py` (PR #28). Versions on `baansafe-versions`, all visible at `/training` and `/ui/training.html`: `ft-20261025T045101Z-e4ce5eb6` SetFit s1_triage, 168 rows, 20 loss points (`loss_source=log_history`), **held-out accuracy 0.875 on 72 rows**; `ft-20261025T045212Z-8d9937b9` LoRA on the 7-row event s2 set, loss 14.27 → 0.0017 (overfit, 7 rows); `ft-20261025T045425Z-114efba3` LoRA on the 36-row RL s2 set, loss 13.20 → 6.56. Re-run: `SYNTHETIC=1 make export-training` then `make modal-finetune DATASET=training/out/s1_synthetic.jsonl` (held-out picked up automatically) or `DATASET=eval/out/rl/training/s2.jsonl`; refresh RL block with `modal volume put --force baansafe-demo eval/out/rl/run.json rl_run.json` | **done** |
| 2 | SetFit **shadow** label: `S1_SHADOW_VERSION=<id>` loads the adapter off the volume, emits `shadow_label` + `shadow_confidence` in the `system_1` trace. Never changes `next_action`. Gives Melanie a disagreement rate | post-demo, ~½ day, Moly plumbing / Melanie reads |
| 3 | S1 stays rules-only (DECIDED). Laya full-encoder recipe parked until human events exist (log has 25, mostly from `demo-correction-loop`) | decision, no work |
| 3 | Sapling: stays stub by decision. When reopened: `sapling.hosting=self-hosted`, `sapling.gpu=L40S`, `sapling.model_id=MubitLabs/banyan-sapling`, `sapling.thai_handling=translate`; needs CUDA 13 base image and confirmation Mubit can route to a self-hosted endpoint. 0 `sapling_verdict` rows, so nothing to fine-tune | post-demo, Melanie |
| 3 | STT: stays scripted. When reopened: `modal.stt_model_id=biodatlab/whisper-th-large-v3-combined`, `modal.stt_gpu=T4` | post-demo, unowned |

Fixed on `main`: `s1_app`, `s2_app`, `sapling_app`, `stt_app` now call `.env()` before `with_repo()` like `finetune_app.py`. Untested against a real deploy — the next `make modal-deploy-*` is the proof.

### Track 3 — S2 cache + overlay "learns to be faster" demo

**Backend half done (PRs #31, #32), hosted in cache mode.** `S2_IMPL=cache` (`system2/cache.py`): cache-first completer, Mubit only on a miss, miss recorded to `S2_CACHE_RECORD_PATH`. Committed `fixtures/s2_cache/demo.jsonl` holds 158 replies (fixtures + synthetic, `MEMORY_IMPL=mock`, exact key); `make record-s2-cache` refills misses. Hosted: `/hosting` → `backends: cache`, `S2_CACHE_KEY=case` (ignores random case id, memory summaries, ledger), record file `/data/s2_cache.jsonl`. Proof 25 Oct 05:40: frozen script pass 1 → F10 and caller B `api.mubit.ai status=ok`; pass 2 → both `s2_cache/case status=cache_hit`, `/metrics.mubit_chat.cache_hit_count=2`. **Before the demo, run the exact script once more after any transcript edit** — a changed word is a miss (goes live, then recorded). To flip back to live-only: `S2_IMPL=real modal deploy infra/modal/gateway_app.py`. `TraceEvent.json` synced (Track 4 #5 done). UI half still Melanie's.

Design reviewed against code. Compatible with four corrections:

1. `make rl-loop-replay` does **not** write the cache; only live `make rl-loop` does, and `eval/out/` is gitignored. Ship a committed `fixtures/s2_cache/demo.jsonl` read via `S2_CACHE_PATH`.
2. No fuzzy key. `S2_CACHE_KEY=exact` (default; RL loop, committed fixture) hashes the messages as sent. Hosted needs `S2_CACHE_KEY=case`, which drops only `case_id`, `memory`, `resources` from the payload (random ids, store grows per case, ledger moves) — transcript, fields, triggers, handoff, system prompt still must match byte for byte. A reply recorded for a different transcript is not a hit.
3. Record the cache **after** Track 1 lands (memory items are in `_messages`, so the key changes once the workspace has content). The 04:07 `run.json` / `s2_cache.jsonl` were produced with `memory: []`; **re-run done 06:00 UTC with `MEMORY_IMPL=local`** (see audit A2), `rl_run.json` on the volume replaced.
4. Local `make hackathon-demo` vs hosted URL tell different stories (no LLM calls vs real Mubit traffic). Pick one for the 3-minute script; hosted stays the judges' URL unless both agree.

| Half | What | Owner / effort |
|---|---|---|
| Backend | **done**: `orchestrator._active_completer()` picks `system2.cache.completer` when `S2_IMPL=cache` and no `use_completer` override; miss with creds → one Mubit call (recorded), miss without → `system2_unavailable`; hit emits `mubit_chat host=s2_cache[/case] status=cache_hit`. Local demo: `S1_IMPL=real S2_IMPL=cache make serve` (fixtures hit the committed file) | Moly, PRs #31 #32 |
| UI | Model Path panel (stage list with latency + cache hit + graduated rule), purple house = S1 via graduated rule, "Learned" badge in `patterns.js`; `rl_panel.js` already renders overlay tables | Melanie, ~5 h, after she pulls `main` |

### Track 4 — Judge items still open

| # | Who | Item |
|---|---|---|
| 1 | Both | Paid S2 on the public URL: keep or stub. Watch `mubit_chat.call_count` and 429s (429 → `system2_unavailable`). |
| 2 | Moly | Dry-run the frozen script on the hosted URL with the UI open, after 1d. |
| 3 | Melanie | Pull `main` (PRs #16–#19 plus Track 1) before touching `ui/sim`. |
| 4 | Both | Aid 501 UI / RL panel hidden or not. |
| 5 | Moly | ~~`python -m contracts.export_schemas`~~ done in PR #31 (`enrich`, `memory`, `mubit_chat` added to `TraceEvent.json`). |

### Decisions needed from humans

- Track 4 #1 (paid S2 on public URL).
- Track 3 #4 (local cache demo vs hosted live demo for the script).
- Track 3 UI half: Melanie go / no-go for tonight.

---

## What’s left

### Must decide / do before judges (tonight)

| # | Who | Action |
|---|---|---|
| 1 | Both | **Keep paid S2 on public URL?** Smoke left it **on** (`S2_IMPL=real`). Else redeploy with stub / no secret spend. Watch `/metrics` and 429s. |
| 2 | Both | Ask Mubit to switch **training on** for workspace `ws-3e4ac86aadff0b72` (console has no Adapters page). The System 2 Task already holds ~650 requests across ~650 sessions (adapter cycle ran 25 Oct ~04:00 with issues; see Mubit history). `make mubit-traffic` adds more distinct examples any time. Pitch: gateway + traces + per-task adapter; memory is ours. |
| 3 | Melanie | Pull `main`, rebase any local `ui/sim` work; review Moly’s town wire before editing. |
| 4 | Moly | Share URL **only with judges**; run the frozen 3‑min script once dry. |
| 5 | Both | Optional: hide aid 501 UI / keep RL panel off (`index.html` does not load `rl_panel.js`). |

### Frozen 3-minute script

1. English **S1** (e.g. F02 rice) — threshold accept, boat may move.  
2. **S2** (e.g. F10 oxygen / under threshold) — PENDING → Accept; say Mubit→Nemotron; point at `/metrics` if a live hop ran.  
3. Second caller, same soi + same need → **memory** `items≥1`, S1 `duplicate_merge` (no second truck); `/metrics.memory.duplicate_merge_count`. Then Reject → Correct this (lesson lands in the store).  
4. Cards in `sim_events.json` are **scripted**; one live hop proves traces.

### Nice-to-have / backlog (not demo blockers)

| # | Action |
|---|---|
| A | ~~Sync `TraceEvent.json`~~ done (PR #31) |
| B | Completers accept `**kwargs` (`case_id`) — Melanie check |
| C | Northern fixtures vs Sukhumvit units — use F17/F18 or accept first usable unit |
| D | Post-hackathon: `gateway.auth`; shared ledger/DB if multi-container |
| E | Live Sapling / STT; Laya/classifier product decision; RL `run.json` on Modal |
| F | Thai keywords only if product reopens |
| G | Housekeeping: `.vscode` gitignore, markdown moves, `routes.yaml` vs needs table |

### Audit, 25 Oct (code read + local probes, not docs)

Measured on `main` `daeaad9` with `S1_IMPL=real`. Things a judge can hit.

| # | Finding | Evidence | Fix / status |
|---|---|---|---|
| A1 | Local `.env` had `MEMORY_IMPL=mubit` (dormant) | `/cases/F09/trace`: `retrieve_error=... HTTP 404 unknown_route`, `memory_write status=error`; F09 → `create_provisional_dispatch` instead of `duplicate_merge` | `.env` set to `local`; `/health.memory` + startup warning added; `OWNERSHIP.md` corrected |
| A2 | The 25 Oct 04:07 live RL run (`eval/out/rl/run.json`, hosted `rl_run.json`) ran under A1 | `mubit: live_ok=54, cache_hits=154`; 20/48 correct, 9 critical under-triage, 9 missed_human, flat across 3 epochs | **Re-run 25 Oct 06:00 UTC with `MEMORY_IMPL=local`** on a store seeded with the 10 lessons (grew to 217 rows during the run): epochs 1–3 correct 22/18/21 of 48, **critical under-triage 2/3/2** (was 9), mean reward −0.125 → 0.01 → 0.189 (was flat), fallbacks 0/0/1; ~133 new Mubit calls (distinct sessions, `x-middleware-record: full`), 84 cache hits, 2 errors. Uploaded as `rl_run.json`; hosted `/training` shows it. Command: `MEMORY_IMPL=local MEMORY_LOCAL_PATH=<seeded store> make rl-loop` |
| A3 | Live Nemotron under-triages the "water at the door + elderly" theme every time | `C01-a`, `C01-b`, `RL-DOOR-1/2`, `RL-UP-1/2` → P2 (truth P1), deterministic at `temperature=0, seed=7`; `C01-a` even with the memory lesson in the prompt | Do not play C01 live in the script. Good material for *why* corrections exist, bad as a "the model gets it" beat |
| A4 | Nothing forces `requires_human` on a P1 rescue | `G01/G03/G04`: live S2 said P1 `rescue_coordination` with `requires_human=false`; `_post_rules` only forces aid/safeguarding; `HUMAN_ROUTES` excludes rescue | Fixed: `_post_rules` now forces `requires_human=True` on any P1 and appends "P1 requires human sign-off" to `reasoning` (+2 tests). The UI gate (`approval.js`) was already holding every S2 decision; the API contract now matches |
| A5 | Extraction emitted `needs=['rescue','rescue']` | "Water is at the door and my grandmother cannot walk. We are trapped." — explicit `trapped` plus the inferred rescue | Fixed in `system1/extract.py` + test |
| A6 | `duplicate_merge` merges *different* households on the same soi | `local` memory: household B (5 people, same soi, water) → `finalize_case`, no dispatch, after household A | Known (Track 1 note). Say it out loud or key the merge on `caller_id_hash` too |
| A7 | Every decision carries two stale policy notes | `auth scheme is TODO_HUMAN; request was not rejected` and `safeguarding and escalation rules were not evaluated` on every `RouterDecision` — the second is false, the chooser does evaluate them | Fixed: `gateway/policy.py` now records the triggers the precheck evaluated (`policy precheck: System 2 triggers from config/escalation.yaml evaluated; fired: …`). The auth note stays — `gateway.auth` is still `TODO_HUMAN` and that is true |
| A8 | Sapling stub can never say `supported`/`violation` on a live case | `_verify_stub` needs an exact (policy, evidence, claim) triple; evidence includes the transcript, so every live aid case → `unsure` → `sapling_unsure` → human | Demonstrable only via `eval/sapling_replay.py` on the 5 stub cases. Do not promise a live Sapling verdict |
| A9 | Overlay "graduated rule" surface is tiny | `overlay.json`: 1 graduated (`RL-ROAD-3`, no needs → P4 info), 1 demoted. `narrow_signature` hashes caller tokens, so a rule fires only on near-identical wording; the `[0.7, 0.8)` confidence band in `system1/decide.py` is unreachable from extraction (it emits 0.85 / 0.6 / None) | "Learns to be faster" must replay the exact fixture that graduated. Not generalisation |
| A10 | `/docs` summary said "System 1 and System 2 logic are not implemented" | `api/main.py` | Reworded |
| A11 | `contracts/schemas/TraceEvent.json` lacks `enrich`, `memory`, `mubit_chat` | schema enum has 5 stages, Pydantic has 8 | Done in PR #31 (`python -m contracts.export_schemas`) |
| A12 | `read_traces()` parses the whole `traces.jsonl` on every `/metrics` and `/cases/{id}/trace` | 831 lines locally; the hosted volume grows unbounded and the town calls `/trace` after every turn | Fixed: `read_traces()` streams the file and skips rows without the case id before parsing. `/metrics` still reads every row; rotate before a long session |

### Mubit training status (25 Oct, 05:45 UTC)

What the API shows: a live S2 call is a plain passthrough (`model: nvidia/nemotron-3-nano-30b-a3b`, `provider: Novita`, `x-middleware-request-id`), with no adapter, task, or version marker in headers or body. `api.mubit.ai` has no readable task/adapter endpoint (`/v1/tasks`, `/v1/adapters`, `/v1/requests` → `404 unknown_route`); the console is the only view. If Mubit promotes an adapter it is served under the same model id, so our traces will not show it.

What ran: an adapter cycle for the System 2 Task at roughly 04:00 UTC, reported "with issues" from the console (exact label not captured here). Context that makes `Below target` / `Prompt only` the expected result for that cycle: strict-JSON output at `temperature=0, seed=7` that the base model already produces, and every prompt before ~04:50 carried `memory: []` (audit A1/A2), so the kept examples were near-duplicates.

What changed since: ~650 distinct requests across ~650 sessions (RL loop, synthetic set, two `make mubit-traffic` batches, 158 `make record-s2-cache` recordings, hosted script runs), each with `metadata.session_id`, one stable system prompt → one Task with held-out sessions available.

**Batch with memory on (25 Oct, seed 23):** `TRAFFIC_MEMORY=local MEMORY_LOCAL_PATH=var/memory-traffic.jsonl TRACE_PATH=var/traces-traffic-23.jsonl make mubit-traffic COUNT=300 SEED=23` (the Makefile used to pin `MEMORY_IMPL=mock` on the recipe line, so the `MEMORY_IMPL=local make mubit-traffic` form in earlier notes silently sent `memory: []`; `TRAFFIC_MEMORY` is the switch now). 300 variants in 133 s → **200 hops, 196 ok, 4 timeouts, 0 errors, 200 distinct sessions**. 296/300 prompts carried memory (avg 4.8 items: the 10 seeded lessons plus earlier batch cases), 300 case records written, 196 hops carry `request_id=mreq_…`. These are the first kept examples whose prompt holds the lessons. Live latency with memory in the prompt: p50 2.2 s, p95 4.5 s, max 8.1 s; 4 of 200 past the 10 s budget. S2 gave P1 on 125 and `requires_human` on all 125 (A4). 86 of 300 callers were `duplicate_merge`d by System 1 before any hop (A6 at scale: 12 locations × few needs). Store and trace stay in gitignored `var/`.

To do (console, human): Adapters → History for the System 2 Task — status label, kept-example count, whether a cycle ran after 05:00 UTC. If "no examples": confirm training is on for `ws-3e4ac86aadff0b72` (Mubit-side). Record the label here and in the demo line: *the gateway recorded every call, grouped the task, ran a cycle, and the test gate held* — the gate is the point. Top up any time with `make mubit-traffic COUNT=300 SEED=<n>`.

### Team backlog for the demo (25 Oct, 06:30 UTC) — evals and front end

Ranked by demo value. Owners per `OWNERSHIP.md`: Moly = API / calls / infra / evals plumbing, Melanie = `ui/sim`, S2, Sapling. Nothing here blocks the frozen script.

**Evals**

| # | Item | Why | Effort | Owner |
|---|---|---|---|---|
| E1 | Before/after comparison: `make rl-compare A=<snapshot> B=<snapshot>` → `eval/out/rl_compare.md` + a "memory off vs on" card on `ui/training.html` | The two snapshots in `eval/snapshots/rl/` are the strongest number we have (critical under-triage 9 → 2, reward flat → +0.19); nothing renders them side by side | ~1 h | Moly |
| E2 | Hosted `GET /training` reports `missing: training/out, eval/out/rl/training` and `events: 1` | Fine-tune exports and the 25 training events exist locally, not on the volume. Either `modal volume put` them or point `/training` at `eval/snapshots/rl/<snap>/training/`. `eval/out/rl/training` now falls back to the newest committed `eval/snapshots/rl/<stamp>/training/` manifests; `training/out` still needs the upload | 15 min | Moly |
| E3 | Per-episode drill-down: `GET /rl/run/episodes?filter=critical_under` + table on the training page | `run.json` holds 48 episodes with truth vs decision; only aggregates show. Lets Melanie click into *which* cases under-triage (A3 theme) | ~1 h | Moly builds, Melanie reads |
| E4 | `make eval-gate`: fail if SetFit held-out accuracy < 0.85 or RL `critical_under` > last snapshot | Turns "we have evals" into a gate. No CI runner on the repo yet, so local/pre-merge | ~45 min | Moly |
| E5 | `scripts/mubit_requests.py`: last N `request_id=mreq_…` from traces with case id + outcome | Ready list for the "paste into Mubit console → Requests" beat | 30 min | Moly |

**Front end** (`ui/sim` is single-writer: Melanie)

| # | Item | Why | Effort | Owner |
|---|---|---|---|---|
| F1 | Badge a cache hit in the Model Path panel (`host=s2_cache/case status=cache_hit`, 0 ms, "replayed") vs a live Mubit hop | Hosted runs `S2_IMPL=cache`; without the badge the resilience story is invisible | small | Melanie |
| F2 | `/hosting` banner at page load: `backends`, `memory`, `secrets` | Nobody curls during the demo | small | Melanie |
| F3 | Training page: link version rows to the Hub repos (flip them public first), render `heldout.per_label` as a table (already in the JSON) | Shows per-class precision/recall, not one number | small | either |
| F4 | Correction → memory round-trip: show "memory items used: n" on each new call's card | `ui/correct.js` writes a lesson; the town never shows it landing on the next call | medium | Melanie |
| F5 | `make demo-reset`: truncate volume `traces.jsonl`, `/data/s2_cache.jsonl`, case rows in `memory.jsonl` (keep the 10 policy lessons) | Every rehearsal grows the hosted store; the script should start from one state | 30 min | Moly |

**Repo hygiene (bit us twice tonight)**

| # | Item | Why |
|---|---|---|
| H1 | `CODEOWNERS` (`ui/sim/sim.js`, `llm/client.py`) and a `make check` that refuses a commit touching another owner's file from a non-owner branch | PRs #34 and #35 each carried someone else's in-progress work swept in by `git add -A` in the shared checkout. Work in a worktree per branch (`git worktree add ../Baan-Safe-wt/<name>`) |
| H2 | `.env.example` with `MEMORY_IMPL=local`, `S1_IMPL=real`, `S2_IMPL=cache`, `S2_CACHE_KEY=exact`, Mubit vars blank | A fresh clone otherwise repeats audit A1 (dormant `mubit` memory) |

Suggested order if one person has ~2.5 h: E2, E1, F5, H2 (all outside `ui/sim`); F1–F4 go with Melanie's next `ui/sim` pull.

**Status 25 Oct 07:15 UTC — all but E2 and F4 merged to `main`.**

| Done | PR | Where |
|---|---|---|
| E1, E3, E4, E5 | #43 | `make rl-compare`, `GET /training/compare` + "memory off vs on" cards; `GET /training/episodes?filter=&epoch=`; `make eval-gate` (`EVAL_GATE_S1_ACC`, `EVAL_GATE_BASELINE`); `make mubit-requests N=` |
| F1, F2, F3 | #47 | `CACHE HIT · replayed` badge; `/hosting` banner strip (red when memory dormant); Hub links + held-out per-label table on `ui/training.html`. Added as `hosting_banner.js` / `training_polish.js`; `sim.js` untouched |
| F5, H1, H2 | #48 | `make demo-reset` (dry run; `RESET_ARGS=--yes`, `--hosted`); `.github/CODEOWNERS` + `make check-owners`; `.env.example` complete, with `tests/test_env_example.py` asserting every env name the code reads is documented |
| QA | #42 | `/rl/run` honours `RL_RUN_PATH`; truthful precheck note; Modal apps load `.env` before reading env; streamed traces |
| Served by | #49 | `x-middleware-served-by` kept in trace note and reply (`mubit_served_by`); cache replays carry the recorded value |
| Root | #52 | `GET /` → 307 to `/ui/sim/index.html` (was FastAPI `{"detail":"Not Found"}` on local and hosted) |
| Fix | #51 | `.env.example` gained `RL_COMPARE_A/B`, `EVAL_GATE_*` — #43 and #48 were each green alone, red together (new env reads vs new "every env name documented" test). Run `make test` on the rebased branch *before* `gh pr merge`, and read the exit code, not the tail |

Duplicates closed unmerged: #44, #45, #46, #50 (a second agent built E3/E4/E5/F5/E1 in parallel). Only differences not carried over: episode filters `s2_fell_back` / `cascaded`, `eval-gate --strict`, `/training/compare?a=&b=`. Pick up if wanted.

Open: **E2** (upload `training/out` to the volume or accept the snapshot fallback), **F4** (Melanie, needs `sim.js`). The local dev server a sidekick started on a random port (`127.0.0.1:62752`) runs pre-merge code; `make serve` on 8000 for current `main`.

### Branch policy

Branch → PR → merge when `make test` / `make validate` green. Do not push feature work straight to `main`. Prefer one writer on `ui/sim/sim.js` and `llm/client.py`.

Use a worktree per branch, not the shared checkout: `git fetch origin && git worktree add -b <branch> ../Baan-Safe-wt/<name> origin/main`, then work only there and stage paths explicitly (`git add <paths>`). Never `git add -A` in the shared checkout; PRs #34 and #35 each swept in someone else's in-progress edits that way. Run `make check-owners` before `gh pr create`: it warns when the branch touches `ui/sim/sim.js` (Melanie, branches `melanie/`, `mel/`) or `llm/client.py` (Moly, `moly/`) from a branch that is not the owner's (`OWNERS_ARGS=--strict` exits 1). `.github/CODEOWNERS` (`@melaniepreen` for `ui/sim/`, `@molyleelatham` for `llm/client.py`, `gateway/`, `infra/`) requests the same review on GitHub. Before a demo, `make demo-reset` (dry run) then `make demo-reset RESET_ARGS=--yes` puts traces, case memory, and recorded replies back to the start of the frozen script; `RESET_ARGS='--hosted --yes'` does the same on the `baansafe-demo` volume between demos (not while the container is serving). H1 and H2 above are done by this.

---

## Live System 2

Model: `nvidia/nemotron-3-nano-30b-a3b` via Mubit. Hosted promotes when secret has key+URL. 429 → `system2_unavailable`. Replay: `make rl-loop-replay` (misses = fallbacks).

Architecture: `BaanSafe_Revised_Architecture.md`. Wire plan: `docs/wire-frontend.md`.

## Laya / latte-bench

Laya = export + optional train; S1 stays rules-only until a product wire. `make latte-bench` often skips without `bun`.
