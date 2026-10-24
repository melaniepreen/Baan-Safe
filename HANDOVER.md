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

### Conflicting decision logic

16. **`config/routes.yaml` contradicts the code.** It maps `evacuation` to `rescue_coordination`. `NEEDS_TABLE` in `system1/decide.py` and the F06 label use `shelter_placement`. No code reads `routes.yaml`.
17. **The town decides on its own.**
    - `ui/sim/sim.js` has a demo-only keyword chooser that maps typed text to a fixture.
    - `ui/sim/data/rulebook.json` picks the vehicle from the priority and ignores `RouterDecision.dispatches`.
    - `ui/sim/data/sim_events.json` scripts a System 1 score against 0.8, a handoff to System 2, and "promote after 3".

    What the town shows is not what the backend decided.
18. **Three learning stories.** `gateway/graduation.py` sends a pattern to System 2. `eval/rl/` with `RL_OVERLAY` writes System 1 rules. `make demo-correction-loop` registers stub model versions. Pick one for the demo.
19. **`always_requires_human` in `config/escalation.yaml` is text.** Nothing executes it. `router/merge.py` hard-codes its own copy.

### Duplicated data

20. **Three district lists.**
    - `districts`: 50 rows, about 30 of them Bangkok, `province` empty.
    - `admin_districts`: 108 rows for the 8 configured provinces.
    - `data/snapshots/gazetteer.json`: 224 KB.

    `system1/extract.py` reads all three plus `DISTRICT_ALIASES`. `enrich/context.py` reads only `districts`.
21. **Four resource lists.**
    - `mocks/resources.json`: 4 fictional units.
    - `ui/sim/data/town.json` `resources`: the same 4 ids under new names.
    - `data/snapshots/places.json`: OpenStreetMap units that dispatch uses. `ui/sim/data/places.json` is a label copy.
    - The `infrastructure` table: 4,218 OpenStreetMap facilities that only enrichment reads.

### Scraped and unused

22. **`disaster_report` has no runtime reader.** 126 rows (GLIDE 109, IDMC 14, GDACS 3). Only `scripts/validate.py` scans it.
23. **The map exports have no consumer.** `data/processed/flood.geojson` (10 MB, 698 features) and `facilities.geojson` (1 MB, 4,218 features) are served by `/map/flood` and `/map/facilities`. No UI page calls them.
24. **Snapshots nothing reads at runtime:** `geoboundaries.json`, `gistda.json`, and `tmd.json` (the TMD fetch failed).
25. **Weather ages without a warning.** Open-Meteo was fetched at 04:08 UTC on 24 October: archive 24 September to 23 October, forecast 7 days. Nothing flags its age at the point of use.
26. **Loaded but unused.** Nothing imports `countries/`. `policies/mof_relief.yaml` loads, but the aid endpoints return 501.

### Dead code

27. **Never called:** `memory/adapter.store_record`, `ingest/overpass._accessibility`, `infra/modal/common.require_secret_present`, `infra/modal/finetune_job.write_registry`, `ui/sim/build_town._incident_modes`.
28. **Called only by tests:** `gateway/route.choose_system`, `enrich/context.sample_districts`, `policies/corpus.corpus_counts`, `policies/corpus.load_labels`, `eval/learning/arms.arm_by_name`, `eval/learning/cases.group_by_id`. The Sapling live parser (`system2/sapling_client.verdict_from_model_output`) waits for `SAPLING_IMPL=live`.

### Geo and UI: what can be leveraged

29. **Every call already carries named facilities.** `enrich/context.location_context` runs on each turn and is stored in `case.resources.location_context`, which the UI receives with the case.
    - It gives the nearest hospitals with distances (F10: Sung Men Hospital, 3.8 km) and candidate shelters (real schools and temples) for all 22 fixtures with a usable district.
    - It also gives 24-hour rain, the forecast, reservoirs for Lampang, Phrae, Nan, and Phayao, and source freshness.
    - The UI shows none of it. The router does not use it: a dispatch could name the nearest real hospital or shelter.
30. **The live water is where no call happens.** All 228 GISTDA 7-day and 30-day polygons are in Songkhla.
    - The nearest is 1,237 km from any fixture.
    - All 22 resolvable fixtures have no flood flag and at most 0.5 mm of rain, so enrichment does nothing in the demo.
    - The Hat Yai flood of November 2025 (EOS-RS polygon) is in the database with no calls. Songkhla fixtures, or `data.demo_event` = Hat Yai, would light it up.
31. **The flood flag tests one point per district.** Thepha has 120 live polygons whose centres are within 5 km of its own. It still reads as dry: its centre is 2.4 km from water, and the buffer is 500 m. Test the district area or a wider radius.
32. **Enrichment knows 50 districts.** `enrich/context._match_district` reads `districts` only. Hat Yai, Mueang Songkhla, and most of the 8 provinces get no point, no flags, and no facilities. Fall back to `admin_districts`.
33. **Flood history is unused.** `disaster_report` names Nan in 9 events, Lampang in 7, Phrae in 6, and Songkhla in 3. That is a "past floods here" line, or System 2 evidence.
34. **Rain trend is unused.** `weather_observation` has 1,900 rows: 50 districts, 30-day archive plus 7-day forecast.
35. **There is no real map.** The town is a local-metre drawing of Sukhumvit. A small WGS84 panel could show call pins (`admin_districts` centres), flood polygons, and nearby facilities, filtered by province to stay light. If the picture stays in Bangkok, Vadhana already resolves: 20 mm of rain in the last 24 hours and named hospitals and shelters.
36. **Endpoints no UI calls:**
    - `/context` and `/resources`.
    - `/cases/{id}`: decision history per turn.
    - `/metrics`: latency per stage, the latency column for the quality, cost, and latency track.
    - `/policies/match` and `/policies/{rule_id}`: cite the rule behind a decision.
    - `/replay`: score every fixture.
37. **Thai names are unused.** `admin_districts.name_th` and the Thai facility names could label the UI in Thai.

## Live System 2

System 2 runs `nvidia/nemotron-3-nano-30b-a3b`, the paid tier, through Mubit. It replaced `nvidia/nemotron-3.5-lightning:free`. OpenRouter's 50-a-day free cap covers every `:free` model on the account, and today's cap was spent. On 24 Oct 2026, nano answered 6 fixture prompts in 1.1–1.7 s. 3 of the 6 matched the fixture priority and route. C01-a came back P2 welfare where P1 rescue was expected. A call costs about $0.0003 (the OpenRouter list price is $0.06 per million input tokens and $0.24 per million output tokens).

The RL replay cache (`eval/out/rl/s2_cache.jsonl`) is keyed by model. Until `make rl-loop` runs live with nano, `make rl-loop-replay` misses every entry and scores them as fallbacks. `run.json` now records `model`.

The full routing walk-through, the loops, and the Modal status are in `BaanSafe_Revised_Architecture.md` under "Routing in detail".

## Laya Model Training Pipeline (Verified 24 Oct 2026)

The Laya fine-tuning path is now fully functional end-to-end.

### Export (`make export-laya`)
- **Train**: 168 calls (56 en, 56 th, 56 mixed)
- **Held-out**: 72 calls (24 en, 24 th, 24 mixed)
- **Questions**: 12 total — 1 `choice` (priority: red/yellow/green/white/black) + 11 `noul` (boolean System 1 labels)
- **Split**: 70/30 by `group_id` (80 groups, seeded) — same split as SetFit export

### Tests & Validation
```
make test       → 232 passed, 1 skipped (needs laya package)
make validate   → validate ok: 24 fixtures (no PII, no TODO_HUMAN in allowlist)
```

### Schema (Laya 0.4.14 JSONL)
```json
{
  "state": {"body": "caller: ...\noperator: ..."},
  "questions": {
    "priority": {"type": "choice", "criteria": {...}},
    "niems_not_conscious_or_breathing": {"type": "noul", ...},
    ... (11 noul total)
  },
  "expected": {"priority": "red", "flood_trapped": true, ...},
  "language": "en|th|mixed",
  "tags": ["group:syn-...", "primary_label"]
}
```

### SetFit Export (same group split)
```bash
SYNTHETIC=1 make export-training
# → s1_synthetic train 168 held_out 72
```
```json
{"text": "...", "label": "flood_trapped", "group_id": "syn-...", "weight": 1.0}
```

### Next Steps (When Ready)
| Action | Command |
|--------|---------|
| Fine-tune locally (GPU) | `LAYA_TRAIN=1 make laya-train` |
| Fine-tune on Modal | `make modal-finetune` |
| Deploy S1 with Laya to Modal | `export S1_MODEL_ID=convaiinnovations/laya-multilingual && make modal-deploy-s1` |
| Deploy fine-tuned checkpoint | `export S1_MODEL_ID=/path/to/laya-ckpt && make modal-deploy-s1` |

### Open Decisions (from `config/decisions.yaml`)
- `modal.s1_model_id: TODO_HUMAN` — set at deploy via env
- `modal.s1_gpu: TODO_HUMAN` — cpu \| T4 \| L4
- `modal.finetune_base_model: TODO_HUMAN` — LoRA base checkpoint

---

## Housekeeping

- **Markdown cleanup is approved but not done.**
  - Untrack and gitignore `MORNING_REPORT.md`, `research/DEMO_PLAN.md`, and `docs/agents/INDEX.md`.
  - Move `BaanSafe_Revised_Architecture.md` to `docs/architecture.md`, `OWNERSHIP.md` to `docs/OWNERSHIP.md`, and `research/` to `docs/research/`, then update every reference.
  - Add `.vscode/` and `*.log` to `.gitignore`.
  - Point the Cursor refresh agent at `docs/architecture.md` afterwards.
- The Cursor Agent refreshes `docs/PRD.md` after pushes, at most every 30 minutes. Rebase before a push.
- Several agents have worked in this folder at once. Check `git status` and `git stash list` before starting.
- The local `.env` has `S1_IMPL=real`. Restart `make serve` after changing it.
