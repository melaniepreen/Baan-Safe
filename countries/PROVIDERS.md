# Provider interface

One capability, one shape. A country pack names a national provider or leaves it null, then names which global fallback it accepts. The retrieved URLs, the date, and the status live in `countries/TEMPLATE/providers.yaml` (`schema_version: baansafe.provider_interface.v0`, retrieved 2026-10-24). This note is the contract. That file is the citation list. Do not add a host that file does not list without opening a new page. Do not fetch ReliefWeb. Do not add DDPM as a source.

A client that does not exist yet would return `capability`, `observed_at`, `geometry`, `value`, `unit`, `label`, `source_id`, `licence`, and `fresh`. Missing data is null, the same way `enrich/context.py` already behaves. `label` is a source label, not a priority.

## flood_extent

Observed water on the ground, as a polygon, for a point. Inputs are lat, lon, and time. A forecast is not an extent.

National slot: the country's own extent service. Thailand uses GISTDA (`ingest/gistda.py`). Status of that client: it already runs. It is not a global fallback.

Global fallbacks in the provider file:

- Copernicus EMS rapid mapping. The harvest page documents activation details. The activation code is a Copernicus id, not a country code. Activations exist only where an authorised user requested mapping. The pack does not call the URL.
- GloFAS is listed here only to say it is a forecast, not an extent. Do not store a forecast raster as a flood polygon.

## rain_and_forecast

Observed precipitation and a short forecast at a point. Unit is millimetres. Inputs include the pack timezone. The 30 mm / 24 h flag in `config/escalation.yaml` is a starting number, not a universal rule.

Global fallback: Open-Meteo forecast `https://api.open-meteo.com/v1/forecast` and archive `https://archive-api.open-meteo.com/v1/archive`, documented at <https://open-meteo.com/en/docs>. The existing client is `ingest/open_meteo.py`. It sends `Asia/Bangkok`. A new country does not get a second client in this change. The robots exception in `config/ingest.yaml` stays as it is.

## river_levels

A measured gauge near the caller. Thailand uses the public ThaiWater JSON (`ingest/thaiwater.py`). That scale is Thailand's. Level 1 is critically low, not a flood class. Do not reuse the numbers.

Global fallback: GloFAS discharge forecast, same data-and-services page as above. It is not an observed-gauge network. There is no global observed-gauge endpoint in this spec. A dataset id was not copied.

## shelters_and_facilities

Candidate shelters and clinical sites. Today's enricher uses OSM types hospital, clinic, school, place_of_worship, and community_centre. A pack may add types. It may not rank them as the dispatch.

Global fallbacks:

- Overpass at the interpreter already in `config/ingest.yaml`: `https://overpass.openstreetmap.fr/api/interpreter`. `overpass-api.de` is not used. Licence is ODbL.
- HOT Export Tool, <https://export.hotosm.org/v3>. The product page says an API exists. No API path was copied. An export needs an OSM account.

## boundaries

Admin polygons and names. The grain comes from the pack. Thailand asks OSM for `admin_level` 6 inside a province and does not load a tambon table. Another country confirms its own integers. The Philippines must not reuse the Thai query.

Global fallbacks:

- geoBoundaries metadata, <https://www.geoboundaries.org/api.html>. One documented pattern: `https://www.geoboundaries.org/api/current/[RELEASE-TYPE]/[ISO3]/[BOUNDARY-TYPE]/`. `gbOpen` is the CC-BY line they recommend. Boundary type is `ADM0`–`ADM5` or `ALL`. The JSON returns a download path. It does not return a priority.
- HDX COD-AB. It is a per-country dataset. Cite the country page that was opened. Thailand's page is <https://data.humdata.org/dataset/cod-ab-tha>. The catalogue search is not that dataset. CKAN `package_search` is the API the HDX client already uses.

## stt_asr

Audio in, text and language out. The model id stays `modal.stt_model_id`, which is `TODO_HUMAN`.

Global fallbacks:

- Whisper, via faster-whisper, which `infra/modal/stt_app.py` already optional-loads. The form language defaults to `th`. A pack language is an argument, not a new model. <https://github.com/openai/whisper>.
- FLEURS, <https://huggingface.co/datasets/google/fleurs>, is an evaluation set, not a transcriber. The card's South-East Asia group names Thai and Filipino. The config id was not copied. Read it from the dataset card before a loader uses it.

## What a pack stores

A national row is `verified` only with a `source_url` that was opened. Otherwise `national: null` and `status: unverified`. `exercised` code is the Thailand client where one exists. A documented fallback is not permission to call it from a pack file. The later loader is `countries/REFACTOR_PROPOSAL.md`.
