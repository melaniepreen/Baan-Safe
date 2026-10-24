---
title: Country packs
tags: [country, locale, hotline, gazetteer, thailand]
files:
  - countries/TEMPLATE/pack.yaml
  - countries/TEMPLATE/providers.yaml
  - countries/TEMPLATE/policy-pack.yaml
  - countries/TEMPLATE/system1_labels.yaml
  - countries/th/pack.yaml
  - countries/ph/pack.yaml
  - countries/ph/policy-pack.yaml
  - countries/ph/system1_labels.yaml
---

## Purpose

Country packs are an unloaded description of how BaanSafe would bind locale, hotlines, a triage scale, a gazetteer, data providers, and an aid corpus for one country. Thailand stays the default and the demo. `countries/th/pack.yaml` records that setup. `countries/ph/` is a worked example for the Philippines. Nothing under `countries/` is imported.

The inventory below has **48** Thailand-specific assumptions. Each row is one hardcoded choice, with the line that owns it. Memory (`memory/adapter.py`) and the Mubit client (`llm/client.py`) have no country branch. The gateway chooser (`gateway/chooser.py`) only evaluates `config/escalation.yaml`. Police **191** and fire **199** are real public codes and are **not** in the runtime. They are in the Thailand pack as verified, unwired numbers.

## Key files

- `countries/TEMPLATE/pack.yaml` — commented schema.
- `countries/TEMPLATE/providers.yaml` — one interface per capability, plus global fallbacks.
- `countries/TEMPLATE/policy-pack.yaml` — Sphere and IFRC baseline, empty national slots.
- `countries/TEMPLATE/system1_labels.yaml` — hypothesis shape, one sentence per language.
- `countries/th/pack.yaml` — today's Thailand, `runtime: unloaded`, `default_demo: true`.
- `countries/ph/pack.yaml` — Philippines example. `countries/ph/policy-pack.yaml` and `countries/ph/system1_labels.yaml` fill the template.
- `policies/corpus.py` — the loaded corpus. It does not read `countries/`.
- `system1/extract.py` — English keywords and the district gazetteer.
- `ingest/admin_districts.py`, `ingest/gistda.py`, `ingest/thaiwater.py`, `ingest/open_meteo.py`, `ingest/gdacs.py`, `ingest/hdx.py`, `ingest/overpass.py` — Thailand data clients.

### Assumptions

| # | Assumption | Where |
|---|---|---|
| 1 | Public medical entry is telephone 1669. The router does not dial it. | `policies/triage.yaml:105` |
| 2 | The town suggestion names 1784 and 1567. The router does not dial them. | `ui/sim/data/responses.json:11` |
| 3 | Triage colours are the five NIEM names (red, yellow, green, white, black). | `policies/triage.yaml:28` |
| 4 | A second five-code description comes from one Khon Kaen hospital study. | `policies/triage.yaml:132` |
| 5 | No retrieved rule gives a flood depth or a 1669 colour for a trapped caller. | `policies/triage.yaml:247` |
| 6 | P1–P4 text is a human judgement, not the NIEM scale, and it is not executed. | `config/priorities.yaml:3` |
| 7 | `decide()` maps needs to P2–P4 and never reads a colour. | `system1/decide.py:19` |
| 8 | The national aid file is the Ministry of Finance criteria, B.E. 2569. | `policies/mof_relief.yaml:19` |
| 9 | That filename is jurisdiction `TH`. Sphere and IFRC are `intl`. | `policies/sources/local_yaml.py:36` |
| 10 | The B.E. 2569 date stays text. It is not turned into a Gregorian ISO date. | `policies/sources/local_yaml.py:62` |
| 11 | The corpus states baht. The aid check does not read an amount. | `policies/mof_relief.yaml:121`, `system1/aid_eligibility.py:4` |
| 12 | Some farm caps are in rai. No conversion is stored. | `policies/mof_relief.yaml:596` |
| 13 | Prototype pages format a baht sign. Those figures are simulated. | `frontend-prototype/v3/index.html:274` |
| 14 | The fast path is English-only. | `system1/extract.py:4` |
| 15 | Tokens are `[a-z']+`, so Thai script cannot match. | `system1/extract.py:20` |
| 16 | The only Thai place word in the water patterns is `soi`. | `system1/extract.py:118` |
| 17 | Counts and confirmations are English number words and yes/yeah/correct. | `system1/extract.py:180`, `system1/extract.py:204` |
| 18 | Policy languages are `en` and `th` only. | `policies/schema.py:9` |
| 19 | A training language is `th`, `en`, or `mixed`. | `contracts/training.py:28` |
| 20 | Thai text is detected as the Unicode block U+0E00–U+0E7F. | `policies/sources/local_yaml.py:44` |
| 21 | Sapling refuses non-English while `sapling.thai_handling` is unset. | `system2/sapling_client.py:199`, `config/decisions.yaml:19` |
| 22 | Speech-to-text defaults the language form to `th`. | `infra/modal/stt_app.py:62` |
| 23 | Label hypotheses already have a Thai sentence beside the English one. | `policies/system1_labels.yaml:12` |
| 24 | The town draws with Noto Sans Thai and speaks a Thai line under English. | `ui/sim/sim.js:532`, `ui/sim/README.md:51` |
| 25 | One `group_id` keeps the Thai and English of the same call together. | `docs/agents/training-schema.md:35` |
| 26 | The gazetteer is OSM `admin_level` 6 inside `ISO3166-2=TH-{code}`. Tambon (`admin_level` 8) is not stored. | `ingest/admin_districts.py:51` |
| 27 | Eight province codes and English names are hardcoded (Chiang Mai through Songkhla). | `config/ingest.yaml:42`, `ingest/admin_districts.py:26` |
| 28 | A hit is formatted `Name, Province`, and the suffix ` Province` is stripped when matching. | `system1/extract.py:337` |
| 29 | Enrichment matches `name_th` as well as `name_en`. The column exists on both district tables. | `enrich/context.py:93`, `ingest/db.py:74` |
| 30 | Phone redaction is `+66` or a leading `0`. | `scripts/validate.py:28`, `ingest/textutil.py:9` |
| 31 | A 13-digit run is a national id. The token PromptPay is banned in fixtures. | `scripts/validate.py:29` |
| 32 | Flood polygons come from the GISTDA feature API and MapServer, filtered by `pv_idn`. | `ingest/gistda.py:22` |
| 33 | A ThaiWater gauge is the 24-hour rain total. Open-Meteo is the fallback. | `ingest/thaiwater.py:21`, `enrich/context.py:67` |
| 34 | "Today" and the weather timezone are `Asia/Bangkok`. | `ingest/open_meteo.py:26` |
| 35 | Rain flags are millimetres per 24 hours. Wind is requested in km/h. | `config/escalation.yaml:24`, `ingest/open_meteo.py:127` |
| 36 | District and gauge match radii are 25 km. The flood buffer flag is 500 m. | `config/ingest.yaml:24`, `config/escalation.yaml:26` |
| 37 | GDACS is queried as `country=THA` for August–December 2025. | `ingest/gdacs.py:25` |
| 38 | HDX search is the string `thailand flood`, plus three Thai dataset ids (GLIDE, IDMC, Hat Yai). | `ingest/hdx.py:86`, `ingest/hdx.py:44` |
| 39 | Flood-cluster districts are also OSM `admin_level` 6. | `ingest/overpass.py:140` |
| 40 | A country-sized ring is described as half of Thailand. | `config/ingest.yaml:50` |
| 41 | Fixtures speak northern district names (Mae Mo, Lampang, and the same set). | `fixtures/scenarios/F01.json:87` |
| 42 | Rescue fans out to a boat, and the sample boats sit in those districts. | `router/merge.py:27`, `mocks/resources.json:7` |
| 43 | A resource matches when its district is a substring of the location string. | `router/merge.py:138` |
| 44 | The town is a Bangkok flood placeholder, not a fetched map. | `ui/sim/README.md:35` |
| 45 | Street names are marked with the Thai word for placeholder. | `ui/sim/README.md:47` |
| 46 | A household has a district label and no country field. | `contracts/models.py:203` |
| 47 | The loaded corpus is four YAML files. ReliefWeb and DDPM hosts are refused. | `policies/corpus.py:20`, `policies/corpus.py:37` |
| 48 | Town copy sends information questions to TMD, RID, and GISTDA. | `ui/sim/data/responses.json:26` |

## Interfaces/contracts

A pack is YAML with `schema_version: baansafe.country_pack.v0` and `runtime: unloaded`. Required blocks are `locale`, `hotlines`, `triage_scale`, `admin`, `providers`, `aid_policy_corpus`, and `system1_labels`. The provider file's capabilities are `flood_extent`, `rain_and_forecast`, `river_levels`, `shelters_and_facilities`, `boundaries`, and `stt_asr`.

Global fallbacks, each with a retrieved URL in `countries/TEMPLATE/providers.yaml`:

- Flood extent: Copernicus EMS rapid mapping. GloFAS is a forecast, not an extent.
- Rain: Open-Meteo forecast and archive.
- Rivers: GloFAS discharge forecast when the country has no gauge feed.
- Facilities: the Overpass interpreter already in `config/ingest.yaml`, or the HOT Export Tool.
- Boundaries: geoBoundaries `gbOpen` metadata, or the country's HDX COD-AB dataset.
- Speech: Whisper (faster-whisper is already the optional app). FLEURS is the eval set, not a transcriber.

A policy pack keeps Sphere (`policies/sphere.yaml`) and IFRC (`policies/safeguarding.yaml`) and leaves a national triage slot and a national aid slot. `status` is `verified` or `unverified`. A verified row has a `source_url` that was opened. A missing number stays null.

System 1 hypotheses are one full sentence per language. `quotation: true` only when the sentence is copied. The demo hypotheses stay in `policies/system1_labels.yaml`. The Philippines file is a draft in English and Filipino.

`gateway/chooser.py` and `router/merge.py` do not grow a country argument in this change. Priorities stay P1–P4.

## Invariants

- Thailand is the demo. `countries/th/pack.yaml` has `default_demo: true`. Any other pack has `default_demo: false`.
- `runtime` stays `unloaded` until the refactor below is actually coded. A pack must not be imported from `gateway/`, `system1/`, `ingest/`, or `policies/`.
- Do not invent a hotline, an endpoint, a millimetre cut, or a payment amount. `unverified` plus null is the honest row.
- Do not fetch ReliefWeb. Do not add DDPM, `disaster.go.th`, or `ddpm.go.th` as a source. The 1784 row cites the PRD article only.
- Synthetic people only. A pack stores short public codes, not a subscriber number, a national id, or a payment identifier.
- Do not copy a baht or peso figure out of a prototype or out of memory into a rule.
- OSM `admin_level` 6 is an amphoe in Thailand and a city or municipality in the Philippines. Do not reuse the Thai query unchanged.
- The loaded corpus stays `policies/*.yaml`. A new country's rules live under `countries/<iso2>/` until a human adds an adapter.
- `make test` and `make validate` stay green without editing fixtures, tests, or `frontend-prototype/`.

## How to test

This change is data and a doc. Confirm the YAML parses, then run the repo check:

```bash
python3 -c '
import yaml
from pathlib import Path
root = Path("countries")
files = sorted(root.rglob("*.yaml"))
assert files, "no country yaml"
for path in files:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} is not a mapping")
    print(f"ok {path}")
'
make validate
```

`make validate` does not read `countries/`. It does check this doc's front matter and the index entry. `make test` is unchanged.

### Checklist for a new country

Do this after the hackathon, when editing code is allowed. Until the refactor lands, stop at step 4. A new directory under `countries/` still changes nothing at runtime.

1. Copy `countries/TEMPLATE/` to `countries/<iso2>/`. Set `iso2`, `iso3`, `default_demo: false`, and `runtime: unloaded`.
2. Fill `locale`. Cite a page for the timezone, the currency, and the phone pattern. Leave a field unverified if the page was not opened. Do not reuse `+66` or the 13-digit rule.
3. Hotlines. Open the national emergency page and the telecom numbering list. One short code per service. Quote the agency name as printed. Set `wired: false`. If two official pages disagree, keep both notes and do not pick a winner in code.
4. Triage and aid. Retrieve the national scale and the assistance instrument. Record `source_excerpt` only from that page. Map onto P1–P4 only as `mapping_status: unverified` unless the document names those priorities. Point the baseline at `policies/sphere.yaml` and `policies/safeguarding.yaml`. Leave the aid slot empty rather than invent a ceiling.
5. Admin levels. Read the OSM wiki page for that country and the HDX COD-AB dataset page. Record `osm_admin_level` separately from the COD-AB level. Pick `gazetteer.grain`. Do not assume Thailand's level 6.
6. Providers. For each capability, either cite a national endpoint you opened or set `national: null` and name a global fallback from `countries/TEMPLATE/providers.yaml`. A product page is not an API. A forecast is not an extent.
7. Labels. Write one hypothesis sentence per language in `system1_labels.yaml`. Mark drafts `quotation: false`. Do not translate a statute you did not read.
8. Verify. Re-fetch every URL. Flip a row to `unverified` when the page moved. Parse the YAML with the command above.
9. Tests to add with the loader, not before it. A pack that is not imported cannot fail a test, and a test that imports it will fail today.
   - The loader returns Thailand when no country is set, and the result matches today's extract on the existing fixtures.
   - An unknown `iso2` raises, naming the code.
   - A hotline with `status: unverified` is not copied into a dispatch.
   - `admin_level` 6 for `ph` is not queried with `ISO3166-2=TH-`.
   - The personal-data scan still rejects a Thai-shaped number in a fixture, and it also rejects the new country's pattern.
   - `policies/corpus.py` still refuses a ReliefWeb or DDPM URL.
   - `make test` and `make validate` stay green. Do not edit `frontend-prototype/`.

## Common pitfalls

- Treating `countries/th/pack.yaml` as config the gateway already reads. It does not.
- Copying the Thai Overpass query into another country because the admin level number matches.
- Filling a millimetre threshold from a news article when the agency page did not print one. The Philippines pack leaves those cuts out on purpose.
- Putting a DDPM or ReliefWeb URL in a policy row. `policies/corpus.py` rejects those hosts, and the project rule is the same.
- Storing an office trunk line. Short public codes only.
- Editing `policies/mof_relief.yaml` or `system1/extract.py` while "only adding a country". That is the refactor, and it waits.
- Letting a prototype baht figure become an aid rule.

## Open TODO_HUMAN keys

No decision in `config/decisions.yaml` was changed. These stay unset, and a pack does not fill them:

- `sapling.thai_handling`
- `speech_to_text.provider`
- `modal.stt_model_id`
- `data.demo_event`
- `policies.authoritative_set`

## Refactor proposal

For after the hackathon. The list is the smallest set of code changes that would let a pack load. Thailand must remain the default path, and the existing fixtures must keep their labels. Do not do these in a docs-only change.

The first five are the ones to do before any other country can affect a call.

1. **No country on the request path.** `config/settings.py:20` reads only `config/<name>`. `gateway/route.py:143` calls `extract` with the transcript and no country. `contracts/models.py:203` has a district label and no country. Add an optional country code with default `th`, and a loader that is not called until a later step. Effort: small for the dormant loader, medium to thread it through the gateway. Risk: medium on the hot path, high if the contract field is required. Leave the field off the contract until a human accepts a schema change.
2. **Extractor, language, and gazetteer.** `system1/extract.py:20` keeps Latin tokens, `:279` reads `admin_districts`, and `:337` builds `Name, Province`. A pack-driven phrase list has to reproduce today's English table on the current fixtures before it accepts another language. Effort: medium. Risk: high. Fixture labels move if a phrase shifts.
3. **Ingest providers, clock, and admin level.** The Thailand clients are `ingest/open_meteo.py:26` (`Asia/Bangkok`), `ingest/gistda.py:22`, `ingest/thaiwater.py:21`, `ingest/gdacs.py:25` (`country=THA`), `ingest/hdx.py:86` (`thailand flood`), `ingest/admin_districts.py:51` (`TH-{code}` and `admin_level` 6), and `config/ingest.yaml:42` (eight province codes). A registry should call today's functions for `th` and refuse a national URL that is `unverified`. Effort: large. Risk: high. These clients write SQLite and honour robots rules.
4. **Policy jurisdiction, languages, and the file list.** `policies/schema.py:8` allows only `TH` and `intl`. `policies/schema.py:9` allows only `en` and `th`. `policies/sources/local_yaml.py:35` maps jurisdiction by filename. `policies/corpus.py:20` lists four files. Add a country by a new adapter pointed at `countries/<iso2>/policy-pack.yaml`. Do not move the Thailand YAML. The corpus hash is the file bytes. Effort: medium. Risk: high.
5. **Personal-data scanners.** `scripts/validate.py:28` and `ingest/textutil.py:9` know `+66` and a leading `0`. `scripts/validate.py:29` treats 13 digits as an id. A new pattern is added beside the Thai one, not instead of it. Effort: small. Risk: medium. A looser pattern lets a real number through. A narrower one misses a Thai number.

Later, still after the hackathon, and only once the five above keep the Thai fixtures green:

- Speech default. `infra/modal/stt_app.py:62` posts `language=th`. Read the pack language only when the request omitted one. Effort: small. Risk: low if the default stays `th`. `modal.stt_model_id` stays `TODO_HUMAN`.
- Sapling language gate. `system2/sapling_client.py:199` refuses non-English. Do not send another language until `sapling.thai_handling` is decided. Effort: small. Risk: high if the gate is removed.
- Router district match. `router/merge.py:138` uses a substring of the location string, and `:27` sends rescue to a boat. Boats are a resource kind for this flood demo, not a national rule. Effort: small. Risk: medium if the location format changes.
- Enrichment thresholds. `config/escalation.yaml:24` flags 30 mm in 24 hours for every caller. A pack may name a different flag later. It must not change the Thai flag in the same change. Effort: small. Risk: medium.
