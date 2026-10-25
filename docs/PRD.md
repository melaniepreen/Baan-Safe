# BaanSafe PRD

Shared product and interface note for Moly and Melanie. Every claim below is what the code on `main` does. This file does not set a value in `config/decisions.yaml`. Owners in the status table are from `OWNERSHIP.md`. Callers are synthetic: `caller_id_hash` values look like `synthetic:f02`, and `scripts/validate.py` rejects phones, 13-digit ids, PromptPay, passport, immigration status, and bank account.

The PRD and diagrams are refreshed at most every 30 minutes, in one docs-only commit, and only when something changed. Code pushes don't trigger it. Feature work branches off `main` and opens a pull request (`AGENTS.md` invariant 6, `bbde2f0`). This note is the docs-only exception: it still pushes straight to `main`. If that push is rejected, run git pull --rebase; it only conflicts if you edited docs/PRD.md.

The README diagram at `0967f21` is the model for this note and for later diagram refreshes. One caller turn runs top to bottom: 1 caller, 2 Mubit gateway, 3a System 1, 3b System 2, 4 decision router, 5 operator review, 6 learning loops. Solid means implemented. Dashed means a stub, opt-in, or not wired. Green is System 1, blue is System 2, and yellow is a person. The file-by-file request map stays in `BaanSafe_Revised_Architecture.md`. Labels were updated in place through `7342a66`. Every turn still retrieves memory. Local `MEMORY_IMPL` stays `mock`. `MEMORY_IMPL=mubit` calls `memory/mubit.py`, and the Modal gateway sets that when `baansafe-mubit` is present. The town posts a transcript on free-text and phone creates, and reads `dispatches`, `location_context`, and `GET /metrics`. One-click households still post `fixture_id`.

## 1. Product

BaanSafe is a flood call-triage scaffold for a synthetic Thai flood. A call is triaged, a provisional dispatch can be named, and aid casework is a separate check that does not approve a payment. Mubit governs memory, policy, and traceability and does not reason. The field precheck picks one entry point; `config/routing.yaml` `mode: cascade` lets a System 1 escalate continue to System 2 in the same turn (the no-stub fallback outcome never cascades). Every LLM call goes through `llm/client.py` or `llm/openai_client.py`. Both refuse a host that is not `api.mubit.ai` or a `mubit.ai` subdomain. `llm.provider_route` is `mubit`. The OpenAI SDK base is the Mubit compat prefix (`/compat/openrouter/v1`). There is no OpenRouter client.

Demo story, as the town page runs it (`ui/sim/`, `make serve`, `http://127.0.0.1:8000/ui/sim/`):

- The picture is a local-metre Sukhumvit block in Watthana. `data.demo_event` is `Sukhumvit / Watthana (Bangkok)`. `scripts/validate.py` allowlists that string, so a branch that still says `Hat Yai / Songkhla` fails `make validate`. Desk flood is `flood.json`. Most fixture `location_label`s stay Lampang, Phrae, Nan, and Phayao, so enrichment does not match Watthana for those calls. F17 and F18 are Soi Sukhumvit 40 and 42, Khlong Tan Nuea, Watthana. `places.json` covers the four northern provinces and has no Watthana unit (open item 9).
- Free-text and phone creates `POST /cases` with a transcript turn and empty fields. A scripted play or a saved prompt posts `fixture_id` only. Both paths then `POST /cases/{id}/turns` with the typed or spoken text. The house pin is labelled demo-only.
- The gateway returns a `RouterDecision`. Answered houses that are not the call in progress take `final_priority` from `OUTLINE_HEX` in `ui/sim/sim.js`: P1 `#ff3b30`, P2 `#ff9f1a`, P3 `#3ddc84`, P4 `#c084fc`. The active caller's house stays `#ff3b30`, and a `matchRule` destination stays `#2f6bff`. The call-list badge and the gateway badge use different colours: P1 `#d1241a`, P2 `#ED7401`, P3 `#0076D8`, P4 `#014855`. The phone speaks a scripted line from `ui/sim/data/replies.json`, not a live operator.
- The right-hand feed plays `ui/sim/data/sim_events.json`. Every card is badged simulated. `confidence_threshold` is 0.8, the same number as `system_1_min_confidence`. The accept/reject story is still the page's scores, not `source_outcomes[0].system`.
- Reject opens Correct this (`ui/correct.js`) and posts `POST /cases/{id}/corrections`.
- Speech uses the browser Web Speech API, else `POST /stt/transcribe`. This API does not mount `infra/modal/stt_app`. If neither returns words, the phone shows a stub transcript and sends nothing.

Scope that is in the tree tonight:

- Gateway: keyword-extract when fields are empty, enrich, mock memory, human-correction graduation (`complex_situation`), field precheck, then one system or a cascade into System 2, `router.merge`. Each turn emits trace stages `enrich` and `memory`. `router/ledger.py` reserves stock in this process only. `POST /cases/{id}/dispatches/confirm` and `/cancel` mark or release those holds and return 422 when this process has none. `GET /resources` lists OpenStreetMap places ahead of the fictional units and subtracts in-process holds. Runtime flood context is committed JSON and GeoJSON in `data/processed`, read by `ingest/store.py`. SQLite is only the gitignored `make ingest` cache at `data/raw/ingest.sqlite`.
- `fixtures/synthetic` has 240 calls. `make export-laya` writes Laya JSONL on the same `group_id` split as the SetFit export (HANDOVER measured 168 train and 72 held-out). `make laya-train` skips unless `LAYA_TRAIN=1` and a GPU or a Modal task is present. Laya is export-only. System 1 stays rules-only. `make modal-finetune` is SetFit and LoRA from the event log (`infra/modal/finetune_job.py`). It does not train Laya or read `training/out/laya/`. Nothing loads a Laya checkpoint. Country packs under `countries/` are not imported.
- System 1 rules (`system1/extract.py`, `system1/decide.py`) when `S1_IMPL=real` or `use_stubs=False`. The API default is `use_stubs=True`, so a normal `/turns` call still uses the stub outcome file. A stub that escalates still cascades to the System 2 stub.
- System 2 calls Nemotron through Mubit only when `S2_IMPL=real` (`system2.orchestrator_model` is `nvidia/nemotron-3-nano-30b-a3b`, `system2.max_latency_ms` 10000). `llm/client.py` and `llm/openai_client.py` accept only `api.mubit.ai` or a `mubit.ai` subdomain. `orchestrate` passes `case_id` into the completer, and every hop emits `mubit_chat`. A local API defaults to `S2_IMPL=stub`. The Modal gateway attaches `baansafe-mubit` and sets `S2_IMPL=real` when both `MUBIT_API_KEY` and `MUBIT_BASE_URL` are present, which spends paid Nemotron calls and can 429 (open item 29). A missing URL or key on a real call is HTTP 503. `make modal-secrets` writes both into `baansafe-mubit`. A 429 becomes a `system2_unavailable` outcome, not a 503. A replay cache miss raises `ValueError("s2 cache miss")`, and that same fallback catches it. Sapling's live client, aid eligibility, and aid exceptions still raise or return HTTP 501. The Mubit memory client is live when `MEMORY_IMPL=mubit`. A failed retrieve returns no items. `GET /hosting` reports `LLM via Mubit only`.
- Integration named in `OWNERSHIP.md`: `S1_IMPL=real`, `S2_IMPL=real`, and `MEMORY_IMPL=mubit` together. Contracts stay frozen at `v0.3-contracts` until then. CR-003 (`Dispatch`, `RouterDecision.dispatches`) is tagged `v0.3-contracts`.

`frontend-prototype/` is not part of this product surface.

## 2. Status

| Component | Owner | State | Files |
|---|---|---|---|
| Gateway turn | Moly | live | `gateway/route.py` `handle` |
| Field precheck | Moly | live. Decided value `field precheck` | `gateway/chooser.py`, `config/escalation.yaml` |
| Keyword extract | Moly | live. English word-boundary phrases for needs, danger, and vulnerability, plus caller-confirmed operator facts. `4913304` removed the Thai phrase lists, so a Thai sentence gets no System 1 needs. District names still match Thai, English `Name District`, a bare multi-word English name that is not all common English, and `DISTRICT_ALIASES` (`Watthana` → `Vadhana`). A hit is `<name_en> District, <Province> Province` at confidence 0.85. An ambiguous name gets 0.6, which the precheck sends to System 2. Skipped when the case already has fields and `keyword_extraction` is absent | `system1/extract.py`, `data/processed/admin_districts.json`, `data/processed/districts.json`, `data/snapshots/gazetteer.json` |
| System 1 decide | Moly | live rules. Default request uses the stub file instead | `system1/decide.py`, `mocks/s1_stub/` |
| Aid eligibility | Melanie | stub. `check` raises. `GET /aid/eligibility` is 501 | `system1/aid_eligibility.py` |
| Router merge | Moly | live. Always called from `handle`. Provisional dispatches reserve stock in this process at decision time. `POST /cases/{id}/dispatches/confirm` and `/cancel` act on those holds and return 422 when this process has none. With no district match, the first usable unit wins, and OpenStreetMap units are listed first | `router/merge.py`, `router/ledger.py`, `api/routes/endpoints.py`, `mocks/loader.py` |
| Auth | Moly | TODO_HUMAN. A note is recorded. The request is not rejected | `gateway/auth.py` |
| Enrichment | shared | live when `districts.json` exists, else off. `_match_district` tries `districts` first, then `admin_districts`. Hat Yai and Mueang Songkhla resolve as Songkhla Province. Rain stays null on that admin-only match. Northern rows keep `province` null, so reservoirs stay empty. `GET /context` returns the context dict. The Modal gateway leaves `ENRICH_IMPL` empty, so the same auto rule applies. Flags do not change priority | `enrich/context.py`, `ingest/store.py`, `gateway/route.py`, `api/routes/endpoints.py` |
| Policy pre-check | Moly | live notes only. Does not change priority | `gateway/policy.py` |
| Memory mock | Melanie | live for fixture ids. This is the local default (`MEMORY_IMPL=mock`) | `memory/adapter.py`, `mocks/memory_context/` |
| Mubit memory client | Melanie | live when `MEMORY_IMPL=mubit`. `POST /v2/control/query` and `/v2/control/ingest`. Project `baansafe-demo`, top 5, 400 tokens. `MUBIT_PROJECT_ID` overrides. A query error returns no items. The turn does not call `store_record` | `memory/mubit.py`, `gateway/route.py` |
| Graduation (escalation) | Moly | live. `correction_loop.escalation_threshold` is 2. A matching pattern is tagged `complex_situation` and gets a `graduated-*` correction `MemoryItem`. It sets no priority and does not move the pattern into System 1 | `gateway/graduation.py`, `eval/graduation_demo.py` |
| RL loop | Moly | offline. `correction_loop.graduation_threshold` is 2: graduate (System 2 → System 1 rule), recommend (P1/complex), demote (System 1 under-triage). Live only with `RL_OVERLAY` | `eval/rl/`, `gateway/overlay.py` |
| System 2 / Nemotron | Melanie. Moly edited these files in `9da21c7` | live only when `S2_IMPL=real`. The default API stays `stub`. The Modal app sets `real` when `baansafe-mubit` injects both Mubit values. Signature is `decide(case, handoff, recommendation)` | `system2/decide.py`, `system2/orchestrator.py` |
| Sapling | Melanie | gate is written. Client is `stub`. Runs after a real System 2 outcome on aid checks | `system2/sapling.py`, `system2/sapling_client.py` |
| Aid exceptions | Melanie | stub. `POST /aid/exceptions` is 501 | `system2/aid_exceptions.py` |
| LLM clients | Melanie wires the call | host check is live. Called by `orchestrate` on System 2 turns | `llm/client.py`, `llm/openai_client.py` |
| Policy corpus | Melanie | live `GET/POST /policies`. `flood.yaml` is in the loaded corpus. Packs under `countries/` are not imported. `policies.authoritative_set` is TODO_HUMAN | `policies/service.py`, `policies/corpus.py`, `api/routes/policies.py` |
| Town phone and feed | `OWNERSHIP.md` lists `ui/` as Moly. Melanie owns the System 2 story the desk shows | live page. Free-text posts a transcript. Vehicles prefer `dispatches`. The desk shows `location_context` and `GET /metrics`. `index.html` does not load `rl_panel.js` | `ui/sim/sim.js`, `ui/sim/index.html`, `ui/sim/data/`, `ui/sim/rl_panel.js` |
| Correct this | Moly | live post of a v1 correction | `ui/correct.js`, `ui/player.html` |
| Training log and export | shared log, Melanie eval | live append and export. `fixtures/synthetic` also exports SetFit rows and Laya JSONL. Laya is export-only. `laya-train` skips without `LAYA_TRAIN=1`. `make modal-finetune` is SetFit and LoRA and does not read `training/out/laya/`. It still refuses a TODO_HUMAN base model | `training/log.py`, `training/export.py`, `training/synthetic_export.py`, `training/laya_export.py`, `scripts/laya_train.py`, `infra/modal/finetune_job.py` |
| Held-out eval | Melanie | stub scoreboard. Does not load weights. Promotion stays false | `eval/learning/` |
| Extract eval | Moly rules, shared fixtures | live comparison of extract vs hand-filled fields. Writes `eval/out/extract.md` | `eval/extract_eval.py` |
| Caller sim | Melanie | scripted path is live. Model backend is TODO_HUMAN | `sim/env.py`, `sim/coach.py` |
| Modal gateway | shared | one ASGI app. `max_containers=1`, so confirm, cancel, and `GET /resources` share one in-process ledger. Traffic queues on that container. A live System 2 call can hold it for up to 10 s (`system2.max_latency_ms`). After `scaledown_window=120` seconds idle the container exits and the ledger is empty. Volume `baansafe-demo` at `/data` holds traces, training events, corrections, and policy pins. `BAANSAFE_DB_PATH` is not set. `S1_IMPL=real`. `ENRICH_IMPL` empty, so enrichment follows `store.available()`. `S2_IMPL` becomes `real` and `MEMORY_IMPL` becomes `mubit` when `baansafe-mubit` injects both Mubit values. Without those values System 2 stays stub and memory stays mock. `GET /hosting` says `LLM via Mubit only`. The image copies `data/processed` JSON and GeoJSON. `.dockerignore` drops `*.sqlite`, `data/raw`, and `eval/out`, so `GET /rl/run` is 404 there. `include_source=True` so Modal can import `gateway_app` at hydrate time. `include_source=False` crash-looped with `ModuleNotFoundError` (`51758cd`). `HANDOVER.md` (`4cedabd`) records a redeploy smoke with `/hosting` live and one System 2 turn. This note did not call that URL (open item 11) | `infra/modal/gateway_app.py`, `policies/service.py` |
| Speech to text | shared | TODO_HUMAN. Not mounted on this API | `infra/modal/stt_app.py` |

## 3. Shared context

Models are Pydantic v2 with `extra=forbid`. JSON Schema copies are `contracts/schemas/*.json`. Required fields below are the schema `required` arrays.

### Must provide

- To match CR-003, Moly provides `Dispatch` and `RouterDecision.dispatches`. The tag is `v0.3-contracts`. `TraceEvent.stage` later gained `enrich`, `memory`, and `mubit_chat` in `contracts/models.py` with no new contract tag. `contracts/schemas/TraceEvent.json` still lists `gateway`, `system_1`, `system_2`, `router`, and `memory_write`. Trace readers and the memory adapter must accept the three new stages (open item 27).
- The town posts a transcript for free-text and phone calls, and a `fixture_id` only for a scripted or saved-prompt household (`useFixtureCreate`). It reads `decision.dispatches` (`need`, `resource_kind`, `resource_id`, `status`), `case.resources.location_context`, and `GET /metrics`. `GET /rl/run` still returns 404 on Modal because `.dockerignore` excludes `eval/out`. `index.html` does not load `rl_panel.js`. That file labels a run `live · via Mubit`, `replay · S2 cache`, or `fake · authored truth`.
- `memory.mubit_project` is `baansafe-demo`, `memory.retrieval_top_k` is 5, and `memory.token_budget` is 400. `scripts/validate.py` allowlists those values. `MEMORY_IMPL=mock` stays the local default and reads fixture files. `MEMORY_IMPL=mubit` calls `memory/mubit.py`: `POST /v2/control/query` on retrieve and `POST /v2/control/ingest` on a correction or a record write. Those routes use the Mubit host root, not the compat prefix. `MUBIT_PROJECT_ID` overrides the project leaf. A `proj-` id is sent as `project_id`. A `ws-` id is sent as `workspace_id` and `project_id`. Any other value is `run_id` only. The Modal gateway sets `MEMORY_IMPL=mubit` when `baansafe-mubit` injects both Mubit values, the same gate as System 2. A retrieve error returns no items. An empty `baansafe-demo` project also returns no items (open item 36). `make modal-secrets` can also sync `MUBIT_PROJECT_ID`. Tests clear that variable so a developer shell cannot leak it. Describe Mubit as the gateway, the trace host, and the control-plane memory store on that path. The turn still does not build a `MemoryRecord`.
- Melanie keeps `MemoryItem.kind` as `similar_case`, `prior_failure`, `policy`, or `correction`. The control-plane map is `lesson` → `correction`, `rule` → `policy`, `fact` → `similar_case`. Those four names also pass through when Mubit sends them. `gateway.route.handle` retrieves on every turn and emits stage `memory` with `latency_ms` and `mode=` in the note. `memory/adapter.py` says the gateway is the only retrieval caller. Fixture `POST /cases` and `GET /cases/{id}` also call `retrieve` from `_refresh_memory`, and that call writes no trace. `eval/extract_eval.py` and `eval/correction_loop.py` call it offline. `gateway/graduation.py` counts `training/log.py` events. It does not query Mubit (open item 35).
- System 2 keeps its `system2_unavailable` fallback when a replay cache miss raises `ValueError("s2 cache miss")`. `orchestrate` catches `ValueError`. The replay completer does not open a socket.
- System 2 calls only the Mubit host. `llm/client.py` and `llm/openai_client.py` refuse a host that is not `api.mubit.ai` or a `mubit.ai` subdomain. Live RL calls go through `llm.client.complete`. A cache hit emits `mubit_chat` with `status=cache_hit` and host `rl_s2_cache` and does not open a socket.
- `sim_events.json` `learning.promote_after` is 2, the same number as `correction_loop.graduation_threshold` and `correction_loop.escalation_threshold`. The page story is correction escalation to System 2. It does not promote into System 1. The remaining split is the RL overlay, which can still write a System 1 rule when `RL_OVERLAY` is set (open item 5).
- To match `GET /context`, Moly returns `matched_province`, `near_flood_extent`, `distance_to_live_flood_m`, and `regional_reservoirs` on every response. Locally `ENRICH_IMPL` is `data` because `districts.json` exists. While enrichment is off those values stay null or false, plus `"enrich": "off"`.
- To match `GET /resources`, the body keeps `boats`, `ambulances`, `shelters`, and `welfare_points`. Boats, ambulances, and shelters now include OpenStreetMap units with `id` `{kind}-{osm_type}-{osm_id}` and `capacity` null, listed before the fictional units. Welfare points stay the fictional file.
- `near_flood_extent` is a data flag only. It is not in `route_to_system_2_if_any`, and it never changes priority.
- System 1 matches Thai district names, English `Name District`, a bare English name of two or more words that are not all common English (`Mae Mo` matches; `Hot`, `Long`, and `Than To` do not), and the caller spellings in `DISTRICT_ALIASES` (`Watthana` → `Vadhana`, `Sathorn` → `Sathon`, `Pathumwan` → `Pathum Wan`, `Klong Toey` and `Khlong Toey` → `Khlong Toei`, `Ladprao` and `Lat Prao` → `Lat Phrao`, `Phayathai` → `Phaya Thai`, `Huay Kwang` → `Huai Khwang`, `Bangrak` → `Bang Rak`, `Thonburi` → `Thon Buri`, `Don Muang` → `Don Mueang`, `Jatujak` → `Chatuchak`). An alias matches bare and as `Alias District`. The stored location is the gazetteer name, so `Watthana` becomes `Vadhana District, Bangkok Province` at confidence 0.85. Thai names come from `admin_districts.json`, `districts.json`, and the gazetteer snapshot. Aliases are added only from the gazetteer snapshot. Need, danger, and vulnerability phrases are English word-boundary matches. `4913304` removed the Thai lists. A Thai caller gets no System 1 needs from those families and escalates more often (open item 24).
- Country packs under `countries/` are documents only. Nothing there is imported. Thailand stays the demo.
- To match human-correction graduation, System 2 treats the `complex_situation` flag and the `graduated-*` correction `MemoryItem` as recommendations only. That path reads `TRAINING_EVENTS_PATH` (`/data/events.jsonl` on Modal) and caches by path, mtime, size, threshold, and labels. It sets no priority and does not move a pattern into System 1. The RL loop is the other meaning of graduation: `correction_loop.graduation_threshold` can write a System 1 rule when `RL_OVERLAY` is set (open item 5).
- To match a cascade, consumers read `source_outcomes[0]` as the final outcome. On a cascade, `[1]` is the System 1 handoff. `merge` builds `[final, *prior]`. Melanie's orchestrator sets `Outcome.system` to `system_2` on that deciding outcome, so `source_outcomes[0].system` is `system_2` whenever System 2 decided.
- To match System 2, the signature is `system2.decide(case, handoff, recommendation)`. `handoff` is the escalating System 1 outcome. `recommendation` is the overlay entry for that narrow signature, or null. A Sapling `violation` must surface as `requires_human`, as the `route`, or as `missing_evidence`. `merge` does not read a `sapling_verdict` string.
- `ui/sim/sim.js` keeps the strings `Mubit → Nemotron` and `token_cost_usd: null`. `ui/correct.js` keeps `Mubit → Nemotron`. `tests/test_town_sim.py` `test_wire_frontend_p0_contracts` reads those files and asserts the strings. `token_cost_usd` stays null because `llm.token_price_usd` is `TODO_HUMAN`.
- The town shows a failed turn as a phone note: "The gateway did not answer." plus the status and the JSON body. A missing Mubit URL or key is HTTP 503, and that `detail` is inside the note. A Nemotron 429 does not take this path. It becomes a `system2_unavailable` outcome.
- To match the chooser, both sides must keep the flag strings `safeguarding`, `conflicting_evidence`, `aid_exception`, and `complex_situation`, and the `ExtractedFields` names (`location`, `location_confidence`, `people_count`, `vulnerable`, `medical`, `danger`, `needs`), stable.
- To match extract, Moly keeps need, danger, and vulnerability phrases English-only, on word boundaries, and matches district names in Thai, as `Name District`, as a bare multi-word English name, and through `DISTRICT_ALIASES`. An English negator in the three words before a match drops it. Caller turns count, plus an operator question the caller confirms with yes, yeah, correct, or that's right. Those confirmed facts count for `vulnerable`, `people_count`, and `danger` only. `F15` is still misrouted: the child is only in an operator turn, and the caller does not confirm it. Thai calls get no System 1 needs (open item 24).
- `system2.orchestrator_model` is `nvidia/nemotron-3-nano-30b-a3b` and `system2.max_latency_ms` is 10000, so `orchestrate` calls `llm.complete` before Sapling. An agent set both values, and `routing.yaml` `mode: cascade`. A human has not confirmed them (open item 4). This note does not unset them.
- `_unavailable` keeps the reason clause `P1 for life-safety trigger X [cite]`. Several triggers are comma-separated. Citations are sorted and joined with `;`. The tests assert the trigger name and the citation are in `reason`, and that a non-life-safety outage reason does not contain `P1`.
- A unit matches only when its `district` string is a substring of System 1's `<name_en> District, <Province> Province`. `merge` tests `unit.district.lower() in fields.location`.
- A P1 outage does not hold a boat. `_unavailable` sets `needs=[]` and `route=supervisor_escalation`, so `merge` does not fan out, and `ledger.release_case` drops holds from earlier turns of that case. To keep a boat, `merge` has to read the needs from the System 1 handoff (`source_outcomes[1]`). This note does not make that change.
- `ui/sim/sim.js`, `ui/sim/index.html`, and `ui/sim/README.md` say `gateway.route_chooser` is the field precheck. `config/routing.yaml` `mode` is `cascade`. `HANDOVER.md` at `5108994` strikes the old gap that claimed those files still say `TODO_HUMAN`. Its header still names tip `61663d0`.
- `HANDOVER.md` records a hosted smoke with `/hosting` live and a System 2 `mubit_chat` hop. This note did not call that URL. The same secret gate sets `MEMORY_IMPL=mubit` (open item 34).
- `load_dispatch_resources` does not give Sukhumvit units for town calls. `data/snapshots/places.json` has Lampang, Phrae, Nan, and Phayao only. Extract can still resolve free text `Watthana` to `Vadhana District, Bangkok Province` from `data/snapshots/gazetteer.json`. The phone posts a fixture id, so `fields.location` stays the fixture district. A same-district match is one of those northern OpenStreetMap units.
- Melanie's `.env` needs `MUBIT_BASE_URL` as well as `MUBIT_API_KEY`. `llm/client.py` raises when either is missing. `make modal-secrets` writes both into `baansafe-mubit`. `make sync` skips that secret when `MUBIT_BASE_URL` is blank. `tests/conftest.py` sets `MUBIT_BASE_URL` to `https://api.mubit.ai` and drops the key, so a clean test run does not need `.env`.
- Melanie adopts `system2.orchestrator_model` `nvidia/nemotron-3-nano-30b-a3b` and the list coercion in `system2/orchestrator.py`. `needs`, `missing_evidence`, and `plan` may arrive as a string or a bool. A string becomes a one-item list. `true` becomes `["unspecified"]`. `false` and null become `[]`.
- Moly returns `RouterDecision.dispatches` on `POST /triage` and `POST /cases/{id}/turns`. Each dispatch has `need`, `resource_kind`, `resource_id`, and `status`. There is no `vehicle` field. The town prefers a provisional `resource_id` from that list. `ui/sim/data/rulebook.json` is a teaching overlay and marks a row that disagrees. A unit the block can draw is one of `boat-fictional-01`, `amb-fictional-01`, `shelter-fictional-01`, and `welfare-fictional-01`.
- The desk learning count is `promote_after` 2. Human-correction graduation never moves a pattern into System 1. The RL loop can, when `RL_OVERLAY` is set (open item 5).
- Enrichment tries `data/processed/districts.json` first (50 rows, every `province` null), then `admin_districts.json` (108 rows). Hat Yai and Mueang Songkhla resolve as Hat Yai District and Mueang Songkhla District, Songkhla Province. Rain stays null on those admin-only matches, because weather rows key to a `districts` `location_id` and the Open-Meteo snapshot does not name them. `regional_reservoirs` stays null there too: the province is Songkhla, and reservoirs fire only for Lampang, Phrae, Nan, and Phayao. A northern name such as Mae Tha matches `districts` first, so `matched_province` stays null and `_regional_reservoirs` never sees the admin row that has the province set (open item 25). The plan bullet in `docs/wire-frontend.md` that still asks for this fallback is already in `enrich/context.py`.
- `gateway/route.py` stores `location_context` on `case.resources`. The desk panel reads that field. It does not call `GET /context`.
- `POST /cases/{id}/dispatches/confirm` and `/cancel` are live. Accept and Reject in the page call them. `GET /resources` subtracts `ledger.reserved_total` from each unit's `available`. The Modal app sets `max_containers=1`, so those three share one ledger. A confirm after that container has scaled down, or against a process that does not hold the reservation, returns 422 (open item 11).
- `data.demo_event` is `Sukhumvit / Watthana (Bangkok)`. `scripts/validate.py` `DECIDED` requires that exact string. A checkout that still has `Hat Yai / Songkhla` fails `make validate`. The town basemap matches the decision. Most household `location_label`s are still Lampang, Phrae, Nan, or Phayao, so `location_context` does not match Watthana for those calls. F17 and F18 are the Sukhumvit exceptions (open item 9).
- Bare `unaccompanied` adds `child` only when no fact sentence contains `adult` or `adults`. "An unaccompanied adult is at the shelter" sets neither `child` nor `safeguarding`. The check is any sentence in the fact list, not the same sentence as `unaccompanied` (open item 22). The word `child` still tags `child` on its own.
- `gateway.auth` stays `TODO_HUMAN` (a note is recorded; the request is not rejected). `data.demo_event` and the three memory leaves are decided.
- `VULNERABLE_PHRASES` tags `child` for `child`, `children`, `kid`, `kids`, `grandchild`, `grandchildren`, `baby`, `babies`, `son`, `daughter`, and `infant`, each on a word boundary. `children`, `kids`, `babies`, `grandchild`, and `grandchildren` set `child`. With an alone-phrase they also set `safeguarding`. Bare `unaccompanied` adds `child`, and with that tag sets `safeguarding`, unless some fact sentence contains `adult` or `adults` (`2431e44`). `not unaccompanied` sets neither. "The child is unaccompanied. The adults are on the roof." still returns `child` and `safeguarding`, because the word `child` matches on its own. "She is unaccompanied. The adults are on the roof." returns neither. Extract on `syn-safeguarding-child-01-en`, `02-en`, `04-en`, `05-en`, `01-mixed`, and `05-mixed` sets `child` and `safeguarding` when those transcripts do not say `adult`. `F15` is still the unconfirmed operator turn. An unaccompanied grandmother is still `elderly` plus `child` (open item 22).
- System 2 treats `safeguarding` as a human decision. The flag is a System 2 trigger. `system2/orchestrator.py` `_post_rules` forces `requires_human` on that flag in the same branch as an aid case. It does not rewrite the route to `aid_caseworker`. `merge` still maps the flag to `escalate_to_supervisor`.
- A System 2 or RL replay cache that includes the extracted fields misses these calls. `eval/rl/run.py` keys `s2_cache.jsonl` by the model and the message list, and that list includes `fields` and `policy_flags`.
- Town `F17` and `F18` do not use `children`, `kids`, `babies`, `grandchild`, `grandchildren`, or `unaccompanied`. Their lines are the renter payment and the household list.
- The live call UI calls `POST /session` before the welcome and before `POST /cases`. The body is `{caller_ip, simulated, note}` from `api/caller_ip.py`. #9 merged as `f790191`. #11 merged as `46101d8`. #12 merged as `b6bfa0f`. There is no open pull request.
- Moly's `router.merge` and the call UI ignore `caller_ip` and `caller_ip_simulated` on `CaseState.resources`, or the page shows them as a session row. They are not a dispatch resource. `merge` fans out from `load_dispatch_resources()`, not from that dict. The town's `live.resources` is `GET /resources`.
- `fa8a4ca` does not change a contract. `contracts/` is untouched. `data.production_db` stays `TODO_HUMAN`. Melanie's `memory/`, `system2/` (including aid exceptions), and `system1/aid_eligibility.py` do not read SQLite. `store.available()` is the runtime check. `db_exists` is gone.
- F17 and F18 keep `needs` `["aid_payment"]` and route `aid_caseworker`. Their locations on main are the Sukhumvit soi strings from #9.
- A landmark location confidence from 0.58 to 0.66 should make System 1 ask a confirm question. On #9 those scores are 0.58 (`bldg-0441`), 0.64 (`bldg-tower-pink`), and 0.66 (`bldg-0328`), and they stay on the page (`planned.path.confidence`). The gateway does not receive them. Confidence below 0.7 is a System 2 trigger. Below `system_1_min_confidence` (0.80) System 1 escalates. The only System 1 question is `How many people are with you?` when `people_count` is missing.

### 3.1 Phone turn to the gateway

Producer: the town phone (`ui/sim/sim.js` `runPlaceCall`). Consumer: Moly's `gateway.route.handle` via `api/routes/endpoints.py` `execute` (`use_stubs=True`).

Path: free-text and phone `POST /cases` with `{ "transcript": [{ "t_ms": 0, "speaker": "caller", "text": "..." }] }`. A scripted or saved-prompt household posts `{ "fixture_id": "F02" }`. Both then `POST /cases/{case_id}/turns` with a `TranscriptTurn`. The turn response is `TurnResult`: `case` (`CaseState`) and `decision` (`RouterDecision`). `POST /triage` takes a full `CaseState` and returns the same `RouterDecision`. The phone does not call `/triage`. `ensureSession` posts `POST /session` first.

`CaseState` required: `case_id`, `caller_id_hash`, `transcript`, `fields`, `received_at`. `TranscriptTurn` required: `t_ms` (int ≥ 0), `speaker` (`caller` or `operator`), `text` (non-empty).

To match the gateway, Melanie must provide either a known `fixture_id` or a `transcript` of `TranscriptTurn`s. A body with neither is HTTP 422. Moly must accept that turn and return one `RouterDecision`. He must not route from `fixtures/... expected.system`. The chooser reads fields and `policy_flags`.

Minimal turn:

```json
{ "t_ms": 1000, "speaker": "caller", "text": "Our rice is finished." }
```

Mismatch: a scripted or saved-prompt create still posts `fixture_id`, so extract does not rewrite those hand-filled fields. Free-text and phone creates do extract. The chooser copy on the page says field precheck. `HANDOVER.md` on main no longer claims those strings are `TODO_HUMAN` (open item 30).

### 3.2 Extracted fields to the chooser and to System 1

Producer: Moly `system1.extract.extract(transcript, districts=None) -> (ExtractedFields, flags)`. Consumer: `gateway/chooser.py` and `system1/decide.py`. Melanie's System 2 will read the same `CaseState.fields` when `orchestrate` returns.

`ExtractedFields`: `location` (str or null), `location_confidence` (0–1 or null), `people_count` (int ≥ 0 or null), `vulnerable` (str list), `medical` (bool, default false), `danger` (str list), `needs` (list of `Need`). No field is required; defaults are null, false, and empty lists. `Need`: `rescue`, `medical`, `water`, `food`, `shelter`, `evacuation`, `power`, `information`, `aid_payment`.

The gateway attaches the returned flags plus `keyword_extraction` only when it actually extracts.

Chooser triggers (`config/escalation.yaml` `route_to_system_2_if_any`), any one sends the turn to System 2:

- `fields.medical`
- `vulnerable` contains `oxygen_dependent` or `immobile`
- location is missing, confidence is missing, or confidence is below 0.7
- `policy_flags` contains `safeguarding`, `conflicting_evidence`, `aid_exception`, or `complex_situation`
- `needs` contains `rescue`, `medical`, or `aid_payment`

`near_flood_extent`, `heavy_rain_forecast`, `heavy_rain_observed`, `in_active_flood_extent`, and `repeat_flood_area` are not in that list. The gateway attaches them as data flags. They do not change priority or the route.

`extract` reads caller turns, plus an operator question the next caller sentence confirms (`yes`, `yeah`, `correct`, or `that's right`). Confirmed operator text counts for `vulnerable`, `people_count`, and `danger` only, never for needs or flags. A negator in the three words before a match drops it. Aid phrases and minimising phrases are exempt: "we cannot get the payment" and "not eligible" stay aid signals. Suggested flags are `conflicting_evidence` (minimising language plus danger, rescue, medical, or a child, elderly person, or immobile person), `safeguarding` (a child and an alone-phrase; `unaccompanied` alone counts as both), and `aid_exception` (an aid phrase plus a refusal). Water at a door, step, or inside a room, or in the street, adds danger `rising_water`. That also adds need `rescue` when a child, elderly person, immobile person, or oxygen-dependent person was extracted, or when the water is at the building and evacuation was not already a need. "bus shelter" is not a shelter need.

To match the chooser, Melanie must leave those field names and flag strings as they are when she builds a non-fixture case. Moly keeps need, danger, and vulnerability phrases English-only, on word boundaries. District names match Thai, English `Name District`, a bare multi-word English name that is not all common English, and `DISTRICT_ALIASES`. A `Watthana` hit is stored as `Vadhana District, Bangkok Province`. A confirmed operator question counts for `vulnerable`, `people_count`, and `danger` only. `system1.extraction_method` is `rules-only`. `system1.extraction_model` stays `TODO_HUMAN` and the rules do not read it. A Thai free-text case gets no needs from extract and escalates to System 2 more often (open item 24). `orchestrate` passes `case_id` as a keyword, so a replacement completer must accept `**kwargs` (open item 28).

Minimal fields the fast path can accept:

```json
{
  "location": "Mae Tha District, Lampang",
  "location_confidence": 0.93,
  "people_count": 3,
  "vulnerable": [],
  "medical": false,
  "danger": [],
  "needs": ["food"]
}
```

Mismatch: `make extract-eval` scores extract against hand-filled fixture fields, and again against the scripted sim callers. An unsafe answer is a case whose true fields go to System 2 while the extracted fields get a System 1 answer with `requires_human` false. Fixture cases on the phone never take the extract path. `F15` is still misrouted: hand fields include `vulnerable: child`, the word "child" is only in an operator turn ("I can hear a child crying"), and caller text says "They are upset" and "invented bus shelter". `0fdc34e` closed the plural miss. `children`, `kids`, `babies`, `grandchild`, and `grandchildren` set `child`, and with an alone-phrase they set `safeguarding`. Bare `unaccompanied` adds `child` and sets `safeguarding` unless a fact sentence contains `adult` or `adults` (open item 22). `not unaccompanied` sets neither. Extract on the six synthetic transcripts named above returns that flag when they do not say `adult`. This note did not re-run `make extract-eval`. An unaccompanied grandmother is still `elderly` plus `child`. The word `adult` in the fact list suppresses only the implied tag. Open item 12: `G01`–`G04` are labelled `expected.system` `system_2` with need `rescue`, matching the precheck. Town `calls[].expected_system` is the fixture label, not the chooser's result.

### 3.3 Memory items to System 1 and the router

Producer: Melanie `memory.adapter.retrieve(case) -> list[MemoryItem]`. Consumer: Moly `system1.decide` (duplicate rule) and `router.merge` (correction notes). The gateway assigns the list onto `case.memory_context` before the chooser.

`MemoryItem` required: `memory_id`, `kind`, `summary`, `relevance` (0–1). Optional `source_case_id`. `kind`: `similar_case`, `prior_failure`, `policy`, `correction`.

`MEMORY_IMPL=mock` (default) reads `mocks/memory_context/{case_id}.json`, or an empty list when the file is missing. `MEMORY_IMPL=mubit` calls `memory.mubit.retrieve`, which posts `/v2/control/query` with an httpx timeout of 20 seconds and maps evidence to `MemoryItem`s (`fact` → `similar_case`, `lesson` → `correction`, `rule` → `policy`; `prior_failure` passes through). The adapter returns `[]` when that call fails, and when the project has no evidence. The query text includes location, needs, and the last transcript line. It does not include `caller_ip`. The memory trace from `handle` carries `latency_ms` and `mode=`. System 2's budget stays 10 seconds and starts after this query (open item 36).

To match System 1, Melanie must provide `kind=similar_case`, a non-empty `source_case_id`, and `relevance` ≥ 0.9 when the call is the same household again. Moly treats that as `route=duplicate_merge` inside `decide`. Below 0.9 it is not a duplicate. Moly must copy `kind=correction` summaries into `RouterDecision.policy_notes` (the note prefix is `retrieved correction memory:`).

Minimal duplicate item (this is `mocks/memory_context/F09.json`):

```json
{
  "memory_id": "mem-F09-open-case",
  "kind": "similar_case",
  "summary": "Open case F08 from the same synthetic household: drinking water, Song District, Phrae. Not yet delivered.",
  "relevance": 0.95,
  "source_case_id": "F08"
}
```

Mismatch: `ui/sim/data/town.json` `calls[].memory` is only `kind` and `summary`. It has no `memory_id` or `relevance`, so it is not a `MemoryItem`. The feed placeholder `{memory_count}` uses that array's length, not `case.memory_context`. `tests/test_town_sim.py` locks `buildings[].fixture` (`expected_route`, `expected_priority`, `expected_system`, `location`, `people_count`) and `calls[].opening` to `fixtures/scenarios/`. Those summaries omit `needs`, `medical`, `danger`, and the transcript. The gateway never reads `town.json`.

`memory.adapter.store_record` is not called from `gateway/` or `api/`. Mock mode raises. `MEMORY_IMPL=mubit` would post the record to `/v2/control/ingest`. A correction posted to `POST /cases/{id}/corrections` calls `store_correction`: mock mode appends JSONL, and mubit mode posts a lesson. That ingest does not soft-fail. The endpoint catches only `NotImplementedError`, so a failed ingest is HTTP 500 and `append_event` does not run (open item 35). See 3.6 for what a `MemoryRecord` needs.

### 3.4 One Outcome into the router

Producer of a System 1 outcome: Moly `system1.decide` when the real switch is on, otherwise `mocks/s1_stub/{id}.json` or `_fallback_outcome`. Producer of a System 2 outcome: Melanie `system2.decide(case, handoff, recommendation)`, live through `llm.complete`. Consumer: Moly `router.merge.merge(case, outcome, extra_notes, prior=())`.

`Outcome` required: `system` (`system_1` or `system_2`), `outcome` (`fast_route`, `reasoned_recommendation`, or `escalate`), `priority` (`P1`–`P4`), `needs`, `route`, `confidence` (0–1), `reason` (non-empty), `requires_human`, `escalate`. Optional: `reasoning`, `missing_evidence`, `next_question`, `latency_ms`.

`Route`: `rescue_coordination`, `medical_response`, `welfare_distribution`, `shelter_placement`, `aid_caseworker`, `information_only`, `duplicate_merge`, `supervisor_escalation`.

System 1 `decide` order when it runs: System 2 triggers → escalate; else similar-case duplicate → `duplicate_merge`; else needs outside `NEEDS_TABLE` (`water`, `food`, `shelter`, `evacuation`, `power`, `information`) or no needs → escalate; else location confidence under `system_1_min_confidence` (0.80) → escalate; else missing `people_count` → `next_question` `How many people are with you?`; else `fast_route`. `rescue`, `medical`, and `aid_payment` are not in the table. System 1 sets `reasoning` null and does not call Sapling.

With `mode: cascade`, a System 1 `escalate=true` outcome hands the turn to System 2 with the S1 outcome as `handoff` and the learned `recommendation` when the overlay has one — except the no-stub fallback (`missing_evidence == ["fixture_stub"]`), which never cascades. `mode: exclusive` keeps the old one-system turn. `merge` still turns `outcome.escalate` into `next_action=escalate_to_supervisor` when no cascade ran.

To match the router, Melanie must return one `Outcome` from `system2.decide` with those required fields, `system=system_2`, and `outcome=reasoned_recommendation` when she has reasoned. On a cascade she receives that escalate as `handoff`. Moly passes the deciding outcome to `merge` with earlier outcomes as `prior`.

Minimal System 1 outcome:

```json
{
  "system": "system_1",
  "outcome": "fast_route",
  "priority": "P3",
  "needs": ["food"],
  "route": "welfare_distribution",
  "confidence": 0.93,
  "reason": "Clear fast-path request with a confident location.",
  "reasoning": null,
  "missing_evidence": [],
  "next_question": null,
  "requires_human": false,
  "escalate": false,
  "latency_ms": 1
}
```

`merge` next action, first match: `supervisor_escalation` or policy flag `safeguarding` → `escalate_to_supervisor`; `aid_caseworker` → `escalate_to_supervisor`; `escalate` → `escalate_to_supervisor`; `duplicate_merge` → `finalize_case`; any `missing_evidence`, a `next_question`, or no `fields.location` → `ask_next_question`; `information_only` → `finalize_case`; else `create_provisional_dispatch`.

Dispatch fan-out only for that last action, one `Dispatch` per mapped need: `rescue`→`boat`, `medical`→`ambulance`, `water` and `food`→`welfare_point`, `shelter` and `evacuation`→`shelter`. `power`, `information`, and `aid_payment` produce none. The turn uses `load_dispatch_resources()`: OpenStreetMap boats, ambulances, and shelters from `data/snapshots/places.json`, then the fictional units in `mocks/resources.json`. Welfare points are fictional only. A unit this case already holds wins, else a same-district unit (`unit.district.lower()` contained in `fields.location`), else the first usable unit, else `status=unfilled` and `resource_id` null. The district string has to be a substring of `<name_en> District, <Province> Province`. Usable means `available` minus reservations other cases hold in `router/ledger.py`. After the fan-out, `ledger.release_case` keeps only the resource ids on this turn's dispatches, so an action with no fan-out frees earlier holds for that case. Neither JSON file is rewritten. Holds live in this process and reset on restart. With no district match, that first usable unit is an OpenStreetMap unit when the kind has one. Open item 3. There is no Sukhumvit unit in the snapshot, so a town call does not reserve one (open item 9).

`Dispatch` required: `need`, `resource_kind` (`boat`, `ambulance`, `shelter`, `welfare_point`), `status` (`provisional` or `unfilled`). Optional: `resource_id`, `same_district` (default false), `note`.

`RouterDecision` required: `case_id`, `next_action`, `final_priority`, `final_route`, `requires_human`, `source_outcomes` (the deciding outcome first; length 2 on a cascade, `[system_2, system_1]`). `policy_notes` and `dispatches` default to empty lists. `NextAction`: `ask_next_question`, `create_provisional_dispatch`, `escalate_to_supervisor`, `finalize_case`, `request_more_evidence`.

`final_priority` and `final_route` copy the outcome. `requires_human` is true when the outcome says so, or the route is `supervisor_escalation` or `aid_caseworker`, or `safeguarding` is in `policy_flags`, or any dispatch is `unfilled`.

### 3.5 RouterDecision to the town phone

Producer: Moly `router.merge`. Consumer: Melanie's phone and feed in `ui/sim/sim.js`.

The phone reads these fields and no others for the reply, the light, and the feed placeholders:

- `final_priority`, `final_route`, `next_action`, `requires_human`
- `source_outcomes[0].system`, `.reason`, `.needs`, `.next_question` — `[0]` is always the deciding system; a cascade appends the S1 outcome after it
- a `policy_notes` line matching `/selected/` (the trace step "System 1" / "System 2")
- `GET /cases/{id}/trace` stages `gateway` and `router` (`notes`)

`operatorReply` uses `final_priority`, `final_route`, `source_outcomes[0].needs`, `source_outcomes[0].next_question`, and `requires_human`. The vehicle comes from `ui/sim/data/rulebook.json` (`matchRule`), which looks at `final_priority`, `final_route`, outcome `needs`, the typed text, and whether the building's `water_m` is at least 0.25. The rulebook file says it is a draft and not repo policy.

`drawCallLights` stores `callResults` from `turned.decision` and outlines an answered house with `OUTLINE_HEX[decision.final_priority]`: P1 `#ff3b30`, P2 `#ff9f1a`, P3 `#3ddc84`, P4 `#c084fc`. It then paints the active caller's building `#ff3b30` and the `matchRule` destination `#2f6bff`, so those two buildings do not show `final_priority`. The call-list badge and `#priority-badge` use the CSS classes: P1 `#d1241a`, P2 `#ED7401`, P3 `#0076D8`, P4 `#014855`.

To match the phone, Moly must keep those `RouterDecision` and `Outcome` fields populated on every turn, including stub turns. `source_outcomes` keeps the deciding outcome first (`[deciding, *prior]`). Melanie reads `final_priority` for answered houses that are not the active call and not the destination. CR-003 is tagged `v0.3-contracts`. Melanie's town must show the router's reserved `resource_id`, and that id has to be one the block can draw. The placed ids are the four fictional ids in `mocks/resources.json`. `sim.js` prefers `dispatches`, `resource_id`, and `resource_kind`. An OpenStreetMap id is not on the block.

Minimal decision the phone can render:

```json
{
  "case_id": "F02",
  "next_action": "create_provisional_dispatch",
  "final_priority": "P3",
  "final_route": "welfare_distribution",
  "requires_human": false,
  "source_outcomes": [
    {
      "system": "system_1",
      "outcome": "fast_route",
      "priority": "P3",
      "needs": ["food"],
      "route": "welfare_distribution",
      "confidence": 0.94,
      "reason": "Clear same-day food request.",
      "requires_human": false,
      "escalate": false
    }
  ],
  "policy_notes": ["gateway selected system_1 exclusively"],
  "dispatches": [
    {
      "need": "food",
      "resource_kind": "welfare_point",
      "resource_id": "welfare-fictional-01",
      "status": "provisional",
      "same_district": false
    }
  ]
}
```

Mismatch: open item 10 below. The feed's ACCEPTED/REJECTED verdict comes from `sim_events.json` scores. `confidence_threshold` is now 0.8, matching `system_1_min_confidence`. `learning.promote_after` is still 3, and the copy says the fast path can take the call. That is not `source_outcomes[0].system`, and it is not graduation. It can say ACCEPTED while that system is `system_2`, or the reverse. Sapling cards use a simulated `verdict` (`supported`, `violation`, `missing`, `unsure`). The gateway does not add `sapling_verdict` on the stub path. `contradicted` is a real Sapling label and is not one of the simulated card verdicts. There is no `GET /cases/{id}/events` stream. `BaanSafeSim.attachLiveFeed` is the unused hook.

### 3.6 Corrections to memory and to a MemoryRecord

Producer: Moly `ui/correct.js` `buildCorrectionBody`, posted by the town Reject button and by the transcript player. Consumer: Melanie `memory.adapter.store_correction` and `contracts.training.adapt_correction` → `training/log.py`. Endpoint: `POST /cases/{case_id}/corrections`.

`Correction` required: `correction_id`, `case_id`, `corrected_by` (`operator`, `supervisor`, `caseworker`), `field`, `reason`, `created_at`. The API fills `correction_id` and `created_at`. The UI sends `corrected_by=operator`, `field=<task>`, `reason`, `task`, `group_id`, `input_ref`, `output_correct`, `source=human`, `model_version`, and `old_value` / `output_model` when the decision maps to a closed label.

`task`: `s1_triage`, `s2_action`, `sapling_verdict`. `ui/correct.js` `inferTask`: System 2 plus an aid route, `aid_payment`, or flag `aid_eligibility` / `aid_exception` / `aid_denial` → `sapling_verdict`; other System 2 → `s2_action`; otherwise `s1_triage`. `output_correct` must be a closed label for that task (`contracts/training.py` `S1Label`, `S2Action`, `SaplingVerdict`). `S2Action` is the same five strings as `NextAction`.

`InputRef` required: `case_id`, `lang` (`th`, `en`, `mixed`). Optional: `turn_ids`, `policy_ids`, `memory_ref`. The UI sets `turn_ids` to `case_id:index:t_ms`, `memory_ref` to `memory_context[0].memory_id` or null, and `policy_ids` from flags or policy-kind memory ids that match `^[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+$`.

`TrainingEvent` required: `task`, `group_id`, `input_ref`, `output_correct`, `reason`, `source` (`human`, `coach`, `sim`), `model_version`, `policy_version`. `adapt_correction` fills `policy_version` from the corpus when the body omits it. A v1 body that fails adaptation is HTTP 422. A legacy body without v1 fields still stores a `Correction` and skips the log.

To match the training log, Moly must keep sending `task`, `input_ref`, `output_correct`, `source`, and `reason` as above. Melanie must keep `store_correction` accepting that `Correction`. She must not expect `output_model` for `s1_triage`: `outputModel` returns null unless the task is `s2_action` (the `next_action`) or `sapling_verdict` (a `sapling_verdict=` note). There is no such note on the stub path, so a Sapling correction has no `output_model`.

Minimal body the UI posts (the API adds id and time):

```json
{
  "corrected_by": "operator",
  "field": "s1_triage",
  "new_value": "sphere_food_short",
  "reason": "Food is the need, not a medical case.",
  "task": "s1_triage",
  "group_id": "F02",
  "input_ref": {
    "case_id": "F02",
    "turn_ids": ["F02:0:0"],
    "lang": "en",
    "policy_ids": [],
    "memory_ref": "mem-f02-similar"
  },
  "output_correct": "sphere_food_short",
  "source": "human",
  "model_version": "s1@stub"
}
```

`MemoryRecord` required: `record_id`, `case_id`, `case_summary`, `evidence` (`ExtractedFields`), `decision` (`RouterDecision`). Optional: `outcome_label`, `failure`, `corrections`.

`memory.mubit.write` accepts a `MemoryRecord` and posts a fact to `/v2/control/ingest`. Nothing in `gateway/` or `api/` builds that record, so the turn does not call `store_record`. Mock mode still raises. A System 1 correction lands through `store_correction`: a JSONL line in mock mode, or a lesson ingest when `MEMORY_IMPL=mubit`, and, when v1 fields are present, a `TrainingEvent`. It does not land inside a `MemoryRecord`. `append_event` runs only after `store_correction` returns. A failed mubit ingest raises `RuntimeError`, the endpoint does not catch it, and the training log is unchanged, so graduation cannot see that correction (open item 35).

Minimal record, if she wires the write:

```json
{
  "record_id": "rec-f02-1",
  "case_id": "F02",
  "case_summary": "Same-day food request, Mae Tha District.",
  "evidence": {
    "location": "Mae Tha District, Lampang",
    "location_confidence": 0.93,
    "people_count": 3,
    "needs": ["food"]
  },
  "decision": {
    "case_id": "F02",
    "next_action": "create_provisional_dispatch",
    "final_priority": "P3",
    "final_route": "welfare_distribution",
    "requires_human": false,
    "source_outcomes": [
      {
        "system": "system_1",
        "outcome": "fast_route",
        "priority": "P3",
        "needs": ["food"],
        "route": "welfare_distribution",
        "confidence": 0.93,
        "reason": "Clear fast-path request with a confident location.",
        "requires_human": false,
        "escalate": false
      }
    ]
  },
  "corrections": []
}
```

### 3.7 Aid eligibility and exceptions

Producer: Melanie `system1.aid_eligibility.check(case) -> AidEligibility` and `system2.aid_exceptions.propose(case) -> Outcome`. Consumer: the HTTP stubs. Moly's `gateway/route.py` does not call either function.

`AidEligibility` required: `case_id`. `status` is only `unset` or `needs_human` (default `unset`). Optional `policy_id`, `notes`. The model cannot store an approval.

Endpoints: `GET /aid/eligibility?case_id=` and `POST /aid/exceptions` with a `CaseState`. Both return HTTP 501.

To match the contract, Melanie must return `AidEligibility` with `status` `unset` or `needs_human` and must not add an approved status. Moly must not treat a welfare `RouterDecision` as an aid payment. `aid_payment` is a System 2 trigger and is not a System 1 needs-table row. `policies.authoritative_set` is `TODO_HUMAN`, so Sapling does not treat the corpus as the binding set unless the case names rule ids (`system2/sapling_policy.py`). `policies/flood.yaml` is loaded with the rest of the corpus. Its depth figures are not a 1669 colour, and the chooser does not read them. Nothing under `countries/` is imported. Thailand stays the demo.

### 3.8 System 2 outcome to Sapling, then to the router

Producer: Melanie `system2.orchestrator.orchestrate` then `system2.sapling.verify_before_router`. Consumer: Moly `router.merge`, only after `decide` returns an `Outcome`.

Sapling runs only when `outcome.system` is `system_2`, `system2.use_banyan_sapling` is true, and the check is `aid_eligibility` or `denial` (`system2.sapling_scope`). `supported` leaves the outcome. `violation` sets `requires_human`, `route=supervisor_escalation`, and prefixes the reason. `unsure`, `missing`, and `contradicted` set `requires_human` and append `sapling_<verdict>` to `missing_evidence`. The committed client (`sapling.client=stub`) reads `mocks/sapling_stub/` and does not open a socket. `SAPLING_IMPL=live` raises while `sapling.hosting`, `sapling.gpu`, `sapling.model_id`, or `sapling.thai_handling` is `TODO_HUMAN`.

To match the router, Melanie must return one `Outcome` from `system2.decide(case, handoff, recommendation)` with `system` `system_2`. On a cascade, `source_outcomes[0]` is that outcome and `[1]` is the System 1 handoff. A Sapling `violation` must surface as `requires_human`, as the `route`, or as `missing_evidence`, because `merge` does not look for a `sapling_verdict` string. The same is true of a human handoff (`unsure`, `missing`, `contradicted`). Moly must keep mapping `aid_caseworker` and `supervisor_escalation` to `escalate_to_supervisor`, and must keep mapping `missing_evidence` to `ask_next_question` before any dispatch. He must not call Sapling from `system1/decide.py`.

Both model leaves are decided, so `orchestrate` calls Nemotron through `llm.complete` when `S2_IMPL=real` or `use_stubs=False`. `execute` always passes `use_stubs=True`, so the live call happens only when `S2_IMPL=real`. A missing Mubit URL or key raises `RuntimeError`. `execute` and the System 2 probe in `POST /replay` map that to HTTP 503 and put `str(exc)` in `detail`. The town note shows that body. A timeout, HTTP error (including 429, named in the reason as `HTTPStatusError 429 (rate limited)`), empty reply, or parse/enum failure becomes a safe `system2_unavailable` outcome and does not raise. That outcome is P1 when the case has `medical`, `oxygen_dependent` (cited `NIEMS-ANNOUNCEMENT-2554`), `need:rescue`, or `immobile` (cited `config/priorities.yaml` P1; the announcement assigns no colour to being trapped), and P2 otherwise. The P1 reason clause is `P1 for life-safety trigger X [cite]`. The outcome sets `needs=[]`, `route=supervisor_escalation`, and `escalate=false`. The model id is `nvidia/nemotron-3-nano-30b-a3b`, the paid tier, about $0.0003 a call at the OpenRouter list price of $0.06 per million input tokens and $0.24 per million output tokens. It replaced `nvidia/nemotron-3.5-lightning:free` after that account's 50-a-day free cap was spent. On 24 Oct 2026 nano matched the fixture priority and route on 3 of 6 prompts. C01-a came back P2 welfare where P1 rescue was expected. `_strings` turns a string or bool `needs`, `missing_evidence`, or `plan` into a list. `true` becomes `["unspecified"]`. `eval/rl/run.py` writes `model` into `run.json`, and `ui/sim/rl_panel.js` prints it. The page no longer loads that panel.

### 3.9 Context and resources

Producer: Moly `enrich.context.location_context` and `mocks.loader.load_dispatch_resources`. Consumer: `GET /context` and `GET /resources`. The town does not call either endpoint. `ui/sim/data/places.json` is a label file written from the same place snapshot.

`GET /context` query: optional `district`, `lat`, `lon`. The body is the `location_context` dict. Keys on every response include `matched_province` (str or null), `near_flood_extent` (bool), `distance_to_live_flood_m` (number or null), and `regional_reservoirs` (object or null). `regional_reservoirs`, when the matched row has a province in Lampang, Phrae, Nan, or Phayao, is `{date, scope, dams}`. `_match_district` tries `districts.json` first. Every row there stores `province` null, so a northern name never reaches the `admin_districts` row that has the province, and reservoirs stay empty. Hat Yai and Mueang Songkhla resolve on `admin_districts` with Songkhla Province. Rain stays null on that admin-only match. `ENRICH_IMPL` defaults to `data` when `districts.json` exists, which it does in the tree, so a local request reads `ingest/store.py`: `districts.json`, `admin_districts.json`, `weather_observation.json`, `flood.geojson`, `facilities.geojson`, and `source_status.json`. Open-Meteo is the rain fallback and the RID snapshot is the reservoir fallback. `disaster_report.json` is not read on this path. `"enrich": "off"` is added only when `ENRICH_IMPL=off`. The Modal gateway leaves that variable empty, so enrichment follows `store.available()` the same way a local serve does. `BAANSAFE_DB_PATH` overrides the gitignored ingest cache at `data/raw/ingest.sqlite`. It is not the runtime store, and the Modal app does not set it.

`GET /resources` returns `ResourcesSnapshot`: `boats`, `ambulances`, `shelters`, `welfare_points`. Each unit has `id`, `kind`, `name`, `district`, `capacity`, `available`, `status`. An OpenStreetMap unit has `capacity` null, `available` 1, and `id` `{kind}-{osm_type}-{osm_id}` (`shelter-way-679376537` is the shape). Hospitals map to `ambulance`, schools and temples to `shelter`, boat rentals and ferry terminals to `boat`. The handler subtracts `ledger.reserved_total` from `available`, floored at 0. `POST /cases/{id}/dispatches/confirm` and `/cancel` return the holds in this process, or HTTP 422 when there are none (open item 13).

`GET /metrics` counts trace stages. `mubit_chat` reports `call_count`, `ok_count`, `cache_hit_count`, `error_count`, `avg_latency_ms`, `models`, and `via` `api.mubit.ai`. `correction_count` is `len(read_corrections())`, the mock JSONL. A mubit-mode correction does not append that file, so the count does not move. The correction trace note is always `mock correction`, with `latency_ms` 0 (open item 35). The desk metrics strip reads that body. `GET /hosting` `note` starts `LLM via Mubit only`.

To match the block, Moly must put a `resource_id` from `mocks/resources.json` on a dispatch the sim is expected to draw. Melanie must not invent a unit id. Country packs do not change either endpoint.

## 4. Open items

PRs #2 through #18 are merged. There is no open pull request. #8 merged as `5cbd85f`. #9 merged as `f790191` (`c148bff`): `POST /session` returns `{caller_ip, simulated, note}` from `api/caller_ip.py`, and the same address is stamped onto `CaseState.resources` in `POST /cases` and `POST /cases/{id}/turns`. F17 and F18 location strings are Soi Sukhumvit 40 and Soi Sukhumvit 42, Khlong Tan Nuea, Watthana. Landmark prompts pin `bldg-0328` (temple, 0.66), `bldg-tower-pink` (Baan Chompoo Apartment, 0.64), and `bldg-0441` (Khlong Saen Saep, 0.58). The dashed route and the boat share one pace, at most 54 projected pixels a second and at least 3 seconds. #10 merged as `bbde2f0`: feature work branches and opens a pull request. #11 merged as `46101d8` (`2431e44`): the judge audit is in `HANDOVER.md`, and bare `unaccompanied` skips the implied `child` tag when a fact sentence says `adult`. #12 merged as `b6bfa0f` (`cb88fe4`): `data.demo_event` is `Sukhumvit / Watthana (Bangkok)`, and the Modal gateway sets `max_containers=1`. #13 merged as `3d1f362` (`51758cd`): `include_source=True` so the gateway container can import `gateway_app`. #14 merged as `4cedabd` (`5197bb4`): `HANDOVER.md` records a redeploy smoke and still asks whether paid System 2 stays on the public URL. #15 through #18 (`7342a66`) wire `memory/mubit.py`: the three memory leaves are decided, the Modal gateway sets `MEMORY_IMPL=mubit` when the secret is present, a `ws-` id is sent as `workspace_id`, and tests clear `MUBIT_PROJECT_ID`. Checked through `7342a66`. These conflicts are not leaves this note will set in `config/decisions.yaml`.

1. **Melanie owns the System 2 orchestrator.** `OWNERSHIP.md` gives `system2/` and `system2/orchestrator.py` to Melanie. Moly changed that file in `9da21c7`, `385c42a`, and `bb29476` (the nano model id and `_strings`). `bb29476` also changed `ui/sim/rl_panel.js`. Melanie should review the orchestrator and own it. On 24 Oct 2026 nano matched 3 of 6 fixture prompts. C01-a came back P2 welfare where P1 rescue was expected.
2. **A P1 outage fans out nothing and frees earlier boats.** `_unavailable` returns `needs=[]`, `route=supervisor_escalation`, and `escalate=false`. `merge` maps that route to `escalate_to_supervisor` before fan-out, so `dispatches` stays empty. `ledger.release_case` then keeps nothing and drops boats reserved on earlier turns of the same case. Fix, not chosen here: carry the System 1 handoff needs (`source_outcomes[1]`), or keep the holds when `missing_evidence` is `system2_unavailable`.
3. **A Watthana hit does not match a unit the town can draw.** Extract stores `Vadhana District, Bangkok Province`. Every fictional unit in `mocks/resources.json` is in Phrae (Wang Chin, Mueang Phrae, Den Chai) or Lampang (Mae Mo). `places.json` has no Bangkok district, so `unit.district.lower() in fields.location` fails and `merge` takes `units[0]`, an OpenStreetMap id. Fix, not chosen here: add fictional Vadhana units, or prefer fictional units when nothing matches.
4. **An agent set two leaves a human has not confirmed.** The files hold `system2.max_latency_ms` `10000` and `config/routing.yaml` `mode: cascade`. `scripts/validate.py` allowlists the decision value. They need a human confirmation. This note does not unset them. Moly chose `system2.orchestrator_model` `nvidia/nemotron-3-nano-30b-a3b` on 24 Oct 2026.
5. **RL graduation into System 1 contradicts the older rule.** `gateway/graduation.py` (`correction_loop.escalation_threshold`) still never moves a pattern into System 1. `eval/rl/learner.py` (`correction_loop.graduation_threshold`, live only with `RL_OVERLAY`) writes a System 1 rule for a repeated non-complex System 2 decision. `system1/decide.py` returns that rule as `fast_route`. Melanie needs to confirm this. The threshold keys stay 2. This note does not change them.
6. **`GET /rl/run` is 404 on Modal.** The handler reads `eval/out/rl/run.json`. `.dockerignore` excludes `eval/out`. `index.html` does not mount `rl_panel.js`, so the town desk does not show that 404. The file itself says it could not load `/rl/run`.
7. **Scripted households still post `fixture_id`.** Free-text and phone creates post a transcript, so extract sees the sentence. `useFixtureCreate` is true for a scripted play and a saved prompt, and those creates keep hand-filled fields. The page says the house pin is demo-only and that `gateway.route_chooser` is the field precheck.
8. **A replay cache miss is the System 2 fallback.** `eval/rl/run.py` keys `eval/out/rl/s2_cache.jsonl` by model and messages. A miss raises `ValueError("s2 cache miss")`. `orchestrate` catches that and returns `system2_unavailable`. Entries written for `nvidia/nemotron-3.5-lightning:free` still miss `nvidia/nemotron-3-nano-30b-a3b`. Live mode calls `llm.client.complete` and traces `mubit_chat`. A cache hit traces `status=cache_hit` and does not open a socket.
9. **The decided place matches the block, and most households do not.** `data.demo_event` is `Sukhumvit / Watthana (Bangkok)`. `scripts/validate.py` rejects any other string, including `Hat Yai / Songkhla`. The town draws Sukhumvit. Most fixture `location_label`s are still Lampang, Phrae, Nan, or Phayao, so enrichment does not match Watthana for those calls. F17 and F18 are the exceptions (`Soi Sukhumvit 40` and `Soi Sukhumvit 42`). `places.json` has no Watthana unit. Melanie reruns `ui/sim/build_town.py` from this main, decides whether to relabel the northern fixtures, and reviews PR #12's edits in `ui/sim/sim.js`, `ui/sim/build_town.py`, `ui/sim/README.md`, `ui/sim/data/streets.json`, `ui/sim/data/town.json`, and `ui/sim/data/responses.json`. Hat Yai still resolves on `admin_districts` with rain null when a call names it. It is not the desk flood.
10. **`promote_after` matches the threshold.** `ui/sim/data/sim_events.json` `learning.promote_after` is 2, the same number as `correction_loop.graduation_threshold` and `correction_loop.escalation_threshold`. The page copy escalates a repeat to System 2. It does not promote into System 1. The remaining split is the RL overlay (open item 5).
11. **The Modal gateway is pinned to one container in git.** `infra/modal/gateway_app.py` sets `max_containers=1`. Confirm, cancel, and `GET /resources` then share one in-process ledger. Other requests queue behind the one container. A live System 2 call can occupy it for up to 10 s. After `scaledown_window=120` seconds with no traffic the container exits and the ledger is empty, so a later confirm returns 422. `include_source` is `True` (`51758cd`, merged as `3d1f362`). `include_source=False` crash-looped: Modal could not import `gateway_app` (`ModuleNotFoundError`). `HANDOVER.md` at `4cedabd` says the hosted app was redeployed in the `3d1f362` era, with `/hosting` live and one System 2 turn that counted `mubit_chat`. This note did not call that URL and does not repeat it. The same secret sets `MEMORY_IMPL=mubit` (open item 34). Whether paid System 2 stays on is still open (open item 30). A local `make serve` is still one process, and a restart still drops the holds.
12. **`G01`–`G04` expect System 2.** `110e370` set `expected.system` to `system_2` with need `rescue`, matching the precheck. `mocks/s2_stub/G01.json` says the fixture expects System 2. `correction_loop.escalation_threshold` is 2.
13. **Accept confirms and Reject cancels, in this process.** System 2 and cascade dispatches still wait on the page. Accept posts `POST /cases/{id}/dispatches/confirm`. Reject posts `/cancel`. `merge` has already reserved stock. `GET /resources` subtracts those holds. A 422 means this process has no holds (open item 11). The landmark path can still set `path.accepted` false in the page after the ledger has reserved.
14. **The RL panel file is not on the page.** `index.html` does not load `rl_panel.js` and has no `#rl-panel`. The file labels live as `via Mubit`, replay as `S2 cache`, and fake as authored truth, and it can read `GET /metrics` `mubit_chat`. The desk shows that hop in `#gateway-hop` and a metrics strip. `61663d0` shows the same Mubit → Nemotron line on Correct this. Whether RL graduation into System 1 stands is still open (open item 5).
15. **The approval gate reads the router and the page scores.** `needsOperatorApproval` waits when `source_outcomes.length > 1`. It lets the call through only when `path.accepted === true` and `path.owner === "system_1"`. `path` comes from `sim_events.json` scores and `promote_after`, not from `source_outcomes[0].system`. A stub labelled System 2 can still dispatch immediately when that page path accepts.
16. **Evacuation has two routes.** `config/routes.yaml` maps `evacuation` to `rescue_coordination`. No runtime code reads that file. `system1/decide.py` `NEEDS_TABLE` maps `evacuation` to `shelter_placement`. The town prefers `RouterDecision.dispatches`. `rulebook.json` is a teaching overlay and marks a disagreeing row.
17. **A caller address on `CaseState.resources` can leave the case.** On main since `f790191`. `stamp_caller_ip` writes `caller_ip` and `caller_ip_simulated` on create and on each turn. `POST /session` returns the same triple and does not store it. The live Nemotron payload does not copy `case.resources`. Its `resources` key is unit counts from `load_resources()`. The turn response does return the case, and `gateway/route.py` already keeps `location_context` in that dict. The desk reads `location_context`. `memory.mubit.write` is still not called on the turn. When `MEMORY_IMPL=mubit`, retrieve sends location, needs, and the last transcript line to `/v2/control/query`, and a correction posts a lesson. Neither body copies `caller_ip`. A later `store_record` of the case, or a prompt that dumps `CaseState`, would carry the address. Fix, not chosen here: keep the address on `StoredCase` or in session-only storage. Melanie makes that change. Moly reviews it.
18. **F17 and F18 are Sukhumvit sois.** Main stores `Soi Sukhumvit 40, Khlong Tan Nuea, Watthana` and `Soi Sukhumvit 42, Khlong Tan Nuea, Watthana`. Needs stay `["aid_payment"]` and the route stays `aid_caseworker`. A one-click create posts `fixture_id`, so extract does not rewrite those fields. A free-text create does extract. `Watthana` maps to `Vadhana` only inside `system1/extract.py`. `places.json` has no Sukhumvit unit, so `unit.district.lower() in fields.location` does not match those two strings.
19. **The first `X-Forwarded-For` hop is trusted.** On main since `f790191`. `api/caller_ip.py` uses the first comma-separated value when it parses as a public address, and marks it not simulated. A client can spoof that header. Loopback and private addresses become the fixed stub `171.6.84.23` with `simulated` true.
20. **Feature work opens a pull request.** `bbde2f0` replaced “push straight to `main`” in `AGENTS.md`, `countries/AGENT_INSTRUCTIONS.md`, and `docs/agents/testing.md`. Branch off `main`, merge when `make test` and `make validate` are green, and delete the remote branch after merge. This PRD and the diagram refresh stay the docs-only exception and still push one commit to `main`. #11 through #14 are merged. There is no open pull request.
21. **`caller_ip` is not a dispatch resource.** On main since `f790191`. `stamp_caller_ip` writes `caller_ip` and `caller_ip_simulated` on `CaseState.resources`, next to `location_context`. `router/merge.py` does not read that dict. It fans out from `load_dispatch_resources()`. The page reads `location_context` and must ignore the two caller-ip keys. It must not draw them as a boat, ambulance, shelter, or welfare point.
22. **The adult exception looks at every fact sentence.** `2431e44` skips the implied `child` tag when any fact sentence contains `adult` or `adults`. "An unaccompanied adult is at the shelter" sets neither `child` nor `safeguarding`. "She is unaccompanied. The adults are on the roof." also sets neither, because `adults` is in the second sentence. The same-sentence rule would keep the implied child on the first sentence. "The child is unaccompanied. The adults are on the roof." still returns `child` and `safeguarding`, because the word `child` matches on its own. "My grandmother is unaccompanied at the shelter" and "She uses a wheelchair and is unaccompanied" still return `child` plus `safeguarding`. `elderly` and `immobile` do not suppress the implied tag. That flag still sends the case to System 2, and `_post_rules` forces `requires_human`. Fix, not chosen here: apply the adult check only in the same sentence as `unaccompanied`.
23. **#9 merged before the desk wiring.** `f790191` landed the session and landmark files. `f65ab55` then posted transcripts and read dispatches and `location_context`. Melanie pulls `main` before she edits `ui/sim` (open item 26).
24. **Thai calls get no System 1 needs.** `4913304` reverted the Thai need, danger, and vulnerability phrases. District names still match Thai. A Thai sentence no longer sets `shelter`, `evacuation`, or `rescue` from those lists, so the precheck sees empty needs more often and sends the call to System 2. The substring overlap from `0bd3340` (`ศูนย์อพยพ`, bare `ติดอยู่`, bare `ที่พัก`) is gone with that revert. English `children`, `kids`, and bare `unaccompanied` stay (open item 22).
25. **Northern reservoirs never fire.** Every row in `districts.json` has `province` null, and `_match_district` tries that table first. A Lampang, Phrae, Nan, or Phayao name therefore never reaches the `admin_districts` row that has the province set, and `_regional_reservoirs` returns null. Hat Yai still resolves, with rain null, when a call names it. `data.demo_event` is `Sukhumvit / Watthana (Bangkok)` (open item 9).
26. **Melanie reviews the town from this main.** Earlier edits through `61663d0` added 578 lines to `ui/sim/sim.js` and also changed `rl_panel.js`, `index.html`, `sim_events.json`, and `ui/correct.js`. PR #12 (`b6bfa0f`) then edited `ui/sim/sim.js`, `ui/sim/build_town.py`, `ui/sim/README.md`, `ui/sim/data/streets.json`, `ui/sim/data/town.json`, and `ui/sim/data/responses.json` so the framing says `Sukhumvit / Watthana (Bangkok)`. Melanie pulls `main`, reruns `ui/sim/build_town.py`, and decides whether to relabel the northern fixture `location_label`s (open item 9).
27. **`TraceEvent.stage` grew without a contract tag.** `contracts/models.py` allows `enrich`, `memory`, and `mubit_chat`. `contracts/CONTRACTS.md` names them. `contracts/schemas/TraceEvent.json` does not. The tag is still `v0.3-contracts` from CR-003. There is no open change request. The memory adapter and any reader that trusts the JSON schema must accept the three stages. `gateway/route.py` emits `enrich` and `memory` on every turn. `llm.complete` emits `mubit_chat`.
28. **Every System 2 completer must take `case_id`.** `system2/orchestrator.py` calls the completer with `case_id=case.case_id`. The RL live and replay completers accept `**kwargs`. A completer that rejects that keyword raises `TypeError`, which `_unavailable` turns into `system2_unavailable`. Melanie's replacement completer should accept `**kwargs`.
29. **Hosted System 2 spends Nemotron credit when the secret exists.** `infra/modal/gateway_app.py` attaches `baansafe-mubit` and `apply_runtime_impl` sets `S2_IMPL=real` and `MEMORY_IMPL=mubit` when both `MUBIT_API_KEY` and `MUBIT_BASE_URL` are non-empty. That is a paid call to `nvidia/nemotron-3-nano-30b-a3b` and can return 429, which becomes `system2_unavailable` rather than HTTP 503. Moly and Melanie need to agree before that secret stays on the public app. `GET /hosting` says `LLM via Mubit only`.
30. **`HANDOVER.md` records the smoke, live memory, and the remaining choices.** #11 put the judge audit on main. #14 (`5197bb4`) rewrote the handover. The copy on this tip also names control-plane retrieve when the secret exists (open item 34). It quotes `make test` as 272 passed and 1 skipped (`tests/test_synthetic_calls.py` needs the `laya` module). It says the hosted app was redeployed, `/hosting` was live, and one System 2 turn counted `mubit_chat`. It asks both owners whether paid System 2 stays on that URL, asks Melanie to pull and review `ui/sim`, and says to freeze `ui/sim` until that review. This note does not edit `HANDOVER.md` and did not call the URL.
31. **#11 through #18 are on main.** #11 merged the judge audit and the unaccompanied-adult extract check (open item 22). #12 merged the Sukhumvit decision and `max_containers=1` (open items 9 and 11). #13 merged `include_source=True` so the gateway container can import `gateway_app` (open item 11). #14 rewrote `HANDOVER.md` (open item 30). #15 through #18 wire live Mubit memory (open item 34). Aid endpoints are still 501. `index.html` still does not load `rl_panel.js`. There is no open pull request.
32. **Correct this labels a stub System 2 hop as Mubit.** `ui/correct.js` reads only `source_outcomes[0]`. When that outcome's `system` is `system_2`, the form says `Mubit → Nemotron` and does not look at the trace. A stub System 2 outcome gets the same line as a live hop. `ui/sim/sim.js` `mubitHopSummary` does look at `mubit_chat` and says the hop is a stub until credentials make System 2 real. On a cascade, `[0]` is System 2, so the form shows the line for the deciding outcome. Melanie keeps `Outcome.system` as `system_2` on that outcome.
33. **Two merged branches are still on the remote.** `origin/cursor/town-session-landmarks-1370` (PR #9) and `origin/cursor/s2-approval-gate-1370` (PR #8) are still there after merge. `AGENTS.md` says to delete the remote branch after merge.
34. **Live memory is the control plane, and the local default is still mock.** `ecf8358` through `d0d13e5` (merged as `7342a66`) set `memory.mubit_project` to `baansafe-demo`, `memory.retrieval_top_k` to 5, and `memory.token_budget` to 400. `memory/mubit.py` posts `/v2/control/query` and `/v2/control/ingest` on the Mubit host root. `MUBIT_PROJECT_ID` overrides the leaf: `proj-` is `project_id`, `ws-` is `workspace_id` and `project_id`, and any other value is `run_id` only. Moly wrote that client in `memory/`, which `OWNERSHIP.md` gives to Melanie. She reviews PRs #15 through #18. `gateway/route.py` retrieves on every turn and emits stage `memory` with `latency_ms` and `mode=`. The adapter returns `[]` when the query fails. The Modal gateway sets `MEMORY_IMPL=mubit` only when both Mubit credentials are present. `store_record` is still not called, so a finished case is not ingested. A correction in mubit mode posts a lesson and does not also append the mock JSONL. Tests delete `MUBIT_PROJECT_ID`. This note does not call the hosted URL.
35. **A failed memory ingest drops the correction before the training log.** `store_correction` does not catch an ingest error. `POST /cases/{id}/corrections` catches only `NotImplementedError`. `RuntimeError` from `/v2/control/ingest` is HTTP 500. `append_event` sits after `store_correction`, so it does not run, and `gateway/graduation.py` never sees that correction because it counts the local training log, not Mubit. On a successful mubit correction the log does append, the trace note is still `mock correction` with `latency_ms` 0, and `GET /metrics` `correction_count` still reads the mock JSONL, which mubit mode does not write.
36. **The memory query can outlast the System 2 budget, and an empty project looks like no memory.** `memory/mubit.py` uses an httpx timeout of 20 seconds. `system2.max_latency_ms` is 10000. Retrieve runs inside `handle` before the chooser, so a slow query holds the turn, and the one Modal container, for up to 20 seconds before System 2 starts. A query against an empty `baansafe-demo` project returns no evidence, and the adapter's `[]` on a failed query looks the same. `HANDOVER.md` already says a console `proj-` id is optional when that project is empty.

## 5. Decide before 19:00 integration

`OWNERSHIP.md` names the integration as `S1_IMPL=real`, `S2_IMPL=real`, and `MEMORY_IMPL=mubit` together. Contracts stay frozen at `v0.3-contracts` until then. This list does not pick the remaining choice.

- Whether a scripted household should also post a transcript. Free-text and phone already do. One-click households still post `fixture_id` (open item 7).
- Whether to relabel northern fixture households now that `data.demo_event` is `Sukhumvit / Watthana (Bangkok)`. The block already matches that string. Most `location_label`s are still Lampang, Phrae, Nan, and Phayao. F17 and F18 are Sukhumvit sois (open item 9). This note does not relabel them.
- Whether RL graduation into a System 1 rule stands (open item 5). Melanie confirms. The threshold numbers stay 2. `promote_after` is 2 and the page does not promote into System 1 (open item 10).
- Whether `max_latency_ms` 10000 and cascade mode stand (open item 4). Moly set `system2.orchestrator_model` to `nvidia/nemotron-3-nano-30b-a3b` on 24 Oct 2026. The files keep these values.
- Whether the public Modal app should keep `baansafe-mubit` and promote System 2 (open item 29). That spends paid Nemotron calls. `HANDOVER.md` records a smoke with System 2 left on and still asks both owners to confirm that spend (open item 30).
- The town showing `dispatches` and `location_context` is on main (`f65ab55`). Melanie pulls before editing `ui/sim` (open item 26). Feature edits go through a pull request (open item 20).
- How to describe Mubit. The three memory keys are decided. A local `make serve` still uses mock files. The hosted gateway uses the control plane when the secret is present: gateway, traces, and live retrieve. A query error returns no items, and the turn still does not write a `MemoryRecord` (open item 34). Melanie reviews that client (open item 34). A failed correction ingest is HTTP 500 and does not graduate (open item 35).

## 6. Open decisions

These leaves are `TODO_HUMAN` in `config/decisions.yaml`. Decided leaves, not in that table: `system1.extraction_method` `rules-only`, `gateway.route_chooser` `field precheck`, `system2.hosting` `openrouter via mubit gateway`, `system2.use_banyan_sapling` true, `system2.sapling_scope` `aid_eligibility,denial`, `sapling.client` `stub`, `llm.provider_route` `mubit`, `correction_loop.graduation_threshold` `2`, `correction_loop.escalation_threshold` `2`, `data.demo_event` `Sukhumvit / Watthana (Bangkok)`, `memory.mubit_project` `baansafe-demo`, `memory.retrieval_top_k` `5`, `memory.token_budget` `400`. Set in the files and allowlisted, but waiting on a person (open item 4): `system2.orchestrator_model` `nvidia/nemotron-3-nano-30b-a3b`, `system2.max_latency_ms` `10000`, and `config/routing.yaml` `mode: cascade`. This note does not unset them.

| Key | Who is blocked |
|---|---|
| `system1.extraction_model` | Nobody on the rules path. A model extractor is blocked. Moly owns that choice. |
| `sapling.hosting`, `sapling.gpu`, `sapling.model_id`, `sapling.thai_handling` | Melanie, only for `SAPLING_IMPL=live`. The stub client does not read them. |
| `gateway.auth` | Moly, for a scheme that can reject a request. Calls are not blocked. |
| `llm.token_price_usd` | Melanie's cost column. `eval/compare.py` leaves `cost_usd` null. Calls are not blocked. |
| `speech_to_text.provider` | The phone demo. A clip with no browser transcript is not sent. |
| `ui.framework` | Nobody for the static town page. A framework choice is blocked. |
| `data.production_db` | A production database. Committed JSON in `data/processed` is the overnight store. SQLite is the gitignored ingest cache. |
| `learning_eval.promotion`, `learning_eval.freeze_mubit_auto_adapters` | Melanie. Eval records the unset value and does not promote. Setting either key without an implementation makes the gate raise. |
| `latte_bench.license_confirmation` | Melanie. Use beyond the reference checkout stays blocked. |
| `sim.caller_model`, `sim.caller_gpu` | Melanie's model caller. The scripted simulator still runs. |
| `policies.authoritative_set` | Melanie. Sapling will not treat the corpus as the binding policy set. Rules still load by id. |
| `modal.s1_gpu`, `modal.s1_model_id`, `modal.s2_gpu`, `modal.s2_model_id`, `modal.nemotron_size`, `modal.s2_quant`, `modal.finetune_gpu`, `modal.finetune_base_model`, `modal.stt_gpu`, `modal.stt_model_id` | Whoever deploys that app. The apps refuse `TODO_HUMAN`. The API process does not need them. |

## 7. Changelog

- 2026-10-24 — Cascade routing replaces the exclusive-turn invariant: `routing.yaml` `mode: cascade`, an S1 escalate hands off to S2 in the same turn (never the no-stub fallback), `source_outcomes` = [deciding, *prior]. System 2 is live Nemotron (`nvidia/nemotron-3.5-lightning:free`, 10000 ms); `correction_loop.graduation_threshold` is 2 and the RL loop (`eval/rl/`, `GET /rl/run`) graduates, recommends, and demotes learned patterns.

- 2026-10-24 `1e4ca79` — First PRD. Field precheck, System 1 rules, and `router.merge` are live on the default turn only as described above. System 2, the Sapling client, and Mubit memory remain stubs.
- 2026-10-24 `11e0859` — Extractor covers water at or inside the door, immobility, a child alone, aid refusals, and minimising. Aid and minimising matches are not dropped for a negator. `F15` still hides the child in an operator turn.
- 2026-10-24 `52d3123` — Open items for the stale phone chooser, `G01`–`G04`, the `4f9e631` overlap with Melanie's sim and `F08`, and the simulated feed. Must-provide lines for CR-003, one System 2 `Outcome`, stable flags, English extract, and the two System 2 TODOs. Diagrams unchanged.
- 2026-10-24 `26b74a1` — District gazetteer, caller-confirmed facts, G stubs, in-process stock holds, and graduation to System 2 (`complex_situation`, threshold 2). CR-003 is `v0.3-contracts`. Open items for the town's promote-after story, the `town.json` rebuild, and the ledger across containers.
- 2026-10-24 `ae01643` — `flood.yaml` joins the loaded corpus. Depth figures are not a 1669 colour and do not change the chooser or System 1. Country packs under `countries/` stay unloaded. #6 and #7 are 10 commits behind this SHA. The call diagram is still the `26b74a1` path.
- 2026-10-24 `7c506d7` — Public snapshots, `near_flood_extent`, `GET /context` fields, Thai district names, and OpenStreetMap units on `GET /resources`. 240 synthetic calls and the Laya export. Country packs stay unloaded. #6 at `31078af` conflicts with main. The call diagram was already updated in `9489cf3` and is not redrawn here.
- 2026-10-24 `edd64d0` — #6 and #7 are on main. Cascade, live Nemotron when `S2_IMPL=real`, RL graduation into System 1, and `source_outcomes` as `[final, *prior]`. The Sukhumvit block does not match the northern place snapshot. The call diagram already shows the cascade. This note only corrects the caption that still called the model id unset.
- 2026-10-24 `385c42a` — A System 2 outage is P1 on a life-safety trigger and P2 otherwise, with `needs=[]` and `supervisor_escalation`, so `merge` fans out nothing and `release_case` frees earlier holds. Extract stores `Watthana` as `Vadhana District, Bangkok Province`, which matches no mock district. The free Nemotron id, `max_latency_ms` 10000, and cascade mode are in the files and still need a person. Answered houses use `final_priority` (P1 `#ff3b30`, P2 `#ff9f1a`, P3 `#3ddc84`, P4 `#c084fc`) except the active caller and the destination. PRs #2 through #7 are merged. Diagrams unchanged. Checked through `bdb068e`.
- 2026-10-24 `df03243` — `MUBIT_BASE_URL` is required next to `MUBIT_API_KEY` and is synced into `baansafe-mubit`. Tests pin the URL and drop the key. PR #8 (`f8b6acd`) is open, not on main: the page holds System 2 and cascade dispatches until Accept or Reject, and main still has no confirm endpoint. `VULNERABLE_PHRASES` still misses `kids` and `children`. Diagrams unchanged.
- 2026-10-24 `5cbd85f` — System 2 is `nvidia/nemotron-3-nano-30b-a3b`. Scalar reply lists become lists, and `true` becomes `["unspecified"]`. The RL cache key includes the model, so replay misses the lightning entries. #8 is merged: the page holds System 2 and cascade vehicles until Accept or Reject, and there is still no dispatch endpoint. `routes.yaml` is not what System 1 runs. The call diagram is unchanged; the caption notes the page gate. Checked through `5cbd85f`.
- 2026-10-24 `0967f21` — The README diagram is the numbered turn (caller, gateway, System 1, System 2, router, operator review, learning loops) and the model for later refreshes. The request map in `BaanSafe_Revised_Architecture.md` is unchanged. #8 stays merged. #9 at `c148bff` is open: a session stamp, Sukhumvit locations for F17 and F18, three landmark pins, and a shared route pace. It is not drawn. The caller address sits on `CaseState.resources`, those soi strings leave the gazetteer form, the first `X-Forwarded-For` hop is trusted, and the approval gate is still only in the page.
- 2026-10-24 `fa8a4ca` — Runtime data is committed JSON and GeoJSON in `data/processed`, read by `ingest/store.py`. `baansafe.sqlite` is gone. SQLite remains the gitignored ingest cache, and `BAANSAFE_DB_PATH` is not set on the Modal gateway. Enrichment is on locally because `districts.json` exists, and off on that Modal app. The 50 district rows still have `province` null. The README diagram keeps its numbered layout and names those files.
- 2026-10-24 `172ebd7` — #9 at `c148bff` is still open, MERGEABLE, and 6 commits behind. Its `endpoints.py` hunks do not overlap the health-store change. It needs a retest of `test_caller_ip`, `test_town_sim`, `test_store`, and `test_modal_infra`. `caller_ip` on `CaseState.resources` is not a dispatch resource. `contracts/` did not change. Memory, System 2, and aid do not read SQLite. `data.production_db` stays `TODO_HUMAN`. The JSON ships in the Modal image.
- 2026-10-24 `0fdc34e` — `VULNERABLE_PHRASES` tags `child` for `kids`, `children`, `grandchild`, and `grandchildren`. Bare `unaccompanied` adds `child` and the safeguarding flag. Extract on the six synthetic transcripts that HANDOVER had called unsafe now returns that flag. `F15` stays the unconfirmed operator turn. Diagrams unchanged.
- 2026-10-24 `4813a29` — `children`, `kids`, `babies`, `grandchild`, and `grandchildren` set `child`, and with an alone-phrase they set `safeguarding`. Bare `unaccompanied` sets both. `not unaccompanied` sets neither. An unaccompanied elderly or immobile adult is also tagged `child`. #9 is 9 commits behind and still shares `endpoints.py` with the JSON store change. Town `F17` and `F18` do not use the new phrases. Diagrams unchanged.
- 2026-10-24 `0bd3340` — Thai need phrases, negator prefixes, and `มี N คน` are in `system1/extract.py`. The commit measures Thai synthetic needs at 76 of 80, up from 0 of 80. Enrichment tries `districts` then `admin_districts`: Hat Yai and Mueang Songkhla resolve, rain stays null, and northern reservoirs stay empty because `province` is null on the first table. Laya is export-only. `make modal-finetune` is SetFit and LoRA. `docs/wire-frontend.md` plans dispatch and transcript wiring and is not live. #9 is 11 commits behind, MERGEABLE, and shares `sim.js`, `sim_events.json`, and `index.html` with that plan. `data.demo_event` stays `TODO_HUMAN`. The extract and enrich labels were updated in place.
- 2026-10-24 `61663d0` — #9 is merged. Thai need phrases are reverted, so extract is English-only again and Thai calls escalate more often. Confirm and cancel are live, and `GET /resources` subtracts holds. `data.demo_event` is `Hat Yai / Songkhla`. `G01`–`G04` expect System 2. The Modal gateway runs real System 1 and auto enrichment, and promotes System 2 when `baansafe-mubit` is present. The town posts transcripts, reads dispatches and `location_context`, and shows `GET /metrics`. `promote_after` is 2. `TraceEvent` gained `enrich`, `memory`, and `mubit_chat` with no contract tag. `GET /rl/run` is still 404 on Modal. Checked through `61663d0`, which includes `e1fc17d`. Diagram labels updated in place.
- 2026-10-25 `bbde2f0` — Feature work branches and opens a pull request. This note stays the docs-only push to `main`. `5108994` rewrote `HANDOVER.md` and struck the old gap 11. Correct this shows `Mubit → Nemotron` from `source_outcomes[0]` even on a stub System 2 hop. PR #11 at `5cf24bb` is open: a judge-audit handover, a proposed learning-story freeze, and an unaccompanied-adult extract check that looks at every sentence. Merged branches `cursor/town-session-landmarks-1370` and `cursor/s2-approval-gate-1370` are still on the remote. Diagrams unchanged.
- 2026-10-25 `4cedabd` — #11 is merged: the judge audit is in `HANDOVER.md`, and bare `unaccompanied` skips implied `child` when any fact sentence says `adult`. #12 is merged: `data.demo_event` is `Sukhumvit / Watthana (Bangkok)` and `make validate` rejects `Hat Yai / Songkhla`. The Modal gateway sets `max_containers=1` (`scaledown_window=120`). #13 sets `include_source=True` after `include_source=False` crash-looped on `ModuleNotFoundError` for `gateway_app`. #14 says the hosted app was redeployed and a smoke saw `/hosting` live plus one System 2 `mubit_chat`. Most fixture labels stay northern, so enrichment still misses Watthana except F17 and F18. There is no open pull request. The turn path is unchanged, so the diagrams are not redrawn. Checked through `4cedabd`, which includes `b6bfa0f`.
- 2026-10-25 `7342a66` — #15 through #18 wire Mubit control-plane memory. `memory.mubit_project` is `baansafe-demo`, `retrieval_top_k` is 5, and `token_budget` is 400. `MEMORY_IMPL=mock` stays the local default. The Modal gateway sets `MEMORY_IMPL=mubit` when `baansafe-mubit` is present. Retrieve posts `/v2/control/query` and a failure returns no items. A correction posts `/v2/control/ingest`. `MUBIT_PROJECT_ID` overrides the project, and a `ws-` id is sent as `workspace_id`. Tests clear that variable. The turn still does not call `store_record`. Diagram labels updated in place.
- 2026-10-25 `7342a66` follow-up — A failed correction ingest is HTTP 500, skips `append_event`, and so cannot graduate. The memory query timeout is 20 seconds against a 10 second System 2 budget. The correction trace note stays `mock`, and `correction_count` reads the mock file. An empty `baansafe-demo` project returns no items. `MemoryItem` kinds stay the four contract values, mapped from `lesson`, `rule`, and `fact`. Graduation counts the local training log. Moly wrote the client; Melanie reviews #15 through #18. `docs/agents/gateway-and-llm-client.md` and `HANDOVER.md` now say the hosted gateway sets `MEMORY_IMPL=mubit` when the secret is present. Diagrams unchanged.
