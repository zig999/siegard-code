# Protocol: Reverse Feedback from Implementation

## Purpose
Define how the implementation group can report problems in approved specs and how the spec group processes that feedback. Without this flow, infeasible specs would remain as "source of truth" even when technical reality contradicts them.

## Principle
The spec prevails over code **until a reverse feedback demonstrates technical infeasibility or ambiguity**. In that case, the spec is updated — the code does not silently work around the spec.

## Feedback Types

### 1. Technical infeasibility
**What it is:** The implementation encountered a technical constraint that makes the spec impossible or impractical.
**Examples:**
- Database does not support the specified query type
- External integration latency makes synchronous flow infeasible
- Framework limitation prevents the specified architectural pattern

**Flow:**
```
Implementation reports infeasibility
  |
  v
Orchestrator opens CR (Change Request) with:
  - CR-NN in the log
  - Affected domain
  - Description of the technical constraint
  - Evidence (log, benchmark, framework doc)
  - Suggested alternative (if any)
  |
  v
Spec Writer receives CR + technical context
  - Rewrites the spec considering the constraint
  - Increments version (minor or major based on impact)
  |
  v
Spec Reviewer reviews the change
  |
  v
Spec Validator revalidates
  |
  v
New package delivered to the implementation group
```

### 2. Spec ambiguity
**What it is:** The spec is syntactically correct but semantically ambiguous — the implementation is not sure what to do.
**Examples:**
- "The user should be notified" — by email? push? in-app?
- "Sensitive data must be protected" — encryption? masking? RBAC?

**Flow:**
```
Implementation reports ambiguity
  |
  v
Orchestrator directs to Spec Writer with:
  - Exact spec excerpt that is ambiguous
  - Specific question about expected behavior
  |
  v
Spec Writer clarifies the spec
  - Rewrites the excerpt with objective language
  - Increments version (patch)
  |
  v
Spec Reviewer validates the clarification
  |
  v
Diff delivered to the implementation group
```

### 3. Improvement suggestion
**What it is:** The implementation identifies an improvement opportunity that the spec did not anticipate.
**Examples:**
- "If we add cache to this endpoint, latency drops 80%"
- "We can consolidate these 3 endpoints into 1 with filters"

**Flow:**
```
Implementation suggests improvement
  |
  v
Orchestrator evaluates impact:
  |
  +--> Low impact + high value --> Fast-track
  |
  +--> High impact --> Register for next version (in backlog-future in out-of-scope)
  |
  +--> Out of scope --> Register in out-of-scope.md for the domain
```

### Out-of-scope Registry

Suggestions classified as "high impact (next version)" or "out of scope" must be registered in `{SPECS_DIR}/domains/{domain}/out-of-scope.md`. This file is permanent and accumulates suggestions over time.

Create the file if it does not exist. Format:

```markdown
# Out of Scope — {domain}

## Deferred Suggestions

| # | Date | Type | Description | Origin | Reason | Status |
|---|------|------|-------------|--------|--------|--------|
| 1 | {YYYY-MM-DD} | next-version | Consolidate 3 endpoints into 1 | feedback-03.md | High impact, requires redesign | PENDING |
| 2 | {YYYY-MM-DD} | out-of-scope | Add distributed cache | feedback-05.md | Outside auth domain scope | PENDING |
```

**Rules:**
- Sequential numbering (next available number)
- `Origin` must reference the `feedback-NN.md` that originated the suggestion
- `Status`: PENDING (not evaluated), INCORPORATED (became a demand), DISCARDED (rejected with reason)
- When starting a new domain version, the Spec Orchestrator must read `out-of-scope.md` and ask the human which PENDING items to incorporate

## Feedback Format and Persistence

The implementation group must **generate a feedback file** in `{SESSIONS_DIR}/{SESSION}/` named `feedback-NN.md` (sequential numbering: `feedback-01.md`, `feedback-02.md`, etc.).

The Orchestrator-Dev is responsible for generating this file when the Developer reports a problem. The file follows this format:

```markdown
# Feedback: {domain}
> Type: infeasibility | ambiguity | suggestion
> From: {back|front} | Priority: {P0|P1|P2}
> Date: {YYYY-MM-DD}
> Status: PENDING | PROCESSED | REJECTED

## Context
{What was being implemented — Story, Epic, referenced UC}

## Problem
{Objective description of the problem found}

## Evidence
{Logs, benchmarks, framework documentation, etc.}

## Affected spec excerpt
{Copy the exact excerpt with file path and section}

## Suggested alternative
{If any}
```

### Persistence rules
- Save in `{SESSIONS_DIR}/{SESSION}/feedback-NN.md` (same directory as the dev session)
- Sequential numbering (detect the last existing number)
- Status `PENDING` on creation — updated to `PROCESSED` by the Spec Orchestrator after processing the CR
- Never overwrite existing feedback
- After processing, move to `{SESSIONS_DIR}/{SESSION}/_temp/` (via cleanup protocol)

## Feedback Priority

| Priority | Criterion | SLA |
|----------|----------|-----|
| **P0** | Blocking — implementation stopped | Process immediately, before new requirements |
| **P1** | Important — temporary workaround possible | Process in the next cycle |
| **P2** | Desirable — implementation can proceed as is | Evaluate for next version |

## Traceability

Every processed feedback generates:
1. Entry in the Orchestrator log
2. CR-NN if it resulted in a spec change
3. Entry in the Changelog of affected files with reference to the CR
