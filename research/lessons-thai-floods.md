# Lessons from 2011 and from Hat Yai, November 2025

For call triage. Not a history paper and not a list of casualties to store.

## 2011, lower Chao Phraya

The 2011 floods covered a large part of the lower Chao Phraya basin, including industrial estates north of Bangkok, and lasted for weeks rather than a night. The World Bank and GFDRR rapid assessment is the document to use for the scale and the recovery plan: https://www.gfdrr.org/en/publication/thai-flood-2011-rapid-assessment-resilient-recovery-and-reconstruction-planning

What matters for a call product, taken from that kind of slow basin flood rather than from a single anecdote:

- **The danger moved.** A caller upstream and a caller downstream were not in the same flood on the same day. A release at a barrage mattered as much as the rain. A system that stamps one "event" on the whole country will mis-triage both.
- **Agencies disagreed in public.** People heard different stories about whether to leave. Conflicting evidence is already an escalation string. Suggest System 2 be the path when the caller quotes two official stories.
- **Location failed.** Estate names, soi names, and "near the factory" stopped working once the landmarks were under water. The fixtures' vague "blue temple" case is this failure in miniature. Ask for a district, a road, and a floor, and accept that the answer may be "I don't know any more".
- **The same household called more than once**, and different agencies logged different calls. Duplicate detection has to survive a second phone and a second agency. The fixture pair F08/F09 is the synthetic version. Both are labelled `duplicate_merge`, which a human may not want.
- **People stayed** because of work, livestock, or not believing the water would reach the second floor. A calm voice is not a low priority.

## Hat Yai, November 2025

Hat Yai in Songkhla flooded in the last ten days of November 2025 after extreme local rain. Reuters reported that the city received 335 mm in a day, described as its highest single-day total in 300 years, and quoted a resident: "By 9 a.m., the water was chest deep." https://www.reuters.com/business/environment/weve-lost-everything-how-floods-devastated-one-thailands-largest-cities-2025-11-28/ That 335 mm figure is Reuters' report of the measurement, not a figure we computed.

The Ministry of Public Health, as reported on 25 November 2025, said Hat Yai Hospital's oxygen would last only into the next day and that about 90 critical patients needed to be moved, with the first 50 by air to Songklanagarind, Songkhla, Phatthalung, and Pattani hospitals. https://www.nationthailand.com/news/general/40058742 Helicopter crews later described 25 November as a day when the phone network did not work at all; people at the hospital knew the aircraft had arrived because they heard it. https://en.thairath.co.th/news/local/2899899 The digital ministry described terrestrial networks as down and a temporary satellite link being brought in for the emergency area. https://www.nationthailand.com/news/general/40058859

GLIDE `FL-2025-000210-THA` (17 November 2025) is the public id whose comment says flooding was reported in southern provinces after heavy rain from around 19 November. GLIDE `FL-2025-000209-THA` is a different record, centred on Phra Nakhon Si Ayutthaya and a Bangkok subdistrict. The Hat Yai satellite polygon in this repo is joined to `FL-2025-000210-THA` with that reasoning written into `data/SOURCES.md`. It is a judgement, not a registry confirmation.

Implications for triage:

- **A hospital can become the caller.** "We are the hospital and the oxygen runs out tomorrow" is P1 medical and rescue, and it is a human conversation. The fixtures' medical cases are households. Add a facility case only if a human writes it. Do not invent one here.
- **Chest-deep water by morning, after a night that looked manageable,** is the failure mode of a P3 "water in the street" label. Time of day and whether the caller can still reach the stairs matter more than the first sentence.
- **Comms dropout** means the disposition has to be safe if you cannot call back. Ask for a second number early. If the network is already dead, the case is not `information_only`.
- **Duplicates and rumours** spike when families cannot reach each other. A second call about the same hospital is not a new incident until a human says the patient is different.
- **The map is preliminary.** The EOS-RS product we store is a flood proxy from Sentinel-1, marked preliminary by its authors, weaker over buildings and vegetation. A point outside the polygon is not a reason to tell the caller they are dry.

## What to test with fixtures

The existing 24 fixtures already cover vague location, duplicates, a child, conflicting stories, and aid exceptions, on northern district names. Hat Yai adds a second geography and a hospital-and-comms pattern those fixtures do not have. Suggest a human add one synthetic scenario later, still with a `synthetic:` caller id, rather than pasting a real patient's story into the repo.
