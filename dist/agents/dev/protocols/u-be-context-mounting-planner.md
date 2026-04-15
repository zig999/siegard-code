## Context Mounting — Planner (Backend)

**Agent:** `.claude/agents/dev/u-be-planner.md`

### Activation prompt structure

```
Read in parallel:
- CLAUDE.md
- [relevant data — see extraction below]
- .claude/agents/dev/u-be-planner.md

[task instruction]
```

> **Note:** the skill `u-planning` is embedded in the agent's system prompt (`u-be-planner.md`). **DO NOT** re-inject it in the activation prompt.

### Context extraction (token reduction)

**Based on the operating mode:**

#### Spec-first mode ({SPECS_DIR} exists with approved domains)

Copy into the prompt:
```
## Approved specs

### Domain: {domain}
[section 3 "Use Cases" from {domain}.spec.md — all UCs with flows]
[section 7 "Domain Dependencies" from {domain}.spec.md]

### Glossary (extracted from {SPECS_DIR}/_global/glossary.md)
[full content]

## Active Decisions (mandatory — from {SPECS_DIR}/decisions.md)
[all DEC-NN entries with Status: Active — the Planner must not contradict active decisions when creating Task Contracts]
[if decisions.md does not exist: omit this section]
```

If an `improve_scope` block exists in the session log (not yet consumed), include:
```
## Requested incremental improvements
[improve_scope block content extracted from {SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md]
```

> **Instruction to the Planner (Spec-first):** "Approved specs available. Use UCs as the basis for Task Contracts — each Task Contract must reference UC-NN in the 'Technical notes' section. Use the glossary for naming. Dependencies between domains must be reflected as dependencies between Epics/Task Contracts."

#### Improve mode (without {SPECS_DIR})

Extract the `improve_scope` block from `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md` and inject it directly:

```
## Requested incremental improvement (improve_scope block)
[full improve_scope YAML block from the session log]
```

> **Additional instruction:** "Generate the backlog from the improvement scope below. Each task_contract entry maps to one Task Contract. Group into Epics when Task Contracts share the same domain or feature boundary. Keep the scope lean — these are incremental improvements, not full features. Use affected_specs listed in the scope block as the only spec references."

#### Bug mode (bug##.md present)

All `bug##.md` concatenated in the prompt, in numeric order.

```
## Reported bugs

### Bug #01 (extracted from bug01.md)
[full content]
---
### Bug #02 (extracted from bug02.md)
[full content]
```

> **Instruction to the Planner (Bug):** "Generate one Bugfix Task Contract per bug. Type: `Bugfix`. Priority: blocking bugs = P0, visible = P1, cosmetic = P2. Each Task Contract must reference `Origin: bug##.md`. If specs exist and the bug affects a specified domain, reference the affected UC-NN. Branch: `fix/TC-XX`."

#### Bug + Improve mode

Bugs first, then improvements:
```
## Reported bugs (priority: process first)
[content of each bug##.md]
---
## Incremental improvements (priority: process after)
[improve_scope block content extracted from {SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md]
```

> **Instruction to the Planner (Bug + Improve):** "Process bugs first as P0/P1 Task Contracts, then improvements as P1/P2. Bugfix Task Contracts never depend on Improve Task Contracts. The reverse is allowed."

#### Resumption (any mode)

Only Epic sections not yet present in the backlog + specs from the relevant domain (if {SPECS_DIR} exists).
