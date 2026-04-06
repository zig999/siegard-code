## Context Mounting — QA & Docs (Backend)

**Agent:** `.claude/agents/dev/u-be-qa-docs.md`

### Activation prompt structure

QA operates in sequential flow (test-gate followed by full mode) within a single invocation. Mount the context to support both modes:

```
Read in parallel:
- CLAUDE.md
- [relevant data — see extraction below]
- .claude/agents/dev/u-be-qa-docs.md

[task instruction]
```

> **Note:** the skills `u-be-qa-docs` and `u-be-standards` are embedded in the agent's system prompt (`u-be-qa-docs.md`). **DO NOT** re-inject them in the activation prompt.

### Context extraction (token reduction)

Copy into the prompt:
```
## Target Story (extracted from backlog.md)
[complete US-XX block: title, narrative, acceptance criteria, type, estimate, dependencies, affected modules]

## Tests written (extracted from us-XX-delivery.md)
[test file table: File | Covers]

## Round: N
[1 if first time, 2+ if retest — include previous diagnosis/QA report if round 2+]
```



### Epic integration mode

Full context — include skills and all Epic artifacts:
```
## Mode: epic-integration

## Target Epic: EPIC-XX — [Name]

## Epic deliveries
[full content of each us-XX-delivery.md from the Epic]

## Epic QA Reports
[full content of each us-XX-qa.md from the Epic]

## Approved domain specs (if they exist)
[relevant endpoints from openapi.yaml for the Epic]
[relevant BRs and STs from .back.md for the Epic]
```

> **Skills in integration mode:** the skills are embedded in the agent's system prompt — do not re-inject. The agent always operates in full mode.
