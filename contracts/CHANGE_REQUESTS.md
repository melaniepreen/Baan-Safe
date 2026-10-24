# Contract change requests

No open change requests.

Agents who think a contract is wrong must add a proposal here. They do not edit
`contracts/models.py` themselves. The Lead re-tags contracts if a change is accepted.

## CR-002 (accepted)

- id: CR-002
- model: Person, Household, Request, Evidence, Hazard, Resource, AidPolicy, Failure, AidEligibility, TrainingJob, ModelVersion; TraceEvent.outcome and TraceEvent.model_version
- proposed change: Add the ontology entities from the 24 Oct 2026 revised architecture. `Need` already existed as an enum and stays the need entity. `CaseState` stays the case. Trace events may carry the outcome of the system that actually ran. Aid eligibility cannot store an approval.
- why: Moly asked for these shapes so Saturday work shares one language, and the correction loop needs a training-job and model-version record. The change is additive. Existing fixtures still validate.
- from: Moly (repo owner), 24 Oct 2026
- status: accepted
- tag: v0.2-contracts

## Template

- id:
- model:
- proposed change:
- why:
- from: (agent / owner)
- status: open
