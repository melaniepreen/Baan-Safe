# Triage philosophy

Suggestions for Moly and Melanie to sign off. No threshold in `config/` was changed to match this note. The escalation rule strings are still not executed by the stub gateway.

## Phone triage, not a waiting room

Emergency medical dispatch systems such as the Medical Priority Dispatch System (MPDS, owned by the International Academies of Emergency Dispatch) and criteria-based dispatch ask a fixed set of questions and turn the answers into a priority and a response. The card sets are proprietary. This project must not copy them. The idea worth taking is the shape: System 1 asks until it has a location, a danger, and a vulnerability, then it stops. https://www.emergencydispatch.org/

NHS 111 in England is a useful contrast, not a template. A nurse or a call-handler ends on a disposition: an ambulance, an emergency department, an urgent callback, a GP, or self-care. https://www.england.nhs.uk/urgent-emergency-care/nhs-111/ Our routes are disaster routes (`rescue_coordination`, `medical_response`, `welfare_distribution`, `shelter_placement`, `aid_caseworker`, `information_only`, `duplicate_merge`, `supervisor_escalation`). Do not rename them to clinical dispositions. A flood call that needs a boat and a flood call that needs a doctor are different routes even when both feel urgent.

## START and SALT

START (Simple Triage and Rapid Treatment) and SALT (Sort, Assess, Lifesaving interventions, Treatment/Transport) are for a responder standing in front of many injured people. A public description of START is at https://chemm.hhs.gov/startadult.htm SALT is described by the US National Association of State EMS Officials and NAEMT as a mass-casualty sort: global sort first, then individual assessment, a few lifesaving acts, then treatment and transport.

The part that transfers to a phone is the sort, not the expectant category. On the phone you cannot see breathing, and you must not tell a caller that someone has been written off. If a caller describes several unconscious people, the right product move is `supervisor_escalation` and `medical_response`, with a human on the line. Suggest that "expectant / dead" never be a route the model can select.

## Vulnerability

In floods, the people who die or who cannot comply with an evacuation order are often older, unable to walk, dependent on oxygen or dialysis or electricity for a device, caring for someone else, or children who are alone. That is already gestured at in `config/escalation.yaml`: medical, `oxygen_dependent`, `immobile`, safeguarding, and a missing location are listed as reasons to involve System 2. Suggest Moly and Melanie keep those as the deliberate-reasoning triggers and add, only by an explicit edit they both accept:

- a child who is alone, even if the rest of the story sounds like "P3 shelter"
- a device that stops if the power stops (oxygen, home ventilator), even if the caller sounds calm
- "we can't climb" as immobile, not as a shelter request

Do not invent a score that adds these up. The fixtures already mark safeguarding and aid exceptions as `requires_human: true`.

## A human in the loop

Two different "human" moments get confused:

1. **The call.** Someone has to be able to take over when the model is unsure, when the route is aid or safeguarding, or when the caller is in immediate danger. That is `requires_human` and `supervisor_escalation`.
2. **The rule.** Thresholds (what "heavy rain" means, when System 2 is invoked, when a repeated correction graduates into System 1) are product decisions. They stay `TODO_HUMAN` or judgement calls in config until a named person changes them.

Safeguarding: do not ask a child for a graphic account. Do not store a story that identifies a real child. The fixtures that mention a child are synthetic and non-graphic on purpose. A real deployment needs a named safeguarding owner. We do not have one in `config/decisions.yaml`.

## Dual process, as a frame for the two systems

A useful frame, not a claim about how the models think: a fast path that applies agreed rules, and a slow path that is used when the fast path is a bad fit. Kahneman's System 1 / System 2 language is the analogy the architecture already uses. It is an analogy.

| | Fast path (Moly, System 1) | Slow path (Melanie, System 2) |
|---|---|---|
| When | The story matches a clear fixture pattern: one need, a known district, no medical flag, no safeguarding | Any line in `escalate_to_system_2_if_any`, or the fast path says it is unsure |
| Output | Priority, route, the next question if something is missing | A revised priority and route, plus a reason a supervisor can read |
| Must not | Invent a household, approve an aid payment, ignore a child alone | Run on every call "just in case" once a latency budget exists |

`system2.max_latency_ms` is still `TODO_HUMAN`. Until it is set, nobody should promise that the slow path returns inside a call.

## How this sits on the current config

These are readings of the files, not edits.

**Priority (`config/priorities.yaml`).** P1 is life safety now. P2 is serious and time-bound but the caller can still talk and move, or the facts conflict. P3 is a real need (water, food, shelter, power, an aid question) without immediate danger. P4 is information. The doubtful labels in `MORNING_REPORT.md` (power as information-only, both sides of a duplicate marked merge, a vague temple as P2) are exactly the calls a human should re-read. This note does not relabel them.

**Routes (`config/routes.yaml`).** Power has no rescue route; the fixture uses `information_only`. Suggest you either add a power route or accept information-only. Water and food share welfare distribution. Rescue and medical can both be true; the router, when it exists, has to pick one next action.

**Escalation (`config/escalation.yaml`).** The strings are not evaluated. Suggest the first real System 1 treat them as the list of reasons to set `escalate: true`, and that "always requires a human" stay true for `supervisor_escalation`, aid exceptions, and safeguarding even if the priority comes out as P3.

**Enrichment flags.** Heavy rain at 30 mm in 24 hours and a 500 m buffer are starting numbers for data flags only. They must not change priority by themselves. Hat Yai's reported single-day rain was an order of magnitude above 30 mm; 30 mm is a flag, not a definition of a disaster.

**Next action.** The stub order sends information-only cases to `create_provisional_dispatch`. Suggest the real router use `finalize_case` or a pure information action for P4, so an information call does not look like a dispatch. That is a Moly decision in `router/merge.py`, which is still unimplemented.
