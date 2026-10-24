# International flood response practice

Use this when a route name needs an outside reference. It is not a commitment to run a UN cluster system inside a Thai call centre.

## Sendai Framework

The Sendai Framework for Disaster Risk Reduction 2015–2030 (UNDRR) has four priorities: understand disaster risk, strengthen governance, invest in resilience, and improve preparedness so that response also supports recovery ("build back better"). https://www.undrr.org/implementing-sendai-framework/what-sendai-framework

For a call product the useful part is priority 4: people need a warning they can act on, and the people who cannot act alone need to be found early. Sendai is not a priority score. Do not map P1–P4 onto Sendai priorities. The letters collide and the ideas do not.

## IASC clusters

In a large international response the Inter-Agency Standing Committee organises agencies into clusters. The list and the coordinators are here: https://www.humanitarianresponse.info/en/coordination/clusters The ones that match flood calls:

| Cluster | What a caller is usually asking for | Closest route name we already have |
|---|---|---|
| Health | Injury, medicine, oxygen, a flooded hospital | `medical_response` |
| WASH | Drinking water, toilets, contamination | `welfare_distribution` (water) |
| Food security | Food | `welfare_distribution` (food) |
| Shelter | A dry place to sleep | `shelter_placement` |
| CCCM | How a shelter is run, who is registered there | `shelter_placement` |
| Protection | A child alone, someone who cannot leave | `supervisor_escalation` |
| Emergency telecoms | "The phone is dying", no callback | no route; a comms fact, not a dispatch |
| Logistics | Boats, trucks, access | `rescue_coordination` when a person is trapped; otherwise not a caller route |

Thailand's own response in 2011 and 2025 was led by Thai authorities, not by a full cluster activation. The table is a vocabulary for Melanie when a case needs an external handover. It is not a change to `config/routes.yaml`.

## Sphere

The Sphere Handbook (2018) is the usual humanitarian minimum. https://spherestandards.org/handbook-2018/ Figures that matter for water, shelter, and food, as published there:

- Water: 15 litres per person per day for drinking, cooking, and hygiene in the survival baseline. There are also figures for how many people share a tap and how close the water point should be. Those are camp standards, not a rule for a household that still has a tap.
- Shelter: about 3.5 square metres of covered space per person is the planning figure for a shared shelter.
- Food: about 2,100 kilocalories per person per day is the planning figure.

A caller who says "we have rice for tonight but no water" is a water case, not a food case. A shelter that is a temple hall will not meet 3.5 square metres, and the call-taker should not promise that it will. Sphere is the standard to hand a caseworker, not a sentence to read to the caller.

## CAP alerts

The Common Alerting Protocol (OASIS CAP 1.2) is a format for a warning: what happened, where, how urgent, and what to do. https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html A CAP message has an urgency, a severity, and a certainty, plus an area. That is a better input to System 1 than a paragraph of a news article, because it is already structured and it has a polygon or a place code.

We do not have a live CAP feed in the database. If TMD or DDPM publishes one, it should land as a data flag ("official warning covers this district"), not as an automatic priority. The human still owns the threshold in `config/escalation.yaml`.
