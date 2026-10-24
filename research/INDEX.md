# Research index

Notes for Moly and Melanie before Phase 1. They are background, not product rules. Nothing here changes `config/decisions.yaml`, the escalation thresholds, or the stub outcomes. Short quotes only. Sources are linked at the bottom of each note.

| File | What it is |
|---|---|
| `research/thai-flood-management.md` | Who does what in a Thai flood: DDPM, RID, the water command, TMD, GISTDA, 1784, provinces and local government, and the 2007 Act. |
| `research/international-practice.md` | Sendai, the IASC cluster system, Sphere water/shelter/food figures, and CAP alerts. |
| `research/triage-philosophy.md` | Phone triage, START/SALT, vulnerability, human sign-off, and how that sits next to Priority / Route / escalation. Suggestions only. |
| `research/lessons-thai-floods.md` | What 2011 and Hat Yai in November 2025 imply for a call-taker. |
| `research/glossary-and-risk-areas.md` | Thai and English flood words, caller phrases, and provinces that show up in the public records we actually hold. |
| `research/MUBIT.md` | Public Mubit docs: gateway, SDK, memory, learning loop, adapters. Thin on a correction-to-LoRA API. |
| `research/MODELS.md` | Sapling is the selected verifier. Nemotron, Thai extraction, speech, and embeddings are still options. |
| `research/PAPERS.md` | Annotated links: call triage, crisis tweets, fast/slow systems, routing, LoRA, human corrections, floods. |
| `research/DATASETS.md` | Labelled sets and their licences. HumAID, CrisisLex, LST20. No public emergency-call audio. |
| `research/DEMO_PLAN.md` | Three-beat demo, the four judging criteria, track options, 12:00 and 12:00–18:00 check-ins, A/B tasks, 19:00. |

## Other context worth getting

Not fetched in this run, and why.

- **DDPM situation reports.** The owner said not to add DDPM as a source in this run. They are the operational narrative (which provinces, what was ordered) and would be the best official twin to a GLIDE id. A human has to decide the terms before anyone scrapes `disaster.go.th`.
- **Current relief-payment amounts.** The Act allows assistance, but the baht figures are set by regulation and cabinet decisions and they move. Do not hardcode a number from an old flood. Ask DDPM which criteria are in force.
- **TMD warning feed.** Official rain and warning areas. Registration is at `https://data.tmd.go.th/api/`. We used Open-Meteo and ThaiWater gauges instead.
- **RID reservoir API.** Daily public storage at `https://app.rid.go.th/reservoir/api/reservoir/public`. Useful when a release, not local rain, is what is flooding the caller. Not called this run.
- **WorldPop.** Counts of people near a polygon. Marked later in `data/SOURCES.md`. Needed before anyone treats a UNOSAT "people exposed" sentence as our own.
- **HDX admin boundaries (COD-AB).** We still match a district by the nearest `admin_level=6` centre within 25 km, not by a boundary intersection. A boundary set would fix that. Human to approve.
- **Larger UNOSAT shapefiles.** Several CC BY-SA water extents are over the 20 MB shapefile cap (Chiang Mai–Lamphun 2024, Chiang Rai 2024, the 2021 central and northeast series). They are listed as candidates in `data/SOURCES.md`.
- **Other EOS-RS bundles.** Bangkok September 2026 and the November 2024 southern maps are CC BY and were not unpacked. Hat Yai November 2025 was.
- **ReliefWeb.** Retired. `robots.txt` disallows `/v2/`, and an approved `appname` is required. Do not bypass the robots rule.
- **Full GISTDA repeat-flood layer.** The frequency service reports millions of polygons. We store a per-province cap. A national layer does not belong in git.
- **A live CAP feed.** If TMD or DDPM publishes Common Alerting Protocol alerts, that is the warning text System 1 should point at. We do not have that feed.
- **`data.demo_event`.** Still `TODO_HUMAN`. Fixtures talk about Lampang, Phrae, Nan, and Phayao. The new observed polygons also include Hat Yai. Picking the demo event is a human decision.
- **Mubit project, retrieval budget, the route chooser, the auth scheme, speech-to-text, UI framework, production database, graduation threshold, token price.** Still unset in `config/decisions.yaml`. What the public docs do say is in `research/MUBIT.md`.
