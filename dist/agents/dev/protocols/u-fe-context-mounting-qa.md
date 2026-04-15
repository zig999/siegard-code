## Context Mounting — QA & Docs

**Agent:** `.claude/agents/dev/u-fe-qa-docs.md`

### Activation prompt structure

QA operates in sequential flow (test-gate followed by full mode) within a single invocation. Mount the context to support both modes:

```
Read in parallel:
- CLAUDE.md
- [relevant data — see extraction below]
- .claude/agents/dev/u-fe-qa-docs.md

[task instruction]
```

> **Note:** the skills `u-fe-qa-docs` and `u-fe-standards` are embedded in the agent's system prompt (`u-fe-qa-docs.md`). **DO NOT** re-inject them in the activation prompt.

### Context extraction (token reduction)

Copy into the prompt:
```
## Target Task Contract (extracted from backlog.md)
[complete TC-XX block: title, narrative, acceptance criteria, type, estimate, dependencies, affected components]
[execution_contract YAML block — QA reads validation.criteria for self-validation checks Developer declared]

## Feature Spec — BDD Scenarios (primary verification criterion)
[§9 BDD Scenarios from the .feature.spec.md of the Task Contract's route]
[feature invariants — Task Contract is rejected if any §9 scenario is broken, regardless of Task Contract AC status]

## Delivery gate (extracted from tc-XX-delivery.md — first YAML block)
[full delivery-gate YAML: status, spec_consumed, tests, acceptance_criteria, spec_divergences, tech_debt, qa_ready, qa_notes]

## Delivery body (extracted from tc-XX-delivery.md — second YAML block)
[full delivery-body YAML: files_created, files_modified, acceptance_criteria_coverage, edge_cases, inference_log]

## Round: N
[1 if first time, 2+ if retest — include previous tc-XX-qa.md if round 2+]
```

**Include conditionally — if the Task Contract creates or modifies a shared component:**
```
## Component Spec — BDD Scenarios
[§7 BDD Scenarios from {SPECS_DIR}/front/components/{name}.component.spec.md]
[validate the component in isolation before feature-level verification]
```

**Always include when {SPECS_DIR}/decisions.md exists:**
```
## Active Decisions (filtered — from {SPECS_DIR}/decisions.md)
[only DEC-NN entries with Status: Active that affect this Task Contract's route or components]
[QA uses these to validate that the implementation respects active architectural decisions]
[if decisions.md does not exist: omit this section]
```

> **Instruction to QA:** §9 BDD Scenarios are the primary verification criterion. Step 1 of full mode: verify all §9 scenarios pass before checking Task Contract acceptance criteria. Step 2: validate Task Contract-level AC (existing flow). A Task Contract cannot be Approved if any §9 BDD scenario is broken.

### Design System (context for QA)

QA needs to validate visual compliance but does not need the full catalog.

**Always include:**
```
## Design System — Rules (extracted from {SPECS_DIR}/front/design-system-rules.md)
[full content — QA validates that tokens are being used correctly]
```

**Include conditionally:**

| Task Contract type | Additional file |
|---|---|
| Visual adjustment | `design-system/implementation.md` (QA checklist) |
| Task Contract with new visual components | `design-system/components.md` (catalog to validate slots/states) |
