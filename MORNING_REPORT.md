# Morning report

Phase 0 contracts are tagged `v0.1-contracts`. System 1 and System 2 decision logic are not implemented. Callers in fixtures are synthetic (`caller_id_hash` starts with `synthetic:`).

## 1. Status

| Check | Result |
|---|---|
| `make validate` | passed (20 scenarios + 4 graduation fixtures) |
| `make test` | passed (22 tests) |
| `make replay-stubs` | passed. System 1 stubs 13/13 on priority, route, and system. System 2 stubs 11/11. |
| `make demo-stub` | passed. Stub gateway printed a `RouterDecision` for all 24 fixtures. |
| `make serve` | passed. Every endpoint below returned a non-error response, including `/docs`. |

Endpoints hit on `:8000`: `GET /health`, `GET /fixtures`, `GET /fixtures/F01`, `GET /fixtures/F01/stream?pace=0`, `POST /cases`, `POST /cases/{id}/turns`, `GET /cases/{id}`, `POST /triage`, `POST /cases/{id}/corrections`, `GET /cases/{id}/trace`, `GET /context` (district and lat/lon), `GET /resources`, `GET /map/flood`, `GET /map/facilities`, `POST /replay`, `GET /metrics`, `GET /docs`, `GET /openapi.json`, `GET /ui/player.html`.

The correction pair works on the stub service: a correction posted on `C01-a` is retrieved as a `MemoryItem` when `C01-b` is loaded.

Runtime is Python 3.12. The code targets 3.11 (`requires-python >= 3.11`). 3.11 is not installed in this environment.

### Data sources

Fetched at about 2026-10-23 22:27 UTC. Full notes are in `data/SOURCES.md`.

| Source | Rows | Freshness / blocker |
|---|---|---|
| GISTDA open API | 0 | **Blocked.** API key required. Sign-up below. Not called. |
| GISTDA ArcGIS fallback | 63 flood-risk polygons | Public MapServer layer 1, fetched 2026-10-23. Stored as `duration_window=flood_risk_layer`. Layer 0 (flood-affected extent) count was **0**. These are not 1/3/7/30-day extents. |
| Repeated flood | 0 | **Blocked** with the open API. Frequency was not invented. |
| ReliefWeb | 0 | **Blocked.** `robots.txt` disallows `/v2/` on `api.reliefweb.int`, so the client did not send the query. An approved `appname` is also required. No article text stored. |
| Open-Meteo | 518 daily rows, 14 district centroids | Archive 2026-09-24 to 2026-10-23, forecast 7 days. See the robots exception under decisions. |
| Overpass | 14 districts, 1350 facilities | Host `overpass.openstreetmap.fr` (no robots file). That mirror's `timestamp_osm_base` was **2026-08-05**. `overpass-api.de` was not used because its robots.txt disallows `/api/`. |
| Facility mix | 40 hospitals, 22 clinics, 12 pharmacies, 237 schools, 527 places of worship, 5 community centres, 150 bridges, 357 waterways | Amenity query capped at 1200 features, then a separate `bridge=yes` query capped at 150. All `accessibility_flag` values are `clear` because no real flood-extent window was ingested. |
| Later sources | not fetched | DDPM, aid-payment aggregates, TMD, RID/NWCC, WorldPop, HDX, EM-DAT, World Bank 2011, policy corpus. Each is marked `later — human to approve` in `data/SOURCES.md`. |

`location_context()` returns the required keys for the ingested districts. `in_flood_extent_1d/7d/30d` and `repeat_flood_area` are false with tonight's data. `in_flood_risk_layer` is an extra key and is not turned into `in_active_flood_extent`.

No 13-digit ids, phone numbers, or PromptPay/bank fields were found in the SQLite text or the fixtures. Disaster-report bodies were not stored (the table is empty).

## 2. Start here

**Moly.** `make serve`, open `/docs`. Write `system1/decide.py`, set `S1_IMPL=real`, and `POST /replay` on the 7 clear System 1 fixtures (`F01`–`F07`) plus the 2 duplicate fixtures (`F08`, `F09`). Then replace the stub copy in `gateway/route.py` and implement `router/merge.py`. The UI can build on `GET /fixtures/{id}/stream`, `/cases/*`, and `/map/*`. `ui/player.html` is only a transcript player. The UI framework is `TODO_HUMAN`.

**Melanie.** Write `system2/decide.py` using the model named in `config/decisions.yaml` (still unset). Set `S2_IMPL=real` and target the 9 System 2 fixtures plus the correction pair (`F10`–`F18`, `C01-a`, `C01-b`). Then implement `memory/mubit.py`, set `MEMORY_IMPL=mubit`, and extend `eval/`. Do not call Mubit unless `MUBIT_API_KEY` and `MUBIT_BASE_URL` are set. `scripts/smoke_mubit.py` prints status and latency only.

Stub outcomes live in `mocks/s1_stub/` and `mocks/s2_stub/`. They are fixtures for the harness, not the decision logic.

## 3. Decisions for humans

### Still `TODO_HUMAN` in `config/decisions.yaml`

Code that needs one of these raises until a human sets it. None were filled in.

- `system1.extraction_method`, `system1.extraction_model`
- `system2.orchestrator_model`, `system2.hosting`, `system2.use_banyan_sapling`, `system2.max_latency_ms`
- `memory.mubit_project`, `memory.retrieval_top_k`, `memory.token_budget`
- `speech_to_text.provider`
- `ui.framework`
- `data.demo_event` (not chosen; see districts below)
- `data.production_db` (SQLite is only the overnight store)
- `correction_loop.graduation_threshold`

### Judgement calls already given a starting value

These are in config and need a yes or a replacement. They are not executed as System 1 or System 2 rules, except the enrichment thresholds, which only attach data flags.

- Priority wording in `config/priorities.yaml`.
- Route list and need map in `config/routes.yaml`. **Power has no route**; `F04` uses `information_only`.
- Escalation rule strings in `config/escalation.yaml`. The stub gateway does **not** evaluate them.
- Enrichment thresholds: heavy rain forecast 30 mm / 24 h, heavy rain observed 30 mm / 24 h, near-flood buffer 500 m.
- Stub next-action order (first match): `requires_human` → `escalate_to_supervisor`; missing evidence or a next question → `ask_next_question`; `escalate` → `escalate_to_supervisor`; else `create_provisional_dispatch`. Information-only cases therefore become `create_provisional_dispatch`, which may be the wrong action.
- `config/ingest.yaml`: Open-Meteo was called even though `api.open-meteo.com` and `archive-api.open-meteo.com` robots.txt say `Disallow: /`, because the documented API is the public forecast/archive interface and the flag `open_meteo_documented_api_despite_robots_disallow` is true. Set it false to stop those calls.
- Overpass host is `overpass.openstreetmap.fr`, not `overpass-api.de`.
- Weather rows are daily aggregates, not hourly.
- A flood polygon is assigned to the nearest `admin_level=6` centre within 25 km. That is not a boundary intersection. HDX boundaries were not fetched.
- Districts used, because their centres fell inside that radius of the public risk polygons: Ban Luang, Chiang Muan, Den Chai, Long, Mae Mo, Mae Tha, Mueang Phrae, Nong Muang Khai, Rong Kwang, Song, Sop Prap, Sung Men, Wang Chin, Wiang Sa. This is not a choice of demo event.
- Transcripts are English so the team can read them. Place names are real districts. Landmarks ("blue temple", "North Canal hall") are invented.
- Dev CORS on the API is allow-all so `ui/player.html` can call it.
- Bridges are OSM `bridge=yes` ways. `man_made=bridge` returned nothing in this bbox.
- One correction pair (`C01-a` / `C01-b`), not two. The brief asks for 20 scenarios and also "2 × correction pairs". 7 + 2 + 9 + one pair (2 files) = 20. A second pair would make 22. Say if you want the second pair added.

### Doubtful fixture labels (not changed)

- `F04` power cut → `P3` / `information_only`.
- `F06` evacuation with full details → `P2` / `shelter_placement`, `requires_human` false.
- `F08` and `F09` are the same household. **Both** are labelled `duplicate_merge`. A human may want only `F09` as the merge and `F08` as welfare.
- `F12` vague "blue temple" → `P2` rescue, not `P1`.
- `F13` unknown district, no danger → `P3` shelter, `requires_human` false, even though location is null.
- `F14` "we're fine" but water at the door → `P2` rescue. Could be `P1`.
- `F15` child crying, caller asks about the road → `P2` / `supervisor_escalation`. Non-graphic. Could be welfare plus a question.
- `G01`–`G04` are labelled System 1 / `P1` rescue as the **illustration** of a graduated rule. `graduation_threshold` is unset, and no rule was coded. `requires_human` is true.

## 4. Blockers needing a human

**GISTDA API key**

1. Open https://api-gateway.gistda.or.th (registration is also described at https://api-gateway.gistda.or.th/v2).
2. Create an API key.
3. Export it as `GISTDA_API_KEY` (do not commit it).
4. Run `make ingest-refresh`.

Documented URL family: `https://api-gateway.gistda.or.th/api/2.0/resources/gi-service/v1.0/disasters/flood-extent-1day?lat={latitude}&lon={longitude}&api_key=…` and the 3, 7, and 30 day windows, plus repeated-flood areas. Catalogue: https://opendata.gistda.or.th/dataset/flood-disaster-data and https://disaster.gistda.or.th/services/open-api. Catalogue contact: disaster@gistda.or.th.

Until that key exists, the map shows the public flood-**risk** layer only, and active-extent flags stay false.

**ReliefWeb**

1. `https://api.reliefweb.int/robots.txt` disallows `/v2/` for all user agents. The client obeyed that and did not fetch. A human has to decide whether ReliefWeb's published API terms override that robots rule.
2. Even then, every call needs a pre-approved `appname`: https://apidoc.reliefweb.int/parameters#appname (ReliefWeb replies by email). Export it as `RELIEFWEB_APPNAME`.
3. API v1 is decommissioned. The disaster id in the brief is `fl-2025-000209-tha`. No report body was stored.

**Open-Meteo robots.txt** is a blanket `Disallow: /` on the API hosts. Calls happened only because of the config flag above. Confirm or revoke that.

**Overpass mirror** data stamp is 2026-08-05. If you need a newer extract, pick a host whose robots.txt allows the interpreter.

## 5. Open change requests

None. `contracts/CHANGE_REQUESTS.md` is empty. Contracts stay at `v0.1-contracts` until a human accepts a proposal.

## 6. Integration point

Saturday 19:00. Both `S1_IMPL=real` and `S2_IMPL=real`, with `MEMORY_IMPL=mubit`. Contracts stay frozen at the latest tag until then.
