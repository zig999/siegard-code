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
```

If `improve##.md` also exist, include:
```
## Requested incremental improvements
[content of each improve##.md]
```

> **Instruction to the Planner (Spec-first):** "Approved specs available. Use UCs as the basis for Stories — each Story must reference UC-NN in the 'Technical notes' section. Use the glossary for naming. Dependencies between domains must be reflected as dependencies between Epics/Stories."

#### Improve mode (without {SPECS_DIR})

All `improve##.md` concatenated in the prompt, in numeric order.

> **Additional instruction:** "Generate the backlog from the improvements listed below. Each improvement may generate one or more User Stories. Group into Epics when thematically appropriate. Keep the scope lean — these are incremental improvements, not full features."

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

> **Instruction to the Planner (Bug):** "Generate one Bugfix Story per bug. Type: `Bugfix`. Priority: blocking bugs = P0, visible = P1, cosmetic = P2. Each Story must reference `Origin: bug##.md`. If specs exist and the bug affects a specified domain, reference the affected UC-NN. Branch: `fix/US-XX`."

#### Bug + Improve mode

Bugs first, then improvements:
```
## Reported bugs (priority: process first)
[content of each bug##.md]
---
## Incremental improvements (priority: process after)
[content of each improve##.md]
```

> **Instruction to the Planner (Bug + Improve):** "Process bugs first as P0/P1 Stories, then improvements as P1/P2. Bugfix Stories never depend on Improve Stories. The reverse is allowed."

#### Resumption (any mode)

Only Epic sections not yet present in the backlog + specs from the relevant domain (if {SPECS_DIR} exists).
