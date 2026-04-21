## Context Mounting — Planner

**Agent:** `.claude/agents/dev/u-fe-planner.md`

### Activation prompt structure

```
Read in parallel:
- CLAUDE.md
- [relevant data — see extraction below]
- .claude/agents/dev/u-fe-planner.md

[task instruction]
```

> **Note:** the skill `u-planning` is embedded in the agent's system prompt (`u-fe-planner.md`). **DO NOT** re-inject it in the activation prompt.

### Context extraction (token reduction)

**Based on the operating mode:**

#### Spec-first mode ({SPECS_DIR} exists with approved domains)

Copy into the prompt:
```
## Approved specs

### Domain: {domain}
[section 3 "Use Cases" from {domain}.spec.md — all UCs with flows]
[section 7 "Domain Dependencies" from {domain}.spec.md]

### Feature Specs (extracted from {SPECS_DIR}/front/features/)
[§1 Endpoints + §2 Feature States + §9 BDD Scenarios from each relevant .feature.spec.md]
[exclude §7 Shared Components and §10 Components to Create — processed in Step 4B by the Planner]

### Navigation flows (extracted from {SPECS_DIR}/front/_flows/)
[content of relevant .flow.md — happy and alternative flows]

### Glossary (extracted from {SPECS_DIR}/_global/glossary.md)
[full content]

### Decisions (extracted from {SPECS_DIR}/decisions.md — MANDATORY if file exists)
[full content — do not filter; Planner must read all Active entries before generating Task Contracts]
```

If an `improve_scope` block exists in the session log (not yet consumed), include:
```
## Requested incremental improvements
[improve_scope block content extracted from {SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md]
```

> **Instruction to the Planner (Spec-first):** "Approved specs available. Use UCs as the basis for Task Contracts — each Task Contract must reference UC-NN in the 'Technical notes' section. Feature specs (feature.spec.md) are the frontend behavioral source — use §2 States and §9 BDD Scenarios as the basis for acceptance criteria. Do NOT duplicate §9 BDD Scenarios into Task Contracts — reference them as 'per FEAT-NN §9'. Use navigation flows (.flow.md) for user journeys. Use the glossary for naming. Dependencies between domains must be reflected as dependencies between Epics/Task Contracts. **Active decisions from decisions.md are hard constraints — they take precedence over SKILL defaults. Do not generate Task Contracts that contradict an Active DEC-NN entry.**"

#### Improve mode (without {SPECS_DIR})

Extract the `improve_scope` block from `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md` and inject it directly:

```
## Requested incremental improvement (improve_scope block)
[full improve_scope YAML block from the session log]
```

> **Additional instruction:** "Generate the backlog from the improvement scope below. Each task_contract entry maps to one Task Contract. Group into Epics when Task Contracts share the same domain or feature boundary. Keep the scope lean — these are incremental improvements, not full features. Use affected_specs listed in the scope block as the only spec references."

#### Bug fix (improve_scope describes broken behavior)

Every change now flows through `/u-improve`, including bug fixes. The Planner reads the `improve_scope.description` — when it describes broken behavior (e.g., text contains `not working`, `broken`, `fails`, `wrong`), generate a Task Contract with:
- Type: `Bugfix`
- Priority default: P0 for blocking, P1 for visible, P2 for cosmetic (derived from `improve_scope.description` severity and whether `execution_policy.pipeline: lean`)
- `Origin: improve`
- Branch: `fix/TC-XX`
- Enforce TDD when `improve_scope.execution_policy.regression_test_required: true`

#### Resumption (any mode)

Only Epic sections not yet present in the backlog + specs from the relevant domain (if {SPECS_DIR} exists).
