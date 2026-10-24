# BaanSafe PRD

Shared product and interface note for Moly and Melanie. Every claim below is what the code on `main` does. This file does not set a value in `config/decisions.yaml`. Owners in the status table are from `OWNERSHIP.md`. Callers are synthetic: `caller_id_hash` values look like `synthetic:f02`, and `scripts/validate.py` rejects phones, 13-digit ids, PromptPay, passport, immigration status, and bank account.

## 1. Product

BaanSafe is a flood call-triage scaffold for a synthetic Thai flood. A call is triaged, a provisional dispatch can be named, and aid casework is a separate check that does not approve a payment. Mubit governs memory, policy, and traceability and does not reason. The field precheck picks one entry point; `config/routing.yaml` `mode: cascade` lets a System 1 escalate continue to System 2 in the same turn (the no-stub fallback outcome never cascades). Every LLM call goes through `llm/client.py` or `llm/openai_client.py`. Both refuse a host that is not `api.mubit.ai` or a `mubit.ai` subdomain. `llm.provider_route` is `mubit`. The OpenAI SDK base is the Mubit compat prefix (`/compat/openrouter/v1`). There is no OpenRouter client.

Demo story, as the town page runs it (`ui/sim/`, `make serve`, `http://127.0.0.1:8000/ui/sim/`):

- The picture is a local-metre Sukhumvit block in Watthana. `data.demo_event` is still `TODO_HUMAN`. Hazard labels say Sukhumvit, Watthana. Fixture households keep their district labels (Lampang, Phrae, Nan, Phayao). `places.json` and `data/snapshots/places.json` cover those four provinces. The snapshot has no Sukhumvit or Watthana unit.
- The phone sends a line by matching it to one of 20 fixture ids (`ui/sim/data/town.json` `calls`, same order as `fixtures/index.json`), then `POST /cases` with that `fixture_id` and `POST /cases/{id}/turns` with the typed or spoken text.
- The gateway returns a `RouterDecision`. `final_priority` lights the house (P1 red, P2 amber, P3 yellow, P4 blue). The phone speaks a scripted line from `ui/sim/data/replies.json`, not a live operator.
- The right-hand feed plays `ui/sim/data/sim_events.json`. Every card is badged simulated. `confidence_threshold` is 0.8, the same number as `system_1_min_confidence`. The accept/reject story is still the page's scores, not `source_outcomes[0].system`.
- Reject opens Correct this (`ui/correct.js`) and posts `POST /cases/{id}/corrections`.
- Speech uses the browser Web Speech API, else `POST /stt/transcribe`. This API does not mount `infra/modal/stt_app`. If neither returns words, the phone shows a stub transcript and sends nothing.

Scope that is in the tree tonight:

- Gateway: keyword-extract when fields are empty, enrich, mock memory, human-correction graduation (`complex_situation`), field precheck, then one system or a cascade into System 2, `router.merge`. `router/ledger.py` reserves stock in this process only. `GET /resources` lists OpenStreetMap places ahead of the fictional units.
- `fixtures/synthetic` has 240 calls. `make export-laya` writes Laya JSONL. `make laya-train` skips unless `LAYA_TRAIN=1` and a GPU or a Modal task is present. Country packs under `countries/` are not imported.
- System 1 rules (`system1/extract.py`, `system1/decide.py`) when `S1_IMPL=real` or `use_stubs=False`. The API default is `use_stubs=True`, so a normal `/turns` call still uses the stub outcome file. A stub that escalates still cascades to the System 2 stub.
- System 2 calls Nemotron through Mubit only when `S2_IMPL=real` (`system2.orchestrator_model` is `nvidia/nemotron-3.5-lightning:free`, `system2.max_latency_ms` 10000). The default API and `infra/modal/gateway_app.py` set `S2_IMPL=stub`, so they do not call it. A missing `MUBIT_BASE_URL` or `MUBIT_API_KEY` on a real call is HTTP 503. A 429 becomes a `system2_unavailable` outcome, not a 503. Sapling's live client, aid eligibility, aid exceptions, and the Mubit memory client still raise or return HTTP 501.
- Integration named in `OWNERSHIP.md`: `S1_IMPL=real`, `S2_IMPL=real`, and `MEMORY_IMPL=mubit` together. Contracts stay frozen at `v0.3-contracts` until then. CR-003 (`Dispatch`, `RouterDecision.dispatches`) is tagged `v0.3-contracts`.

`frontend-prototype/` is not part of this product surface.

## 2. Status

| Component | Owner | State | Files |
|---|---|---|---|
| Gateway turn | Moly | live | `gateway/route.py` `handle` |
| Field precheck | Moly | live. Decided value `field precheck` | `gateway/chooser.py`, `config/escalation.yaml` |
| Keyword extract | Moly | live. English phrase and regex families, plus caller-confirmed operator facts. District names match Thai and English. A matched district is `District, Province`. An ambiguous name gets confidence 0.6, which the precheck sends to System 2. Skipped when the case already has fields and `keyword_extraction` is absent | `system1/extract.py`, `data/snapshots/gazetteer.json` |
| System 1 decide | Moly | live rules. Default request uses the stub file instead | `system1/decide.py`, `mocks/s1_stub/` |
| Aid eligibility | Melanie | stub. `check` raises. `GET /aid/eligibility` is 501 | `system1/aid_eligibility.py` |
| Router merge | Moly | live. Always called from `handle`. Provisional dispatches reserve stock in this process. With no district match, the first usable unit wins, and OpenStreetMap units are listed first | `router/merge.py`, `router/ledger.py`, `mocks/loader.py` |
| Auth | Moly | TODO_HUMAN. A note is recorded. The request is not rejected | `gateway/auth.py` |
| Enrichment | shared | live when SQLite exists, else off. `GET /context` always returns `matched_province`, `near_flood_extent`, `distance_to_live_flood_m`, and `regional_reservoirs`. Those flags do not change priority | `enrich/context.py`, `gateway/route.py`, `api/routes/endpoints.py` |
| Policy pre-check | Moly | live notes only. Does not change priority | `gateway/policy.py` |
| Memory mock | Melanie | live for fixture ids | `memory/adapter.py`, `mocks/memory_context/` |
| Mubit memory client | Melanie | stub. Raises. Three keys are TODO_HUMAN | `memory/mubit.py` |
| Graduation (escalation) | Moly | live. `correction_loop.escalation_threshold` is 2. A matching pattern is tagged `complex_situation` and gets a `graduated-*` correction `MemoryItem`. It sets no priority and does not move the pattern into System 1 | `gateway/graduation.py`, `eval/graduation_demo.py` |
| RL loop | Moly | offline. `correction_loop.graduation_threshold` is 2: graduate (System 2 → System 1 rule), recommend (P1/complex), demote (System 1 under-triage). Live only with `RL_OVERLAY` | `eval/rl/`, `gateway/overlay.py` |
| System 2 / Nemotron | Melanie. Moly edited these files in `9da21c7` | live only when `S2_IMPL=real`. Default API and the Modal app stay `stub`. Signature is `decide(case, handoff, recommendation)` | `system2/decide.py`, `system2/orchestrator.py` |
| Sapling | Melanie | gate is written. Client is `stub`. Runs after a real System 2 outcome on aid checks | `system2/sapling.py`, `system2/sapling_client.py` |
| Aid exceptions | Melanie | stub. `POST /aid/exceptions` is 501 | `system2/aid_exceptions.py` |
| LLM clients | Melanie wires the call | host check is live. Called by `orchestrate` on System 2 turns | `llm/client.py`, `llm/openai_client.py` |
| Policy corpus | Melanie | live `GET/POST /policies`. `flood.yaml` is in the loaded corpus. Packs under `countries/` are not imported. `policies.authoritative_set` is TODO_HUMAN | `policies/service.py`, `policies/corpus.py`, `api/routes/policies.py` |
| Town phone and feed | `OWNERSHIP.md` lists `ui/` as Moly. The phone, feed, and rulebook are what the demo consumes | live page. Feed and vehicle picture are simulated | `ui/sim/sim.js`, `ui/sim/data/` |
| Correct this | Moly | live post of a v1 correction | `ui/correct.js`, `ui/player.html` |
| Training log and export | shared log, Melanie eval | live append and export. `fixtures/synthetic` also exports SetFit rows and Laya JSONL. `laya-train` skips without `LAYA_TRAIN=1`. The Modal fine-tune still refuses a TODO_HUMAN base model and does not read the synthetic rows | `training/log.py`, `training/export.py`, `training/synthetic_export.py`, `training/laya_export.py`, `scripts/laya_train.py` |
| Held-out eval | Melanie | stub scoreboard. Does not load weights. Promotion stays false | `eval/learning/` |
| Extract eval | Moly rules, shared fixtures | live comparison of extract vs hand-filled fields. Writes `eval/out/extract.md` | `eval/extract_eval.py` |
| Caller sim | Melanie | scripted path is live. Model backend is TODO_HUMAN | `sim/env.py`, `sim/coach.py` |
| Modal gateway | shared | stub town and API as one ASGI app. `S2_IMPL=stub`. Volume `baansafe-demo` at `/data` for traces, training events, policy pins, and SQLite | `infra/modal/gateway_app.py`, `policies/service.py`, `ingest/db.py` |
| Speech to text | shared | TODO_HUMAN. Not mounted on this API | `infra/modal/stt_app.py` |

## 3. Shared context

Models are Pydantic v2 with `extra=forbid`. JSON Schema copies are `contracts/schemas/*.json`. Required fields below are the schema `required` arrays.

### Must provide

- To match CR-003, Moly provides `Dispatch` and `RouterDecision.dispatches`. The tag is `v0.3-contracts`. Contracts stay frozen there until the 19:00 integration. Melanie's town must show the router's reserved `resource_id` rather than picking its own unit. The drawn units are the ids in `mocks/resources.json` (`boat-fictional-01`, `amb-fictional-01`, `shelter-fictional-01`, `welfare-fictional-01`). `ui/sim/sim.js` still does not read `dispatches`.
- To match `GET /context`, Moly returns `matched_province`, `near_flood_extent`, `distance_to_live_flood_m`, and `regional_reservoirs` on every response. While enrichment is off those values stay null or false, plus `"enrich": "off"`.
- To match `GET /resources`, the body keeps `boats`, `ambulances`, `shelters`, and `welfare_points`. Boats, ambulances, and shelters now include OpenStreetMap units with `id` `{kind}-{osm_type}-{osm_id}` and `capacity` null, listed before the fictional units. Welfare points stay the fictional file.
- `near_flood_extent` is a data flag only. It is not in `route_to_system_2_if_any`, and it never changes priority.
- System 1 matches Thai district names as well as English. A Thai hit uses the gazetteer snapshot, and SQLite `name_th` when that database exists. Phrase families for needs, danger, and vulnerability stay English.
- Country packs under `countries/` are documents only. Nothing there is imported. Thailand stays the demo.
- To match human-correction graduation, System 2 treats the `complex_situation` flag and the `graduated-*` correction `MemoryItem` as recommendations only. That path reads `TRAINING_EVENTS_PATH` (`/data/events.jsonl` on Modal) and caches by path, mtime, size, threshold, and labels. It sets no priority and does not move a pattern into System 1. The RL loop is the other meaning of graduation: `correction_loop.graduation_threshold` can write a System 1 rule when `RL_OVERLAY` is set (open item 2).
- To match a cascade, consumers read `source_outcomes[0]` as the final outcome. On a cascade, `[1]` is the System 1 handoff. `merge` builds `[final, *prior]`.
- To match System 2, the signature is `system2.decide(case, handoff, recommendation)`. `handoff` is the escalating System 1 outcome. `recommendation` is the overlay entry for that narrow signature, or null. A Sapling `violation` must surface as `requires_human`, as the `route`, or as `missing_evidence`. `merge` does not read a `sapling_verdict` string.
- The town shows a failed turn as a phone note: "The gateway did not answer." plus the status and the JSON body. A missing Mubit URL or key is HTTP 503, and that `detail` is inside the note. A Nemotron 429 does not take this path. It becomes a `system2_unavailable` outcome.
- To match the chooser, both sides must keep the flag strings `safeguarding`, `conflicting_evidence`, `aid_exception`, and `complex_situation`, and the `ExtractedFields` names (`location`, `location_confidence`, `people_count`, `vulnerable`, `medical`, `danger`, `needs`), stable.
- To match extract, Moly keeps the phrase families English-only and matches district names in Thai and English. Caller turns count, plus an operator question the caller confirms with yes, yeah, correct, or that's right. Those confirmed facts count for `vulnerable`, `people_count`, and `danger` only. `F15` is still misrouted: the child is only in an operator turn, and the caller does not confirm it.
- `system2.orchestrator_model` is `nvidia/nemotron-3.5-lightning:free` and `system2.max_latency_ms` is 10000, so `orchestrate` calls `llm.complete` before Sapling.
- `ui/sim/sim.js`, `ui/sim/index.html`, and `ui/sim/README.md` still say `gateway.route_chooser` is `TODO_HUMAN`. On main the decided value is `field precheck`, and `config/routing.yaml` `mode` is `cascade`.
- `load_dispatch_resources` does not give Sukhumvit units for town calls. `data/snapshots/places.json` has Lampang, Phrae, Nan, and Phayao only. The phone posts a fixture id, so `fields.location` stays the fixture district. A same-district match is one of those northern OpenStreetMap units.

### 3.1 Phone turn to the gateway

Producer: the town phone (`ui/sim/sim.js` `runPlaceCall`). Consumer: Moly's `gateway.route.handle` via `api/routes/endpoints.py` `execute` (`use_stubs=True`).

Path: `POST /cases` `{ "fixture_id": "F02" }` then `POST /cases/{case_id}/turns` with a `TranscriptTurn`. The turn response is `TurnResult`: `case` (`CaseState`) and `decision` (`RouterDecision`). `POST /triage` takes a full `CaseState` and returns the same `RouterDecision`. The phone does not call `/triage`.

`CaseState` required: `case_id`, `caller_id_hash`, `transcript`, `fields`, `received_at`. `TranscriptTurn` required: `t_ms` (int ≥ 0), `speaker` (`caller` or `operator`), `text` (non-empty).

To match the gateway, Melanie must provide either a known `fixture_id` or a `transcript` of `TranscriptTurn`s. A body with neither is HTTP 422. Moly must accept that turn and return one `RouterDecision`. He must not route from `fixtures/... expected.system`. The chooser reads fields and `policy_flags`.

Minimal turn:

```json
{ "t_ms": 1000, "speaker": "caller", "text": "Our rice is finished." }
```

Mismatch: open item 4. `demoChoose`, `ui/sim/index.html`, and `ui/sim/README.md` still say `gateway.route_chooser` is `TODO_HUMAN`. The decided value is `field precheck`, and the mode is `cascade`. The phone posts `fixture_id`, so extract and the chooser never see the spoken text.

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

`extract` reads caller turns, plus an operator question the next caller sentence confirms (`yes`, `yeah`, `correct`, or `that's right`). Confirmed operator text counts for `vulnerable`, `people_count`, and `danger` only, never for needs or flags. A negator in the three words before a match drops it. Aid phrases and minimising phrases are exempt: "we cannot get the payment" and "not eligible" stay aid signals. Suggested flags are `conflicting_evidence` (minimising language plus danger, rescue, medical, or a child, elderly person, or immobile person), `safeguarding` (a child and an alone-phrase), and `aid_exception` (an aid phrase plus a refusal). Water at a door, step, or inside a room, or in the street, adds danger `rising_water`. That also adds need `rescue` when a child, elderly person, immobile person, or oxygen-dependent person was extracted, or when the water is at the building and evacuation was not already a need. "bus shelter" is not a shelter need.

To match the chooser, Melanie must leave those field names and flag strings as they are when she builds a non-fixture case. Moly must keep the phrase families English-only. District names match Thai and English. A confirmed operator question counts for `vulnerable`, `people_count`, and `danger` only. `system1.extraction_method` is `rules-only`. `system1.extraction_model` stays `TODO_HUMAN` and the rules do not read it.

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

Mismatch: `make extract-eval` scores extract against hand-filled fixture fields, and again against the scripted sim callers. An unsafe answer is a case whose true fields go to System 2 while the extracted fields get a System 1 answer with `requires_human` false. Fixture cases on the phone never take the extract path. `F15` is still misrouted for that reason: hand fields include `vulnerable: child`, the word "child" is only in an operator turn ("I can hear a child crying"), and caller text says "They are upset" and "invented bus shelter". Open item 10: `G01`–`G04` are labelled `expected.system` `system_1` with need `rescue`, and `config/escalation.yaml` routes `rescue` to System 2. Town `calls[].expected_system` is the fixture label, not the chooser's result.

### 3.3 Memory items to System 1 and the router

Producer: Melanie `memory.adapter.retrieve(case) -> list[MemoryItem]`. Consumer: Moly `system1.decide` (duplicate rule) and `router.merge` (correction notes). The gateway assigns the list onto `case.memory_context` before the chooser.

`MemoryItem` required: `memory_id`, `kind`, `summary`, `relevance` (0–1). Optional `source_case_id`. `kind`: `similar_case`, `prior_failure`, `policy`, `correction`.

`MEMORY_IMPL=mock` (default) reads `mocks/memory_context/{case_id}.json`, or an empty list when the file is missing. `MEMORY_IMPL=mubit` calls `memory.mubit.retrieve`, which raises.

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

`memory.adapter.store_record` is not called anywhere in the gateway. Mock mode raises. See 3.6 for what a `MemoryRecord` needs.

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

Dispatch fan-out only for that last action, one `Dispatch` per mapped need: `rescue`→`boat`, `medical`→`ambulance`, `water` and `food`→`welfare_point`, `shelter` and `evacuation`→`shelter`. `power`, `information`, and `aid_payment` produce none. The turn uses `load_dispatch_resources()`: OpenStreetMap boats, ambulances, and shelters from `data/snapshots/places.json`, then the fictional units in `mocks/resources.json`. Welfare points are fictional only. A unit this case already holds wins, else a same-district unit (district name contained in `fields.location`), else the first usable unit, else `status=unfilled` and `resource_id` null. Usable means `available` minus reservations other cases hold in `router/ledger.py`. Neither JSON file is rewritten. Holds live in this process and reset on restart. With no district match, that first usable unit is an OpenStreetMap unit when the kind has one. Open item 7. There is no Sukhumvit unit in the snapshot, so a town call does not reserve one (open item 6).

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

To match the phone, Moly must keep those `RouterDecision` and `Outcome` fields populated on every turn, including stub turns. `source_outcomes` keeps the deciding outcome first (`[deciding, *prior]`). Melanie must keep reading `final_priority` for the house light. CR-003 is tagged `v0.3-contracts`. Melanie's town must show the router's reserved `resource_id`, and that id has to be one the block can draw. The placed ids are the four fictional ids in `mocks/resources.json`. `sim.js` still does not read `dispatches`, `resource_id`, or `resource_kind`. An OpenStreetMap id is not on the block.

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

Mismatch: open item 8 below. The feed's ACCEPTED/REJECTED verdict comes from `sim_events.json` scores. `confidence_threshold` is now 0.8, matching `system_1_min_confidence`. `learning.promote_after` is still 3, and the copy says the fast path can take the call. That is not `source_outcomes[0].system`, and it is not graduation. It can say ACCEPTED while that system is `system_2`, or the reverse. Sapling cards use a simulated `verdict` (`supported`, `violation`, `missing`, `unsure`). The gateway does not add `sapling_verdict` on the stub path. `contradicted` is a real Sapling label and is not one of the simulated card verdicts. There is no `GET /cases/{id}/events` stream. `BaanSafeSim.attachLiveFeed` is the unused hook.

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

To match a future `store_record`, Moly must provide the `ExtractedFields` he decided from and the `RouterDecision` `merge` returned, plus each `Correction` already stored. Melanie must accept that bundle in `memory.mubit.write`. Nothing in `gateway/` or `api/` builds a `MemoryRecord` today. `store_record` raises in mock mode. A System 1 correction therefore lands as a `Correction` JSONL line and, when v1 fields are present, as a `TrainingEvent`. It does not land inside a `MemoryRecord`.

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

Both model leaves are decided, so `orchestrate` calls Nemotron through `llm.complete` when `S2_IMPL=real` or `use_stubs=False`. `execute` always passes `use_stubs=True`, so the live call happens only when `S2_IMPL=real`. A missing Mubit URL or key raises `RuntimeError`. `execute` and the System 2 probe in `POST /replay` map that to HTTP 503 and put `str(exc)` in `detail`. The town note shows that body. A timeout, HTTP error (including 429, named in the reason as `HTTPStatusError 429 (rate limited)`), empty reply, or parse/enum failure becomes a safe `system2_unavailable` outcome and does not raise.

### 3.9 Context and resources

Producer: Moly `enrich.context.location_context` and `mocks.loader.load_dispatch_resources`. Consumer: `GET /context` and `GET /resources`. The town does not call either endpoint. `ui/sim/data/places.json` is a label file written from the same place snapshot.

`GET /context` query: optional `district`, `lat`, `lon`. The body is the `location_context` dict. New keys on every response: `matched_province` (str or null), `near_flood_extent` (bool), `distance_to_live_flood_m` (number or null), `regional_reservoirs` (object or null). `regional_reservoirs`, when set, is `{date, scope, dams}` for Lampang, Phrae, Nan, or Phayao. When `ENRICH_IMPL` is off, or no SQLite file exists, the handler returns that dict at the empty defaults and adds `"enrich": "off"`. There is no SQLite file in the tree, so a normal request takes that path. Open-Meteo and RID snapshots are read only inside the SQLite path.

`GET /resources` returns `ResourcesSnapshot`: `boats`, `ambulances`, `shelters`, `welfare_points`. Each unit has `id`, `kind`, `name`, `district`, `capacity`, `available`, `status`. An OpenStreetMap unit has `capacity` null, `available` 1, and `id` `{kind}-{osm_type}-{osm_id}` (`shelter-way-679376537` is the shape). Hospitals map to `ambulance`, schools and temples to `shelter`, boat rentals and ferry terminals to `boat`.

To match the block, Moly must put a `resource_id` from `mocks/resources.json` on a dispatch the sim is expected to draw. Melanie must not invent a unit id. Country packs do not change either endpoint.

## 4. Open items

These are conflicts on `edd64d0`. They are not leaves this note will set in `config/decisions.yaml`. #6 merged as `3f14f8d`. #7 merged as `9e61fd4`.

1. **Moly edited Melanie's System 2 files.** `OWNERSHIP.md` gives `system2/` and `system2/orchestrator.py` to Melanie. `9da21c7` changed `system2/orchestrator.py` and `system2/decide.py`. Melanie should review them.
2. **RL graduation into System 1 contradicts the older rule.** `gateway/graduation.py` (`correction_loop.escalation_threshold`) still never moves a pattern into System 1. `eval/rl/learner.py` (`correction_loop.graduation_threshold`, live only with `RL_OVERLAY`) writes a System 1 rule for a repeated non-complex System 2 decision. `system1/decide.py` returns that rule as `fast_route`. Melanie needs to confirm this. The threshold keys are already decided as 2. This note does not change them.
3. **`GET /rl/run` is 404 on Modal.** The handler reads `eval/out/rl/run.json`. `.dockerignore` excludes `eval/out`. The panel then says it could not load `/rl/run`.
4. **The phone still says the chooser is unset.** `ui/sim/sim.js`, `ui/sim/index.html`, and `ui/sim/README.md` say `gateway.route_chooser` is `TODO_HUMAN`. It is decided: `field precheck`, and `routing.yaml` is `cascade`. The phone still posts `fixture_id`, so the spoken sentence never reaches extract.
5. **The hosted demo does not call Nemotron.** `infra/modal/gateway_app.py` sets `S2_IMPL=stub`. The free tier can return 429 when a real call is made. `orchestrate` turns that into `system2_unavailable` (`HTTPStatusError 429 (rate limited)`), which is not the HTTP 503 path.
6. **The picture and the dispatch list are different places.** The block draws Sukhumvit, Watthana. `data/snapshots/places.json` has Lampang, Phrae, Nan, and Phayao only, and no Sukhumvit unit. Town calls post fixture ids, so `fields.location` stays the fixture district and a same-district unit is one of those northern places. `data.demo_event` is `TODO_HUMAN`. A person has to pick one map. This note does not.
7. **A call with no district match can reserve a unit the sim cannot draw.** `load_dispatch_resources` lists OpenStreetMap units first. `router/merge.py` then takes `units[0]`. That id looks like `shelter-way-{osm_id}` and is not in `mocks/resources.json`. The block only places `boat-fictional-01`, `amb-fictional-01`, `shelter-fictional-01`, and `welfare-fictional-01`. Proposed fix: list the fictional units first, or make the fallback skip OpenStreetMap units. This note does not pick which.
8. **The town learning story still promotes into System 1 after 3 repeats.** `ui/sim/data/sim_events.json` `learning.promote_after` is 3. That copy is neither human-correction escalation nor the RL overlay. `confidence_threshold` is 0.8. Melanie should align it with one of those two paths.
9. **Stock holds do not survive a second container.** `router/ledger.py` keeps reservations in a process dict. They reset on restart. The Modal app says cases stay in memory until the container scales down. Several containers would each hold their own stock. Recommendation: pin that app to one container, or persist the holds. This note does not pick which.
10. **`G01`–`G04` labels still say System 1.** Each fixture `expected.system` is `system_1` with need `rescue`. The precheck routes `rescue` to System 2. `mocks/s2_stub/G01.json` through `G04.json` are the stub outcomes that path loads. `G01.json`'s reason still says the threshold is unset. `correction_loop.escalation_threshold` is 2. Recommendation: relabel the fixtures, or change their need. This note does not do either.

## 5. Decide before 19:00 integration

`OWNERSHIP.md` names the integration as `S1_IMPL=real`, `S2_IMPL=real`, and `MEMORY_IMPL=mubit` together. Contracts stay frozen at `v0.3-contracts` until then. This list does not pick the remaining choice.

- Free text versus fixture ids on the phone. Today the phone posts a fixture id. `POST /cases` already accepts a transcript and empty fields (open item 4).
- Which place the picture is. `data.demo_event` is `TODO_HUMAN` (open item 6). The streets are Sukhumvit. The snapshots and fixture locations are Lampang, Phrae, Nan, and Phayao.
- Whether RL graduation into a System 1 rule stands (open item 2). Melanie confirms. The threshold numbers stay 2.
- The town showing `dispatches` is no longer an open choice. Melanie shows the router's reserved `resource_id`, and that id is one of the four in `mocks/resources.json` (open item 7). `sim.js` does not read `dispatches` yet.

## 6. Open decisions

These leaves are `TODO_HUMAN` in `config/decisions.yaml`. Decided leaves, not open: `system1.extraction_method` `rules-only`, `gateway.route_chooser` `field precheck`, `system2.hosting` `openrouter via mubit gateway`, `system2.use_banyan_sapling` true, `system2.sapling_scope` `aid_eligibility,denial`, `sapling.client` `stub`, `llm.provider_route` `mubit`, `system2.orchestrator_model` `nvidia/nemotron-3.5-lightning:free`, `system2.max_latency_ms` `10000`, `correction_loop.graduation_threshold` `2`, `correction_loop.escalation_threshold` `2`.

| Key | Who is blocked |
|---|---|
| `system1.extraction_model` | Nobody on the rules path. A model extractor is blocked. Moly owns that choice. |
| `sapling.hosting`, `sapling.gpu`, `sapling.model_id`, `sapling.thai_handling` | Melanie, only for `SAPLING_IMPL=live`. The stub client does not read them. |
| `gateway.auth` | Moly, for a scheme that can reject a request. Calls are not blocked. |
| `memory.mubit_project`, `memory.retrieval_top_k`, `memory.token_budget` | Melanie. `memory.mubit` raises. Mock retrieval still works. |
| `llm.token_price_usd` | Melanie's cost column. `eval/compare.py` leaves `cost_usd` null. Calls are not blocked. |
| `speech_to_text.provider` | The phone demo. A clip with no browser transcript is not sent. |
| `ui.framework` | Nobody for the static town page. A framework choice is blocked. |
| `data.demo_event` | Anyone claiming the picture is a specific flood. The page stays a placeholder. |
| `data.production_db` | A production database. SQLite remains the store. |
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
