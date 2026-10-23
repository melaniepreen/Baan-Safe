# BaanSafe — Revised Architecture

## Correction

The previous architecture mixed responsibilities. This revision separates them cleanly:

- **Mubit Gateway** owns API access, memory retrieval, policy enforcement, tracing, and audit.
- **System 1** is its own fast decision system with its own inputs, rules, and outcomes.
- **System 2** is its own deliberative reasoning system, orchestrated by **Nemotron**.
- **Nemotron is the orchestrator**, not a component inside the Mubit Gateway.
- BaanSafe does **not** need a separate memory-retrieval service before Mubit, because Mubit already performs memory retrieval.

## Corrected responsibility map

| Layer | Owns | Does not own |
|---|---|---|
| **BaanSafe Frontend / Call Agent** | Call UX, operator controls, live transcript, case view | Policy decisions, memory, model orchestration |
| **Mubit Gateway** | API gateway, memory retrieval, policy checks, traceability, audit, versioning | Reasoning about ambiguous cases |
| **System 1** | Fast, deterministic triage and routing | Deliberate reasoning, memory synthesis, complex exceptions |
| **System 2** | Deliberate reasoning, evidence synthesis, orchestration | Routine low-risk routing |
| **Nemotron** | System 2 orchestration and reasoning | Being embedded inside Mubit |
| **Human operator** | Final decisions on high-risk, safeguarding, and irreversible actions | Routine dispatch acceptance |

## Revised high-level architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│                       BaanSafe Call Agent                          │
│                                                                    │
│  Live transcript · Operator console · Case view · Dispatch view     │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                          Mubit Gateway                             │
│                                                                    │
│  • Authenticated API gateway                                        │
│  • Memory retrieval                                                 │
│  • Policy and safeguarding checks                                   │
│  • Trace, versioning, audit                                         │
│  • Routes work to System 1 or System 2                              │
└───────────┬────────────────────────────────────┬───────────────────┘
            │                                    │
            ▼                                    ▼
┌───────────────────────────┐        ┌───────────────────────────┐
│      System 1              │        │      System 2              │
│  Fast Response System      │        │  Deliberative Reasoning    │
│                            │        │                            │
│  • Deterministic rules     │        │  • Nemotron orchestrator   │
│  • Keyword/field extraction│        │  • Evidence synthesis      │
│  • Priority rules          │        │  • Ambiguity resolution    │
│  • Simple routing          │        │  • Complex triage          │
│  • Duplicate checks        │        │  • Aid exceptions          │
│                            │        │  • Correction proposals    │
│  Own outcome:              │        │                            │
│  fast triage decision      │        │  Own outcome:              │
│                            │        │  reasoned recommendation   │
└─────────────┬─────────────┘        └──────────────┬────────────────┘
              │                                     │
              └──────────────────┬──────────────────┘
                                 ▼
                   ┌───────────────────────────┐
                   │      Decision Router       │
                   │                            │
                   │  • Merge outcomes          │
                   │  • Apply final policy       │
                   │  • Require human review     │
                   │  • Return action to agent   │
                   └──────────────┬────────────┘
                                  ▼
                   ┌───────────────────────────┐
                   │   BaanSafe Call Agent      │
                   │   Next question / dispatch │
                   └───────────────────────────┘
```

## Why this is cleaner

### Mubit Gateway

Mubit is the **gateway and control plane**. It does not reason about the case itself.

It:

- Authenticates and receives agent requests.
- Retrieves relevant memory: similar cases, prior failures, policies, and corrections.
- Applies policy and safeguarding constraints.
- Decides whether the request should go to System 1 or System 2.
- Records traces, versions, latency, token use, and audit events.
- Returns a validated, structured response.

So BaanSafe does **not** build a separate “memory retrieval before Mubit” service. Memory retrieval is a Mubit capability.

### System 1

System 1 is a separate fast-response system.

It handles:

- Clear, low-risk requests.
- Deterministic triage rules.
- Simple location and need extraction.
- Standard routing.
- Duplicate checks.
- Fast evidence-gap detection.

Its outcome is a **fast triage decision**:

```json
{
  "system": "system_1",
  "outcome": "fast_route",
  "priority": "P3",
  "needs": ["water", "food"],
  "route": "welfare_distribution",
  "confidence": 0.94,
  "reason": "Clear non-urgent welfare request with complete location"
}
```

### System 2

System 2 is a separate deliberative reasoning system.

It handles:

- Conflicting or incomplete evidence.
- Medical dependency.
- Safeguarding-sensitive cases.
- Complex routing.
- Aid exceptions.
- Root-cause or correction analysis.

Its outcome is a **reasoned recommendation**:

```json
{
  "system": "system_2",
  "outcome": "reasoned_recommendation",
  "priority": "P1",
  "needs": ["rescue", "medical"],
  "route": "rescue_coordination",
  "confidence": 0.86,
  "reasoning": "Immobility plus rising water creates immediate life-safety risk",
  "missing_evidence": ["exact_location"],
  "next_question": "Can you share a location pin or nearby landmark?"
}
```

### Nemotron

Nemotron is the **orchestrator of System 2**.

It:

- Receives the evidence pack from Mubit.
- Retrieves and interprets relevant memory.
- Reasons over conflicting or incomplete information.
- Decides what additional evidence is needed.
- Produces a structured recommendation.
- Hands the result back to Mubit for policy validation, tracing, and memory write.

Nemotron is not “part of” Mubit. Mubit calls Nemotron when System 2 is required.

## Revised real-time call flow

```text
Caller speaks
      │
      ▼
Live speech-to-text
      │
      ▼
BaanSafe Call Agent
      │
      ▼
Mubit Gateway
      │
      ├── Memory retrieval
      ├── Policy pre-check
      │
      ├── Simple / clear / low-risk ──▶ System 1
      │                                      │
      │                                      ▼
      │                              Fast triage outcome
      │
      └── Ambiguous / high-risk ──────▶ System 2
                                             │
                                             ▼
                                    Nemotron orchestrator
                                             │
                                             ├── Interpret evidence
                                             ├── Retrieve memory context
                                             ├── Decide next question
                                             └── Produce recommendation
                                             │
                                             ▼
                                    Reasoned outcome
      │
      ▼
Decision Router
      │
      ├── Merge System 1 / System 2 outcome
      ├── Apply final policy and safeguarding rules
      ├── Require human review if needed
      └── Return next action
      │
      ▼
BaanSafe Call Agent
      │
      ├── Ask next question
      ├── Update live case state
      └── Start provisional dispatch
```

## Parallel workstreams, revised

Parallel workstreams still run during the call, but they feed **Mubit**, not a separate retrieval layer.

```text
                         Caller speaks
                              │
                              ▼
                   ┌─────────────────────┐
                   │  Live speech-to-text │
                   └──────────┬──────────┘
                              │
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
       ▼                      ▼                      ▼
┌─────────────┐       ┌──────────────┐       ┌──────────────┐
│ Evidence     │       │ Policy &     │       │ Mubit Memory  │
│ Extraction   │       │ Safety       │       │ Retrieval     │
│              │       │              │       │               │
│ • location   │       │ • P1 rules   │       │ • similar     │
│ • people     │       │ • medical    │       │   cases       │
│ • danger     │       │ • safeguard  │       │ • failures    │
│ • medical    │       │ • escalation │       │ • policies    │
└──────┬──────┘       └──────┬───────┘       └──────┬────────┘
       │                      │                      │
       └───────────┬──────────┴───────────┬──────────┘
                   ▼                      ▼
          ┌─────────────────┐    ┌─────────────────┐
          │ Resource Status  │    │  Mubit Gateway   │
          │                  │    │                  │
          │ • boats          │    │ • route to S1/S2 │
          │ • ambulances     │    │ • trace + audit  │
          │ • shelters       │    │ • policy check   │
          └────────┬─────────┘    └────────┬─────────┘
                   │                       │
                   └───────────┬───────────┘
                               ▼
                 ┌───────────────────────────┐
                 │  System 1  or  System 2    │
                 └──────────────┬────────────┘
                                ▼
                   ┌───────────────────────────┐
                   │      Decision Router       │
                   └──────────────┬────────────┘
                                  ▼
                   ┌───────────────────────────┐
                   │   BaanSafe Call Agent      │
                   └───────────────────────────┘
```

## System 1 versus System 2 outcomes

| Aspect | System 1 | System 2 |
|---|---|---|
| Purpose | Fast, repeatable handling | Careful reasoning under uncertainty |
| Trigger | Clear request, complete evidence, low risk | Ambiguity, conflict, medical risk, safeguarding, exceptions |
| Memory | Mubit provides limited context | Mubit provides richer memory context |
| Reasoning | Deterministic rules | Nemotron-led reasoning |
| Output | Fast triage decision | Reasoned recommendation |
| Latency target | Immediate | Higher, but bounded |
| Human review | Only for policy-required cases | Often required for high-risk cases |
| Example | “No drinking water, address known” → welfare route | “Elderly person immobile, oxygen dependent, location unclear” → rescue + medical reasoning |

## Decision router

The Decision Router is the component that combines outcomes.

It:

1. Receives the System 1 or System 2 outcome.
2. Applies the final policy and safeguarding rules.
3. Checks whether human approval is required.
4. Returns one of:
   - Ask next question.
   - Create provisional dispatch.
   - Escalate to supervisor.
   - Finalize case.
   - Request more evidence.

```text
System 1 outcome ─┐
                  ├──▶ Decision Router ──▶ Next action
System 2 outcome ─┘
```

## Memory ownership

Memory retrieval belongs to **Mubit**.

```text
BaanSafe Call Agent
        │
        ▼
   Mubit Gateway
        │
        ├── Retrieve similar cases
        ├── Retrieve prior failures
        ├── Retrieve relevant policies
        ├── Retrieve corrections
        └── Return memory context
        │
        ├──▶ System 1
        └──▶ System 2
```

BaanSafe does not need a separate memory-retrieval service in front of Mubit. The call agent sends the live case state to Mubit; Mubit retrieves the relevant memory and provides it to whichever system handles the case.

## Ontology, revised

The ontology stays largely the same, but memory retrieval is explicitly a Mubit capability.

```text
Person ──▶ Request ──▶ Case ──▶ Decision ──▶ Outcome
   │          │          │                       │
   ▼          ▼          ▼                       ▼
Household  Evidence   Need / Resource          Failure
   │                     │                       │
   ▼                     ▼                       ▼
Location              AidPolicy              Correction
   │                                             │
   ▼                                             ▼
 Hazard                                      MemoryRecord
                                               │
                                               ▼
                                     Retrieved by Mubit Gateway
```

### Memory relationships

```text
MemoryRecord
  ├── describes ──────────────▶ Case
  ├── contains ───────────────▶ Evidence
  ├── records ────────────────▶ Decision
  ├── captures ───────────────▶ Outcome
  ├── identifies ─────────────▶ Failure
  └── supports ───────────────▶ Correction

Mubit Gateway
  ├── retrieves ──────────────▶ MemoryRecord
  ├── provides_context_to ────▶ System 1
  ├── provides_context_to ────▶ System 2
  └── writes ─────────────────▶ MemoryRecord
```

## Corrected two-person split

| Area | Person A | Person B |
|---|---|---|
| Call agent | Live call UX, transcript, operator controls, dispatch view | Aid caseworker view, policy dashboard |
| Mubit Gateway | API gateway, routing to System 1/System 2, trace logging | Memory schemas, retrieval behaviour, correction memory |
| System 1 | Fast triage rules, deterministic routing, simple outcomes | Aid eligibility fast checks |
| System 2 | Complex triage and medical reasoning | Exception reasoning, correction proposals, replay |
| Nemotron | System 2 orchestration for response cases | System 2 orchestration for aid and correction cases |
| Evaluation | Triage and dispatch replay | Aid, exclusion, and correction replay |

## Guardrails

- Mubit does not reason; it governs access, memory, policy, tracing, and routing.
- System 1 does not handle ambiguous or high-risk cases.
- System 2 does not handle routine low-risk routing.
- Nemotron orchestrates System 2; it is not embedded inside Mubit.
- Every System 1 and System 2 outcome is separately recorded.
- The Decision Router merges outcomes and enforces the final policy.
- Humans retain authority over denials, safeguarding exceptions, and irreversible actions.

## Corrected positioning

> **Mubit governs memory, policy, and traceability. System 1 acts fast. System 2 reasons deeply with Nemotron as its orchestrator. The Decision Router turns their outcomes into one safe next action.**
