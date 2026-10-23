# BaanSafe — Product Requirements Document

## 1. Product summary

**BaanSafe** is an emergency response and aid-allocation assistant for floods and other disasters. It helps hotlines, local authorities, and relief teams understand incoming requests, identify urgent needs, route people to the right support, and allocate limited resources fairly.

BaanSafe does not replace emergency responders, caseworkers, or government decision-makers. It helps them make faster, better-evidenced decisions.

**Core promise:**  
*Every request is triaged, routed, and followed up. Every failure becomes a lesson for the next response.*

## 2. Problem

During a flood, people contact hotlines, local leaders, social media channels, and government apps with urgent but incomplete information:

- “Water is entering my house.”
- “My elderly parent is trapped.”
- “My child needs formula.”
- “I have no power for medical equipment.”
- “I cannot reach the hospital.”
- “My documents were destroyed and I need aid.”

Response teams must decide, quickly:

- Is this life-threatening?
- Who needs rescue, medical help, shelter, food, water, transport, or financial aid?
- Which team should respond?
- Which request should be handled first when resources are limited?
- Did anyone eligible get missed, delayed, or given the wrong support?

Today, this often depends on phone queues, manual spreadsheets, local knowledge, and fragmented systems. That creates delays, duplicate work, and exclusion errors.

## 3. Goals

### Product goals

1. Triage every incoming request into a clear priority and need category.
2. Route each request to the correct responder or agency.
3. Collect only the evidence needed to make a safe decision.
4. Allocate scarce resources based on urgency, vulnerability, and location.
5. Track every request from first contact to resolution.
6. Learn from delays, exclusions, wrong routing, and unmet needs.
7. Give officials a clear view of coverage, gaps, and resource pressure.

### Non-goals

BaanSafe will not:

- Automatically deny emergency assistance.
- Replace medical professionals, rescue teams, or caseworkers.
- Make final decisions on compensation, safeguarding, or legal eligibility.
- Use criminal history, political affiliation, religion, ethnicity, or nationality to prioritize aid.
- Publish identifiable personal information.

## 4. Users

| User | What they need |
|---|---|
| Hotline operator | Quickly understand a request and know what to do next |
| Rescue coordinator | See urgent rescue cases, locations, and available teams |
| Medical dispatcher | Identify medical dependencies and route to emergency care |
| Welfare officer | Identify households needing food, shelter, cash, or essential supplies |
| Local authority | See coverage gaps, resource pressure, and unresolved cases |
| Aid administrator | Verify eligibility evidence and process aid packages |
| Government decision-maker | Understand response performance and recurring policy failures |
| Affected resident | Receive timely, understandable help and know what happens next |

## 5. Core user journeys

### Journey 1: Trapped resident

1. A resident sends a LINE message: “Water is waist-high. My father cannot walk. We need help.”
2. BaanSafe identifies two needs: rescue and mobility assistance.
3. It asks for a location pin or nearby landmark.
4. It checks the reported location against flood extent and road access.
5. It creates a high-priority rescue case.
6. It routes the case to the local rescue coordinator.
7. The coordinator sees the request, location, urgency, and available nearby team.
8. After resolution, the outcome is recorded.

### Journey 2: Medical dependency

1. A caller says a family member uses an oxygen machine and has no electricity.
2. BaanSafe identifies a medical-power dependency.
3. It asks whether the person has backup power, medication, or immediate breathing difficulty.
4. If the risk is high, it routes the case to medical dispatch.
5. If the risk is uncertain, it requests targeted additional information.
6. The case remains open until a responder confirms the person is safe.

### Journey 3: Flood-aid application

1. A household applies for flood relief.
2. BaanSafe checks whether the home is in an officially declared assistance area.
3. It checks reported flood duration and property damage.
4. If evidence is missing, it tells the applicant exactly what is needed.
5. If documents were destroyed, it offers an alternative evidence route where policy allows.
6. A caseworker reviews any exception or uncertain case.
7. The approved aid package is recorded and tracked through payment or delivery.

### Journey 4: Resource allocation

1. A district has 20 open rescue requests and three available boats.
2. BaanSafe ranks requests using urgency, number of people at risk, medical dependency, isolation, and travel feasibility.
3. It recommends a dispatch order.
4. The coordinator can accept, change, or override the recommendation.
5. Every override and outcome is recorded.

## 6. Request intake

BaanSafe should accept requests from multiple channels:

- Hotline calls, through operator transcription or structured call notes.
- LINE messages, including text, photos, videos, and location pins.
- Web or mobile forms.
- Field reports from village heads, district officers, or volunteers.
- Referrals from hospitals, shelters, or community organizations.

Each request should capture:

- Contact method and preferred language.
- Location, preferably a map pin, address, landmark, or approximate area.
- People affected.
- Immediate danger.
- Medical or accessibility needs.
- Household composition.
- Requested support.
- Photos, videos, or other evidence.
- Time of request.
- Whether the person can be contacted again.

## 7. Triage logic

Every request receives:

1. A priority level.
2. One or more need categories.
3. A routing destination.
4. An evidence status.
5. A follow-up plan.

### Priority levels

| Priority | Meaning | Examples |
|---|---|---|
| **P1 — Life safety** | Immediate danger to life | Person trapped, rising water, structural collapse, missing person |
| **P2 — Urgent medical** | Medical need that can deteriorate quickly | Oxygen dependence, dialysis, medication shortage, injury |
| **P3 — Urgent welfare** | Basic needs at immediate risk | No safe drinking water, infant formula, no shelter tonight, no food |
| **P4 — Access and mobility** | Person cannot reach essential services | Flooded road, no transport to hospital, inaccessible shelter |
| **P5 — Recovery and compensation** | Non-immediate support | Aid application, document replacement, damage assessment |

### Need categories

- Rescue and evacuation.
- Medical support.
- Shelter.
- Food and drinking water.
- Infant and child needs.
- Accessibility support.
- Power or generator support.
- Transport.
- Communication support.
- Financial aid.
- Document replacement.
- Damage assessment.
- Mental-health or psychosocial support.

### Routing rules

| Need | Primary route |
|---|---|
| Life-threatening rescue | Local rescue coordination |
| Medical emergency | Emergency medical dispatch |
| Shelter | Local authority or shelter coordinator |
| Food and water | Relief distribution team |
| Infant or medical supplies | Welfare and logistics team |
| Power dependency | Medical dispatch plus logistics |
| Road or infrastructure issue | Roads or local infrastructure team |
| Compensation | Aid administration or district office |
| Unclear or high-risk case | Human supervisor |

## 8. Evidence and verification

BaanSafe should distinguish between what a person says, what can be verified, and what still needs checking.

### Evidence types

- Location pin or landmark.
- Photo or video.
- Flood-depth description.
- Number and age of people affected.
- Medical-device information.
- Damage description.
- Official flood-zone status.
- Responder confirmation.
- Shelter availability.
- Road-status information.

### Evidence states

| State | Meaning |
|---|---|
| **Verified** | Evidence supports the request |
| **Partially verified** | Some evidence exists, but key facts remain uncertain |
| **Needs evidence** | The request cannot be safely assessed yet |
| **Conflicting** | Evidence points in different directions |
| **Provisional** | Aid or support can proceed while further evidence is gathered |

### Evidence-gathering principle

BaanSafe should ask for the minimum additional information required to make a safe decision.

For example:

- If someone reports a trapped person, ask for location first, not income documents.
- If someone reports a medical dependency, ask about immediate symptoms and backup power.
- If someone applies for compensation, ask for flood duration and damage evidence.
- If documents are destroyed, offer alternative evidence where policy permits.

## 9. Resource routing

BaanSafe should maintain a live view of available resources:

- Rescue teams and boats.
- High-clearance vehicles.
- Medical teams and ambulances.
- Shelters and available spaces.
- Food, water, and hygiene kits.
- Infant supplies.
- Generators and power banks.
- Accessible transport.
- Cash-aid budget.
- Field staff and volunteers.

### Allocation principles

1. **Life safety first.** P1 requests take precedence over lower-priority requests.
2. **Medical dependency matters.** A person dependent on powered medical equipment may need urgent support even if they are not physically trapped.
3. **Isolation increases urgency.** People who cannot self-evacuate or contact help need earlier intervention.
4. **Household vulnerability matters.** Children, older people, disabled people, pregnant people, and people with chronic conditions may require adapted support.
5. **Feasibility matters.** A nearby team that can reach a person safely may be preferable to a better-resourced team that cannot access the area.
6. **Do not waste scarce resources.** Avoid duplicate dispatches where possible.
7. **Human override is always available.** The system recommends; people decide.

### Recommended dispatch order

For each open request, BaanSafe should show:

- Priority.
- People at risk.
- Medical or accessibility flags.
- Location and access constraints.
- Nearest suitable resource.
- Estimated response feasibility.
- Reason for the recommendation.
- Alternative options if the primary resource is unavailable.

## 10. Aid-package logic

An aid package is the combination of support assigned to a household or individual.

Examples:

- Emergency cash.
- Food and water.
- Shelter placement.
- Hygiene kit.
- Infant formula.
- Medicine delivery.
- Generator or power bank.
- Transport voucher.
- Document-replacement appointment.
- Temporary housing referral.

### Package rules

A package should be built from:

- Verified immediate needs.
- Household composition.
- Medical and accessibility needs.
- Location and access constraints.
- Available inventory.
- Policy eligibility.
- Previously received support.

### Avoiding gaps and duplication

BaanSafe should check:

- Has this household already received this item?
- Is another family member receiving the same support?
- Is the requested item appropriate for the household?
- Is there a more urgent unmet need?
- Is the household in an area that can be reached safely?

## 11. Persistent memory

BaanSafe should remember patterns across requests, events, and response periods.

### Operational memory

Short-term memory for the current emergency:

- Open requests.
- Active dispatches.
- Resource availability.
- Unresolved follow-ups.
- Recent routing outcomes.

### Institutional memory

Long-term memory across floods and response periods:

- Which areas flooded repeatedly.
- Which request types increased during comparable events.
- Which evidence requirements caused delays.
- Which communities were under-served.
- Which aid packages were mismatched.
- Which policies created bottlenecks.
- Which resources were needed earlier than expected.

### Memory record

Each learning record should include:

- The original decision.
- The information available at the time.
- The outcome.
- What went wrong, if anything.
- The correction.
- The evidence supporting the correction.
- The person or team that approved the correction.

## 12. Correction loop

When an outcome reveals a problem, BaanSafe should create a correction record.

### Failure types

| Failure | Example | Correction |
|---|---|---|
| Under-triage | A medical case was treated as non-urgent | Update triage rules and evidence prompts |
| Delayed rescue | Location information was not used early enough | Request location earlier and escalate incomplete P1 cases |
| Exclusion | A household could not provide damaged documents | Add alternative-evidence pathway |
| Wrong package | A household received cash but needed shelter | Improve need-to-package mapping |
| Duplicate aid | Two family members received the same supply | Add household-level deduplication |
| Resource mismatch | A boat was sent where road access was possible | Improve route and resource matching |
| Coverage gap | One district had low registration despite high exposure | Trigger outreach and local-partner follow-up |

### Correction approval

A correction should not silently change policy.

The workflow should be:

1. System detects a pattern or failure.
2. It drafts a proposed correction.
3. It shows the evidence and affected cases.
4. A responsible human reviews it.
5. If approved, the correction becomes active.
6. Future similar cases are handled differently.
7. The system measures whether the correction improved outcomes.

## 13. Dashboards

### Hotline operations

- Open requests by priority.
- Requests waiting for follow-up.
- Average time to first response.
- Requests by need category.
- Requests by district.
- Unresolved P1 and P2 cases.

### Resource view

- Available rescue teams, boats, ambulances, and shelters.
- Requests waiting for each resource type.
- Resource bottlenecks.
- Dispatch recommendations.
- Overrides and reasons.

### Aid coverage

- Registered households.
- Estimated affected households.
- Approved, pending, rejected, and appealed cases.
- Payments issued.
- Average time to payment.
- Exclusion-risk areas.
- Duplicate or suspicious cases for review.

### Learning view

- Recent corrections.
- Policy rules changed.
- Failure patterns.
- Before-and-after performance.
- Cases replayed under old and new rules.

## 14. Metrics

### Response metrics

- Time from request to triage.
- Time from request to dispatch.
- Time from dispatch to resolution.
- Percentage of P1 cases dispatched within target.
- Percentage of requests routed correctly on first attempt.
- Percentage of requests requiring follow-up.

### Equity and coverage metrics

- Requests received versus estimated affected population.
- Aid registrations versus affected households.
- Approval, delay, and rejection rates by district.
- Language and accessibility support usage.
- Repeat-contact rate.
- Unresolved-case rate.

### Aid metrics

- Time from application to aid decision.
- Time from approval to payment or delivery.
- Percentage of eligible households receiving aid.
- Percentage of applicants requiring additional evidence.
- Percentage of denied cases overturned on review.
- Duplicate-aid rate.

### Learning metrics

- Number of corrections proposed, approved, and applied.
- Improvement in routing accuracy after correction.
- Reduction in delay or exclusion after correction.
- Percentage of historical failures correctly prevented on replay.

## 15. Trust, safety, and fairness

### Human oversight

- A human must review denials, reductions, safeguarding conflicts, and exceptions.
- Rescue dispatch recommendations must always be visible to a human coordinator.
- The system must clearly show why it made a recommendation.

### Fail toward help

When uncertain, BaanSafe should:

- Escalate rather than downgrade.
- Request more evidence rather than reject.
- Provide provisional support where policy allows.
- Keep the case open until resolved.

### Fairness

- Do not use protected characteristics to prioritize individuals.
- Monitor outcomes by area, language, disability status, age group, and other relevant dimensions where lawful and appropriate.
- Investigate unexplained differences in delay, approval, or exclusion rates.
- Allow people to correct wrong information and appeal decisions.

### Privacy

- Minimize personal data collection.
- Separate identity data from operational dashboards where possible.
- Restrict access to sensitive case details.
- Keep an audit trail of who viewed, changed, or approved a case.
- Use synthetic data for demos and testing.

## 16. MVP scope

### Included

- Request intake from a simulated hotline or LINE-style channel.
- Thai and English request examples.
- Priority and need-category triage.
- Location, evidence, and follow-up prompts.
- Routing to rescue, medical, welfare, infrastructure, or aid teams.
- Simple resource inventory and dispatch recommendations.
- Household aid-package recommendations.
- Case status tracking.
- Operational dashboard.
- Correction-loop demo using simulated failures.
- Before-and-after replay of a delayed or excluded case.

### Deferred

- Live integration with 1784, 1669, LINE, or Thang Rath.
- Real payment disbursement.
- Official identity verification.
- Automated safeguarding decisions.
- Real-time satellite ingestion.
- Full macroeconomic forecasting.
- Public-facing mobile app.
- Multi-country expansion.

## 17. Demo scenario

### Before correction

1. A caller reports an older relative trapped but does not know the exact address.
2. The request enters a general follow-up queue.
3. Rescue is delayed.
4. The post-incident review finds that the location pin and nearby landmark were not used early enough.

### Correction

BaanSafe creates a correction:

> “When a request includes a trapped person, request location immediately and escalate to local rescue before all details are complete.”

### After correction

1. A similar request arrives.
2. BaanSafe immediately classifies it as P1.
3. It asks for a location pin.
4. It shows the nearest rescue team and access constraints.
5. The coordinator dispatches without waiting for complete information.

## 18. Success criteria

For the MVP demo, BaanSafe is successful if it can:

1. Triage a mixed set of simulated requests into sensible priorities.
2. Route each request to a plausible responder.
3. Identify missing evidence and request only what is necessary.
4. Recommend a resource allocation under scarcity.
5. Detect at least one simulated exclusion or delay.
6. Apply a human-approved correction.
7. Replay a similar future case and show improved handling.
8. Explain every recommendation in plain language.

## 19. Open questions

- Which agencies should own each routing category in a real deployment?
- What is the minimum evidence required for provisional cash aid?
- How should duplicate households be identified without excessive data collection?
- Who approves changes to triage or eligibility rules?
- How should BaanSafe handle areas with poor connectivity?
- How should the system support local dialects and vulnerable callers?
- What human-review capacity is required during peak demand?
- How should the system balance individual urgency against district-level equity?
