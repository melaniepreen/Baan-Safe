# Morning report

Phase 0 contracts are tagged `v0.1-contracts`. System 1 and System 2 decision logic are not implemented. Callers in fixtures are synthetic (`caller_id_hash` starts with `synthetic:`).

Background for Phase 1 is in `research/INDEX.md`. Nothing in that folder changes config.

## 1. Status

| Check | Result |
|---|---|
| `make validate` | passed (20 scenarios + 4 graduation fixtures) |
| `make test` | passed (27 tests) |
| `make replay-stubs` | passed. System 1 stubs 13/13 on priority, route, and system. System 2 stubs 11/11. |
| `make demo-stub` | passed. Stub gateway printed a `RouterDecision` for all 24 fixtures. |
| `make serve` | passed. Every endpoint below returned a non-error response, including `/docs`. |

Run those with `PYTHON=.venv/bin/python` if `python3` has no pytest. This environment is Python 3.12. The code targets 3.11.

Endpoints hit on `:8000`: `GET /health`, `GET /fixtures`, `GET /fixtures/F01`, `GET /fixtures/F01/stream?pace=0`, `POST /cases`, `POST /cases/{id}/turns`, `GET /cases/{id}`, `POST /triage`, `POST /cases/{id}/corrections`, `GET /cases/{id}/trace`, `GET /context` (district and lat/lon), `GET /resources`, `GET /map/flood`, `GET /map/facilities`, `POST /replay`, `GET /metrics`, `GET /docs`, `GET /openapi.json`, `GET /ui/player.html`.

The correction pair works on the stub service: a correction posted on `C01-a` is retrieved as a `MemoryItem` when `C01-b` is loaded.

### Data sources

Counts below are the database committed with this report. Full sentences, licences, and the HDX candidate list are in `data/SOURCES.md`. Times are Europe/London (UTC+1).

| Source | Rows | Freshness / blocker |
|---|---|---|
| GISTDA open API, live extent | 228 polygons (Songkhla 7-day 120, 30-day 108) | Key read from `GISTDA_API_KEY` in the gitignored `.env`. The key is not in the repo, the cache URLs, or this report. National `numberMatched`: 1-day 0, 3-day 0, 7-day 70,630, 30-day 185,645. Stored pages are Songkhla only. A count-only scan (codes 10–96) shows the 7-day water is in the central plain (Suphan Buri, Ayutthaya, and Nakhon Sawan each above 10,000) plus Pattani (404) and Songkhla (120). Those central pages were not stored: a first page of a 10,000-cell layer would look like a complete flood. |
| GISTDA repeat flood | 400 | National frequency layer is 7,874,656 polygons. Cap 400, split across the eight configured provinces. Not a national layer. |
| GISTDA ArcGIS risk layer | 63 | Public MapServer layer 1. Layer 0 count was 0. `duration_window=flood_risk_layer`. Not a 1/3/7/30-day extent. |
| GDACS | 3 reports, 3 polygons | Fetched 05:05–05:08 Europe/London on 24 Oct 2026, inside `Visit-time` 05:00–07:45, one request a minute. robots.txt was read as text. An earlier attempt at 02:43 Europe/London is not in this commit: a JSON `Accept` header made `/robots.txt` return HTTP 406 HTML, the client treated that as no rules, and those rows and the cache were deleted. |
| GLIDE via HDX | 109 | CC BY-IGO. `event_id` is the GLIDE number. Comments clipped to 280 characters. https://data.humdata.org/dataset/tha-glide-events |
| IDMC via HDX | 14 flood rows | CC BY-IGO. 9 non-flood rows skipped (conflict and wildfire). 1 extra flood figure dropped because a recommended figure exists. `affected_people` is a displacement flow, not a census. A standalone GLIDE token is the `event_id`. An AHA-only code stays `idmc-event-<id>`. The 17 Nov 2025 multi-province figure (219,000) has an empty `event_codes` field, so it was not joined. https://data.humdata.org/dataset/tha-idmc-idu-events |
| EOS-RS Hat Yai | 1 dissolved polygon | CC BY, preliminary, 23 Nov 2025, v0.9, 9,172 source polygons. `duration_window=observed`. Sentinel-1, analysed by EOS-RS. `event_id` `FL-2025-000210-THA` is a judgement: that GLIDE record is the southern flood of 17 Nov 2025, and the location text says Thailand, not Hat Yai. Confirm it before treating the join as exact. |
| UNOSAT water extents | 3 dissolved polygons | CC BY-SA (attribution and share-alike). Phayao accumulated Aug–Oct 2024, Doi Tao (Chiang Mai) 6 Oct 2024, Chaiyaphum and Nakhon Ratchasima. `duration_window=observed`. Shapefiles over 20 MB were not fetched; they are candidates in `data/SOURCES.md`. |
| HDX search | 37 packages | `q=thailand flood`. Stored rows are above. The rest are candidates (other EOS-RS bundles, damage assessments, ODbL waterways, UNOSAT files over the size cap). File downloads redirect to `s3.us-east-1.amazonaws.com`; that host is allowed for those downloads only, and the signed query is redacted before it is cached. |
| ThaiWater | 805 level stations, 4,774 rain gauges, 50 district rows | Public portal JSON. `api-v3.thaiwater.net/robots.txt` is 404, so the client allows it. Not the keyed exchange API. Station and village names are not stored. Level labels are the feed's own scale: 18 over bank (`น้ำล้นตลิ่ง`), 141 high, 355 normal, 209 low, 67 critically low, 15 unlabelled. Where a gauge matched a district, `rainfall_last_24h_mm` prefers that gauge over Open-Meteo. |
| Open-Meteo | 1,850 daily rows, 50 districts | Archive 24 Sep–23 Oct 2026, forecast 7 days. API robots.txt is `Disallow: /`. Calls happened because `open_meteo_documented_api_despite_robots_disallow` is true. |
| Overpass | 50 districts, 4,218 facilities | Host `overpass.openstreetmap.fr` (no robots file). `overpass-api.de` was not used. Four clusters kept of seven: risk layer (14 districts), EOS-RS (3), two GDACS clusters (34 and 2 before the cap). All 14 fixture districts still resolve. Hat Yai District is not one of the 50. |
| ReliefWeb | 0 | Retired. No request is sent. robots.txt disallows `/v2/`, and the API wants a pre-approved appname. |
| DDPM | not added | Left out of this run on the owner's instruction. |

Facility mix: 176 hospitals, 183 clinics, 166 pharmacies, 807 schools, 1,487 places of worship, 53 community centres, 541 bridges, 805 waterways. Flags: `inside_flood_extent` 0, `near_flood_extent` 0, `inside_observed_event` 1,363, `near_observed_event` 251, `clear` 2,604. Live 1/3/7/30-day polygons are Songkhla and were not one of the four Overpass clusters, so the queried facilities do not sit on a live extent. Observed polygons do set `in_observed_event_extent`. They do not set `in_flood_extent_1d/7d/30d` or the gateway's active-extent flag.

No phone numbers or 13-digit ids were written into SQLite text. Summaries are clipped to 280 characters. The GISTDA key is not in any git-tracked file.

### Research index

| File | What it is |
|---|---|
| `research/thai-flood-management.md` | DDPM, RID, ONWR / the water command, TMD, GISTDA, 1784, governors and local government, the 2007 Act, relief payments without a baht figure. |
| `research/international-practice.md` | Sendai, IASC clusters, Sphere water/shelter/food figures, CAP alerts. |
| `research/triage-philosophy.md` | MPDS/NHS 111 style dispositions, START/SALT, vulnerability, human sign-off, and a reading of Priority / Route / escalation. Suggestions only. |
| `research/lessons-thai-floods.md` | 2011 and Hat Yai in November 2025, for call triage: moving water, vague locations, duplicates, comms loss. |
| `research/glossary-and-risk-areas.md` | Thai/English flood words, caller phrases, and the places the public records actually name. |
| `research/INDEX.md` | One line per file, plus "Other context worth getting". |

## 2. Start here

**Moly.** `make serve`, open `/docs`. Write `system1/decide.py`, set `S1_IMPL=real`, and `POST /replay` on the 7 clear System 1 fixtures (`F01`–`F07`) plus the 2 duplicate fixtures (`F08`, `F09`). Then replace the stub copy in `gateway/route.py` and implement `router/merge.py`. Read `research/triage-philosophy.md` before changing a threshold. The UI can build on `GET /fixtures/{id}/stream`, `/cases/*`, and `/map/*`. `ui/player.html` is only a transcript player. The UI framework is `TODO_HUMAN`.

**Melanie.** Write `system2/decide.py` using the model named in `config/decisions.yaml` (still unset). Set `S2_IMPL=real` and target the 9 System 2 fixtures plus the correction pair (`F10`–`F18`, `C01-a`, `C01-b`). Then implement `memory/mubit.py`, set `MEMORY_IMPL=mubit`, and extend `eval/`. Do not call Mubit unless `MUBIT_API_KEY` and `MUBIT_BASE_URL` are set. `scripts/smoke_mubit.py` prints status and latency only. `research/lessons-thai-floods.md` and `research/glossary-and-risk-areas.md` are the background for vague locations, duplicates, and Thai phrases. They are not fixtures.

Stub outcomes live in `mocks/s1_stub/` and `mocks/s2_stub/`. They are fixtures for the harness, not the decision logic.

## 3. Decisions for humans

### Still `TODO_HUMAN` in `config/decisions.yaml`

Code that needs one of these raises until a human sets it. None were filled in.

- `system1.extraction_method`, `system1.extraction_model`
- `system2.orchestrator_model`, `system2.hosting`, `system2.use_banyan_sapling`, `system2.max_latency_ms`
- `memory.mubit_project`, `memory.retrieval_top_k`, `memory.token_budget`
- `speech_to_text.provider`
- `ui.framework`
- `data.demo_event` (not chosen; the new polygons make Hat Yai a candidate alongside the northern fixture districts)
- `data.production_db` (SQLite is only the overnight store)
- `correction_loop.graduation_threshold`

### Judgement calls already given a starting value

These are in config or in the ingest code. They are not System 1 or System 2 rules.

- Priority wording in `config/priorities.yaml`.
- Route list and need map in `config/routes.yaml`. **Power has no route**; `F04` uses `information_only`.
- Escalation rule strings in `config/escalation.yaml`. The stub gateway does **not** evaluate them. `research/triage-philosophy.md` suggests how a human might read them. It does not edit them.
- Enrichment thresholds: heavy rain forecast 30 mm / 24 h, heavy rain observed 30 mm / 24 h, near-flood buffer 500 m. A ThaiWater gauge, when one was matched, supplies `rainfall_last_24h_mm`.
- Historical and preliminary polygons use `duration_window=observed`. They set `in_observed_event_extent` and the facility flags `inside_observed_event` / `near_observed_event`. They do not set the live extent flags.
- Stub next-action order (first match): `requires_human` → `escalate_to_supervisor`; missing evidence or a next question → `ask_next_question`; `escalate` → `escalate_to_supervisor`; else `create_provisional_dispatch`.
- Open-Meteo was called despite `Disallow: /` because `open_meteo_documented_api_despite_robots_disallow` is true. Set it false to stop those calls.
- Overpass host is `overpass.openstreetmap.fr`. At most 4 clusters, each bbox at most 4 degrees, then at most 50 district centres within 25 km. That is nearest centre, not a boundary intersection. Order: risk layer, EOS-RS, GDACS, UNOSAT, then live extents. The risk layer is kept so the fixture districts still resolve.
- The two December 2025 GDACS events share one small polygon over central Bangkok (about 13.78–13.87 N, 100.52–100.61 E). Thirty-four district centres fall within 25 km of it, which is why Bangkok fills most of the cap of 50. The 17 Nov 2025 polygon is the southern one and carries GLIDE `FL-2025-000210-THA`.
- Hat Yai's map is joined to that same GLIDE id with the caveat in `data/SOURCES.md`. `FL-2025-000209-THA` is a different record (Ayutthaya / Bangkok) and was not used for Hat Yai.
- UNOSAT is stored only for CC BY, CC BY-SA, CC BY-IGO, CC0, or ODC-BY, and only when the shapefile is at most 20 MB. CC BY-SA needs attribution and share-alike.
- IDMC conflict rows are not stored. The displacement figure is labelled as a flow.
- GISTDA downloads stay inside the configured province list and the caps in `config/ingest.yaml`. Empty provinces do not use up the extent cap, so Songkhla's 7-day and 30-day pages are complete (120 and 108). Repeat-flood rows stay an even split.
- ThaiWater is one snapshot of the public portal, not a history.
- Weather rows are daily aggregates, not hourly.
- Transcripts are English so the team can read them. Place names are real districts. Landmarks ("blue temple", "North Canal hall") are invented.
- Dev CORS on the API is allow-all so `ui/player.html` can call it.
- Bridges are OSM `bridge=yes` ways.
- One correction pair (`C01-a` / `C01-b`), not two. The brief asks for 20 scenarios and also "2 × correction pairs". 7 + 2 + 9 + one pair (2 files) = 20. A second pair would make 22.

### Doubtful fixture labels (not changed)

- `F04` power cut → `P3` / `information_only`.
- `F06` evacuation with full details → `P2` / `shelter_placement`, `requires_human` false.
- `F08` and `F09` are the same household. **Both** are labelled `duplicate_merge`. A human may want only `F09` as the merge and `F08` as welfare.
- `F12` vague "blue temple" → `P2` rescue, not `P1`.
- `F13` unknown district, no danger → `P3` shelter, `requires_human` false, even though location is null.
- `F14` "we're fine" but water at the door → `P2` rescue. Could be `P1`.
- `F15` child crying, caller asks about the road → `P2` / `supervisor_escalation`. Non-graphic. Could be welfare plus a question.
- `G01`–`G04` are labelled System 1 / `P1` rescue as the **illustration** of a graduated rule. `graduation_threshold` is unset, and no rule was coded. `requires_human` is true.

### Suggested next decisions

Not done in this run. Each one is a human call.

1. Confirm or reject the Hat Yai join to `FL-2025-000210-THA`.
2. Choose `data.demo_event`. The fixture districts still resolve. The new observed polygons also cover Hat Yai, Phayao, Doi Tao, and Chaiyaphum / Nakhon Ratchasima, and the live 7-day counts sit on the central plain.
3. Decide whether Hat Yai District should be added even though its centre lost the cap of 50. The EOS-RS polygon is stored either way; a caller who says "Hat Yai" does not match a district row today.
4. Decide whether to download central-plain GISTDA pages. The counts are in `data/SOURCES.md`. Storing a thin sample would paint a false flood edge.
5. Decide whether a GDACS refresh outside 05:00–07:45 Europe/London should keep waiting. The client already refuses. Do not loosen it.
6. Put `GISTDA_API_KEY` in `.env` on any machine that will refresh. It is not in git.
7. Read `research/triage-philosophy.md` before editing `config/escalation.yaml`. The note's extra triggers (a child alone, oxygen, "we can't climb") are proposals, not changes.
8. Do not hardcode a relief-payment amount. `research/thai-flood-management.md` stops at the Act on purpose.

## 4. Blockers needing a human

**GISTDA key on a new machine.** This ingest used a key from the gitignored `.env`. The key was not written to SQLite, cache metadata, or the report. Another checkout needs its own `GISTDA_API_KEY` before `make ingest-refresh` can refresh the feature API. Registration: https://api-gateway.gistda.or.th and https://api-gateway.gistda.or.th/v2. Catalogue: https://opendata.gistda.or.th/dataset/flood-disaster-data. Contact: disaster@gistda.or.th.

**GDACS clock.** `https://www.gdacs.org/robots.txt` sets `Request-rate: 1/60` and `Visit-time: 0400-0645` UTC, which is 05:00–07:45 Europe/London. The client fails closed if that file cannot be read. A refresh outside the window does not delete rows already stored.

**ReliefWeb** stays retired unless a human accepts both the robots disallow on `/v2/` and an approved `appname`. Do not bypass the robots rule.

**Open-Meteo robots.txt** is a blanket `Disallow: /` on the API hosts. Calls happened only because of the config flag above. Confirm or revoke that.

**Hat Yai District is absent** from the 50 district rows. Southern centres that did fit are Khok Pho, Krasae Sin, Nong Chik, Ranot, and Thepha. The flood polygon is still in `flood_extent`.

**DDPM, TMD's registered warning API, RID reservoir levels, WorldPop, HDX admin boundaries, and a live CAP feed** were not fetched. Reasons are in `research/INDEX.md` under "Other context worth getting".

## 5. Open change requests

None. `contracts/CHANGE_REQUESTS.md` is empty. Contracts stay at `v0.1-contracts` until a human accepts a proposal.

## 6. Integration point

Saturday 19:00. Both `S1_IMPL=real` and `S2_IMPL=real`, with `MEMORY_IMPL=mubit`. Contracts stay frozen at the latest tag until then.
