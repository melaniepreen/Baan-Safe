# Policy sources

Retrieved 24 October 2026. Rule text is in `policies/*.yaml`. The service in `policies/service.py` loads that text through a source adapter (`fetch`, `normalise`, `version`). `local_yaml` is the only live adapter. Sapling and System 1 read the service, which is also exposed as `GET /policies`, `GET /policies/{rule_id}`, `POST /policies/match`, and `GET /policies/labels`.

An eval run pins the corpus with `POST /policies/pins` and a `run_id`. Later reads pass that `version` or `run_id`. A version that is not the loaded corpus and not a stored pin is rejected. The pin files live under `var/policy-pins/` and are not committed.

Each rule has an id, English plain language, Thai where the source is in Thai, a source URL, an excerpt, a retrieved date, and a licence note. The service also records jurisdiction (`TH` or `intl`), domain (`aid_eligibility`, `safeguarding`, or `triage`), and any effective date the source itself states. The B.E. 2569 instrument date is kept as the words in clause 2. It is not converted into a Gregorian ISO date.

`policies.authoritative_set` in `config/decisions.yaml` is `TODO_HUMAN`. Loading a rule by id does not make it the demo's authority. A human chooses that set.

ReliefWeb was not used. DDPM (`disaster.go.th`) was not used. No personal data and no account numbers are stored. Examples in tests use synthetic household ids only.

The PDF text layer of the Ministry of Finance criteria often prints `ไม,เกิน` for `ไม่เกิน`. Verified baht digits are the Thai digits that extracted cleanly. A Latin `1` sitting between Thai digits was not converted into a number.

## Sources

| id | document | url | retrieved | licence |
|---|---|---|---|---|
| MOF-2569 | หลักเกณฑ์ วิธีการ เงื่อนไข การใช้จ่ายเงินทดรองราชการเพื่อช่วยเหลือผู้ประสบภัยพิบัติกรณีฉุกเฉิน พ.ศ. 2569, hosted by the Department of Agricultural Extension | https://plan.doae.go.th/wp-content/uploads/2026/04/หลักเกณฑ์-ปี-69.pdf | 2026-10-24 | Official instrument. Thai Copyright Act B.E. 2537 section 7 excludes regulations, announcements and orders of state agencies from copyright. Confirm that reading before reuse beyond this corpus. |
| SPHERE-2018 | Sphere Handbook, fourth edition, 2018 | https://spherestandards.org/wp-content/uploads/Sphere-Handbook-2018-EN.pdf | 2026-10-24 | © Sphere Association, 2018 (CHS portions also © CHS Alliance, Sphere Association and Groupe URD, 2018). Reproducible without fee for education, training, research and programme use with acknowledgement. Not for resale. Other reuse needs written permission from info@spherestandards.org. The live URL returned HTTP 403. Wording was read from the Internet Archive capture of 27 December 2024 of that same file. |
| IFRC-PGI-2018 | Minimum standards for protection, gender and inclusion in emergencies | https://www.ifrc.org/sites/default/files/Minimum-standards-for-protection-gender-and-inclusion-in-emergencies-LR.pdf | 2026-10-24 | © IFRC, Geneva, 2018. Noncommercial copies with acknowledgement. Commercial reproduction via secretariat@ifrc.org. |
| UNHCR-PAR | Emergency Handbook, Overview of persons at risk | https://emergency.unhcr.org/protection/persons-risk/overview-persons-risk | 2026-10-24 | No redistribution licence on the page. Short quotation. The page says the entry is outdated and under revision, last updated 21 January 2026. |
| NIEM-2013-SLIDES | NIEM slides hosted by NSTDA, citing the กพฉ emergency-level announcement | https://www.nstda.or.th/nac/2013/download/presentation/Set4/NT-106-02/04Pairoj.pdf | 2026-10-24 | No licence line on the extracted slides. Short quotation. The slides are not the announcement. |
| KKH-EMS | Khon Kaen Hospital EMS ebook, phone-triage chapter | https://www.kkh.go.th/wp-content/uploads/2023/09/EMS-KKH-2023_eBook-2.pdf | 2026-10-24 | No licence line extracted. One centre's description of criteria-based dispatch, not a national regulation. |
| NIEMS-2554 | ประกาศคณะกรรมการการแพทย์ฉุกเฉิน เรื่อง หลักเกณฑ์การประเมินเพื่อคัดแยกระดับความฉุกเฉินและมาตรฐานการปฏิบัติการฉุกเฉิน พ.ศ. 2554, Royal Gazette volume 128, special part 131 ง, pages 32-35 | https://www.ratchakitcha.soc.go.th/DATA/PDF/2554/E/131/32.PDF | 2026-10-24 | Official announcement. Thai Copyright Act B.E. 2537 section 7 excludes regulations, announcements and orders of state agencies from copyright. Confirm that reading before reuse beyond this corpus. A plain download returned HTTP 403. The PDF text was read from that URL on the retrieved date. Damaged words in the extract were not repaired. |
| NWS-FLOOD-DURING | National Weather Service, During a Flood | https://www.weather.gov/safety/flood-during | 2026-10-24 | US government material. Short quotation. |
| READY-FLOODS | FEMA Ready.gov, Floods | https://www.ready.gov/floods | 2026-10-24 | US government material. Short quotation. |
| READY-DISABILITY | FEMA Ready.gov, People with Disabilities | https://www.ready.gov/disability | 2026-10-24 | US government material. Short quotation. The Alzheimer's lines are on that page. They are not a flood-only age rule. |
| CDC-FLOODWATER | CDC, Safety Guidelines: Floodwater | https://www.cdc.gov/floods/safety/floodwater-after-a-disaster-or-emergency-safety.html | 2026-10-24 | US government material. Short quotation. The page marks leptospirosis as not common. That marking was kept. |
| CDC-INSULIN | CDC, Managing Insulin in an Emergency | https://www.cdc.gov/diabetes/articles/managing-insulin-in-emergency.html | 2026-10-24 | US government material. Short quotation. The 86°F figure is the page's. No dose was copied. |
| EA-FLASH | Environment Agency, Flash flooding (England) | https://www.gov.uk/guidance/flash-flooding | 2026-10-24 | GOV.UK. Open Government Licence v3.0 unless the page says otherwise. Short quotation. |
| EA-WARNINGS | Environment Agency, Flood alerts and warnings (England) | https://www.gov.uk/guidance/flood-alerts-and-warnings-what-they-are-and-what-to-do | 2026-10-24 | GOV.UK. Open Government Licence v3.0 unless the page says otherwise. Short quotation. |
| IFRC-FLOODS | IFRC and Save the Children, PAPE second edition, floods messages | https://www.ifrc.org/sites/default/files/2021-06/18-FLOODS-HR.pdf | 2026-10-24 | © IFRC 2018, with Save the Children. The copyright page does not print a redistribution licence beyond the disclaimer that interpretation lies with the reader. Short quotation. Confirm before redistribution. Vehicle-depth conversions are quoted as printed, including where they disagree. |
| UK-MAFP | Developing a multi-agency flood plan | https://www.gov.uk/government/publications/flooding-developing-a-multi-agency-flood-plan/developing-a-multi-agency-flood-plan | 2026-10-24 | GOV.UK. Open Government Licence v3.0 unless the page says otherwise. Short quotation of the boat team types only. |
| UK-FRCO-2019 | Flood Rescue Concept of Operations, November 2019 | https://assets.publishing.service.gov.uk/media/5faa9ca5e90e0730666d4162/frco-november-2019a.pdf | 2026-10-24 | Withdrawn on 13 January 2026 as out of date. The PDF was still reachable. Short quotation. Not adopted as a current order. Withdrawal page: https://www.gov.uk/government/publications/flood-rescue-concept-of-operations-2019 |

## Counts

As loaded on 24 October 2026: 89 rules, 83 verified, 6 unverified. System 1 has 16 hypotheses, all 16 verified. Placeholders are the rules whose status is `unverified` and whose English text contains `TODO_HUMAN`. The corpus version is the sha256 of the normalised rules, labels, and adapter versions. After this load it is `86b78f8ca22d8a24f70f4358fa6b8857549fcd2db00079842e824cca16bf5ca0`.

New rules in `policies/flood.yaml`, by topic. `FLOOD-WATER-DEPTH` was already in the corpus and is not counted as new. `FLOOD-TRAPPED-DISPATCH` and `NIEMS-ANNOUNCEMENT-2554` were updated in place.

| topic | new rules | verified | unverified |
|---|---|---|---|
| Walking and driving water depth, beside the updated `FLOOD-WATER-DEPTH` | 3 | 3 | 0 |
| Evacuation triggers | 3 | 3 | 0 |
| Boat and water rescue | 5 | 4 | 1 |
| Electrical hazard in floodwater | 3 | 3 | 0 |
| Medically dependent people | 2 | 2 | 0 |
| Floodwater health | 2 | 2 | 0 |
| Children and older people left alone | 3 | 3 | 0 |

The walking figure is shared: about 6 inches, and 15 centimetres where the page prints that. The vehicle figures are not. National Weather Service: 12 inches floats a car or small SUV, 18 inches carries large vehicles. Ready.gov: one foot sweeps a vehicle away. Environment Agency: around 60cm carries a vehicle of any size. IFRC prints both "20 centimetres or 6 inches" and "50 centimetres, i.e. 2 feet". All four are quoted. None was chosen.

## Gaps a human still has to close

- The B.E. 2568 Ministry of Finance regulation itself (definitions of disaster, flood, and victim, and whether assistance is immediate relief rather than full compensation). The 2569 criteria cite it. A non-DDPM copy of the regulation was not retrieved. See `MOF-2568-REGULATION-TEXT`.
- The temporary-shelter conversion cap in clause 5.1.8, and the per-place toilet cap in clause 5.1.9 (3). A Latin digit broke the Thai number. See `MOF-2569-TEMP-SHELTER-CAP` and `MOF-2569-TOILET-BLOCK-COST`.
- Age and baht glyphs in the PM2.5 mask and dust-net clauses. See `MOF-2569-PM25`.
- No baht-per-rai crop price is printed. `MOF-2569-CROP-CAP` keeps the rai caps and the labour percentages only.
- Dispatch minute targets are still not in the corpus. The B.E. 2554 announcement was retrieved and its clause 5 does not print a minute figure. The Khon Kaen Hospital table still was not a stable sentence, and the ebook URL returned HTTP 403 on this pass. See `CBD-RESPONSE-MINUTES`. This is a team assumption: do not store a minute target.
- No retrieved page ranks a person in the water, a person on a roof, and a person who cannot climb. The 2019 Flood Rescue Concept of Operations says those most at risk are prioritised, and that rescuer safety comes before the casualty, but the publication was withdrawn on 13 January 2026. See `FLOOD-BOAT-ORDER`. This is a team assumption: do not invent that ranking or a 1669 colour for a boat task.
- The UNHCR persons-at-risk page says it is outdated and under revision.
- Sphere's Thai edition was not retrieved. Thai on Sphere rules is absent. Thai on System 1 hypotheses is a template, not a Sphere translation.
- Which of these rules the demo may treat as authoritative is `policies.authoritative_set: TODO_HUMAN`.

## Adapters

Live: `local_yaml` only. It reads the five rule files and `system1_labels.yaml` in this directory. Its version is a hash of those bytes. The corpus version is a hash of the normalised rules, labels, and adapter versions. `policies/flood.yaml` is the international flood-safety file. System 1 hypotheses cite those rules in `derived_from`. That citation does not change `config/escalation.yaml` or `config/priorities.yaml`.

Remote sources below were probed on 24 October 2026. They are candidates, not adapters. Each one is `TODO_HUMAN`. None of their payloads were copied into a rule. Funding totals from the HPC response were not stored.

| source_id | probed url | accessible | why it is not an adapter |
|---|---|---|---|
| sphere_handbook_api | https://handbook.spherestandards.org/ | no | HTTP 403. The WordPress JSON endpoint also returned HTTP 403. Sphere's search API needs a key. No key is stored. |
| ifrc_go | https://goadmin.ifrc.org/api/v2/disaster_type/ | yes | HTTP 200 disaster-type list with empty summaries. Not the PGI standards. |
| ifrc_documents | https://www.ifrc.org/api/documents | no | HTTP 403. |
| iasc | https://interagencystandingcommittee.org/jsonapi | no | HTTP 202, empty body, WAF challenge. No ReliefWeb catalogue was used. |
| hdx_hapi | https://hapi.humdata.org/api/v2/util/version | partial | Version endpoint HTTP 200 (API 0.9.15). Data queries need an app identifier built from an email. No email was sent. Rows are indicators, not rules. |
| hdx_ckan | https://data.humdata.org/api/3/action/package_search | yes | HTTP 200 operational datasets. Not handbook text. |
| ocha_hpc_fts | https://api.hpc.tools/v1/public/fts/flow | yes | HTTP 200 funding flows. Not eligibility rules. Totals were not copied. |
| data_go_th | https://data.go.th/api/3/action/package_search | no | HTTP 403. |
| gdcatalog_ratchakitcha | https://gdcatalog.go.th/api/3/action/package_show?id=gdpublish-dataset-02-04 | partial | Package metadata HTTP 200, including monthly Royal Gazette JSON links. `robots.txt` for `User-agent: *` disallows `/`. The JSON host timed out. Titles were not downloaded. |
| worldbank_documents | https://search.worldbank.org/api/v3/wds | yes | HTTP 200 document metadata. Not a rule corpus. No abstract was stored. |
| worldbank_aspire | https://www.worldbank.org/en/data/datatopics/aspire | no | Indicator files. No verified JSON API of legal rules. |
| krisdika | https://www.krisdika.go.th/ | no | TLS certificate did not verify. No law text was fetched. |
