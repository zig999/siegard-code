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
## Target Story (extracted from backlog.md)
[complete US-XX block: title, narrative, acceptance criteria, type, estimate, dependencies, affected components]

## Tests written (extracted from us-XX-delivery.md)
[test file list from the "Tests written" section]

## Round: N
[1 if first time, 2+ if retest — include previous diagnosis/QA report if round 2+]
```

### Design System (context for QA)

QA needs to validate visual compliance but does not need the full catalog.

**Always include:**
```
## Design System — Rules (extracted from {SPECS_DIR}/front/design-system-rules.md)
[full content — QA validates that tokens are being used correctly]
```

**Include conditionally:**

| Story type | Additional file |
|---|---|
| Visual adjustment | `design-system/implementation.md` (QA checklist) |
| Story with new visual components | `design-system/components.md` (catalog to validate slots/states) |
