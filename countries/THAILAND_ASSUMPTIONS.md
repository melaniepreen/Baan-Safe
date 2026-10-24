# Thailand assumptions

Counted assumptions: **49**. Each item is one choice the running tree hardcodes for Thailand. The line is where that choice sits on `main` after the flood-rule and graduation commits. Nothing in `countries/` is loaded, so editing a pack does not move these lines.

Police **191** and fire **199** are not in this count. They are not in the runtime, the corpus, or the town. `countries/th/pack.yaml` records them as verified public codes, unwired, with the scope disagreement on 199 (government list versus the NBTC Bangkok fire-police row). Memory (`memory/adapter.py`) and the Mubit client (`llm/client.py`) have no country branch. `gateway/chooser.py` only evaluates `config/escalation.yaml`.

## Hotlines and the colour scale

1. The public medical entry is telephone 1669. The router does not dial it. `policies/triage.yaml:119` (`NIEMS-1669-PATH`).
2. The town suggestion names 1784 and 1567. The router does not dial them. `ui/sim/data/responses.json:11`. The pack cites the August 2024 PRD article for those digits and does not store a `disaster.go.th` URL.
3. Triage colours are the five NIEM names, and the Royal Gazette announcement of B.E. 2554 names the same five symbols. `policies/triage.yaml:42`, `policies/triage.yaml:129` (`NIEMS-ANNOUNCEMENT-2554`, verified).
4. A second five-code description comes from one Khon Kaen hospital study. `policies/triage.yaml:161`. Its black code is a false call. The slide's black is "no patient".
5. International pages print flood depths, including 6, 12, and 18 inches. None of them is a 1669 colour. The B.E. 2554 announcement does not map a trapped caller to a colour. `policies/flood.yaml:92`, `policies/triage.yaml:287`.
6. P1–P4 text is a human judgement, not the NIEM scale, and it is not executed as the colour table. `config/priorities.yaml:4`.
7. `decide()` maps needs to P2–P4 and never reads a colour. `system1/decide.py:23`.

## Aid, language, script

8. The national aid file is the Ministry of Finance criteria, B.E. 2569. `policies/mof_relief.yaml:19`.
9. That filename is jurisdiction `TH`. Sphere, IFRC, and `flood.yaml` are `intl`. `policies/sources/local_yaml.py:36`, `policies/sources/local_yaml.py:40`.
10. The B.E. 2569 date stays text. It is not turned into a Gregorian ISO date. `policies/sources/local_yaml.py:63`.
11. The corpus states baht. The aid check does not read an amount. `policies/mof_relief.yaml:121`, `system1/aid_eligibility.py:4`.
12. Some farm caps are in rai. No conversion is stored. `policies/mof_relief.yaml:596`.
13. Prototype pages format a baht sign. Those figures are simulated. `frontend-prototype/v3/index.html:274`. Do not copy one into a pack.
14. The fast path is English-only. `system1/extract.py:3`.
15. Tokens are `[a-z']+`, so Thai script cannot match. `system1/extract.py:20`.
16. The only Thai place word in the water patterns is `soi`. `system1/extract.py:118`.
17. Counts and confirmations are English number words and yes/yeah/correct. `system1/extract.py:180`, `system1/extract.py:204`.
18. Policy languages are `en` and `th` only. `policies/schema.py:9`.
19. A training language is `th`, `en`, or `mixed`. `contracts/training.py:28`.
20. Thai text is detected as the Unicode block U+0E00–U+0E7F. `policies/sources/local_yaml.py:46`.
21. Sapling refuses non-English while `sapling.thai_handling` is unset. `system2/sapling_client.py:199`, `config/decisions.yaml:21`.
22. Speech-to-text defaults the language form to `th`. `infra/modal/stt_app.py:62`.
23. Label hypotheses already have a Thai sentence beside the English one. `policies/system1_labels.yaml:12`.
24. The town draws with Noto Sans Thai and speaks a Thai line under English. `ui/sim/sim.js:533`, `ui/sim/README.md:51`.
25. One `group_id` keeps the Thai and English of the same call together. `docs/agents/training-schema.md:35`.

## Admin, identifiers, data

26. The gazetteer is OSM `admin_level` 6 inside `ISO3166-2=TH-{code}`. Tambon (`admin_level` 8) is not stored. `ingest/admin_districts.py:51`.
27. Eight province codes and English names are hardcoded (Chiang Mai through Songkhla). `config/ingest.yaml:42`, `ingest/admin_districts.py:26`.
28. A hit is formatted `Name, Province`, and the suffix ` Province` is stripped when matching. `system1/extract.py:337`.
29. Enrichment matches `name_th` as well as `name_en`. The column exists on both district tables. `enrich/context.py:93`, `ingest/db.py:74`.
30. Phone redaction is `+66` or a leading `0`. `scripts/validate.py:28`, `ingest/textutil.py:9`.
31. A 13-digit run is a national id. The token PromptPay is banned in fixtures. `scripts/validate.py:29`.
32. Flood polygons come from the GISTDA feature API and MapServer, filtered by `pv_idn`. `ingest/gistda.py:22`.
33. A ThaiWater gauge is the 24-hour rain total. Open-Meteo is the fallback. `ingest/thaiwater.py:21`, `enrich/context.py:67`. Level 5 on that feed is over bank. Level 1 is critically low.
34. "Today" and the weather timezone are `Asia/Bangkok`. `ingest/open_meteo.py:26`. Case stamps in the gateway stay UTC.
35. Rain flags are millimetres per 24 hours. Wind is requested in km/h. `config/escalation.yaml:32`, `ingest/open_meteo.py:127`.
36. District and gauge match radii are 25 km. The flood buffer flag is 500 m. `config/ingest.yaml:24`, `config/escalation.yaml:34`.
37. GDACS is queried as `country=THA` for August–December 2025. `ingest/gdacs.py:25`.
38. HDX search is the string `thailand flood`, plus three Thai dataset ids (GLIDE, IDMC, Hat Yai). `ingest/hdx.py:86`, `ingest/hdx.py:44`.
39. Flood-cluster districts are also OSM `admin_level` 6. `ingest/overpass.py:140`.
40. A country-sized ring is described as half of Thailand. `config/ingest.yaml:50`.
41. Fixtures speak northern district names (Mae Mo, Lampang, and the same set). `fixtures/scenarios/F01.json:87`.
42. Rescue fans out to a boat, and the sample boats sit in those districts. `router/merge.py:27`, `mocks/resources.json:7`.
43. A resource matches when its district is a substring of the location string. `router/merge.py:144`.
44. The town is a Bangkok flood placeholder, not a fetched map. `ui/sim/README.md:35`.
45. Street names are marked with the Thai word for placeholder. `ui/sim/README.md:47`.
46. A household has a district label and no country field. `contracts/models.py:203`.
47. The loaded corpus is five YAML files. `flood.yaml` is jurisdiction `intl`. ReliefWeb and DDPM hosts are refused. `policies/corpus.py:20`, `policies/sources/local_yaml.py:40`, `policies/corpus.py:38`.
48. Town copy sends information questions to TMD, RID, and GISTDA. `ui/sim/data/responses.json:26`.
49. The only labels that can graduate a pattern into System 2 include the NIEMS colour and flood labels. `config/escalation.yaml:19`. Graduation does not set a priority.
