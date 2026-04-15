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
## Target Task Contract (extracted from backlog.md)
[complete TC-XX block: title, narrative, acceptance criteria, type, estimate, dependencies, affected modules]
[execution_contract YAML block — QA reads validation.criteria for self-validation checks Developer declared]

## Delivery gate (extracted from tc-XX-delivery.md — first YAML block)
[full delivery-gate YAML: status, spec_consumed, tests, acceptance_criteria, spec_divergences, tech_debt, qa_ready, qa_notes]

## Delivery body (extracted from tc-XX-delivery.md — second YAML block)
[full delivery-body YAML: files_created, files_modified, acceptance_criteria_coverage, edge_cases, inference_log]

## Round: N
[1 if first time, 2+ if retest — include previous tc-XX-qa.md if round 2+]
```



### Epic integration mode

Full context — include skills and all Epic artifacts:
```
## Mode: epic-integration

## Target Epic: EPIC-XX — [Name]

## Epic deliveries
[full content of each tc-XX-delivery.md from the Epic]

## Epic QA Reports
[full content of each tc-XX-qa.md from the Epic]

## Approved domain specs (if they exist)
[relevant endpoints from openapi.yaml for the Epic]
[relevant BRs and STs from .back.md for the Epic]
```

> **Skills in integration mode:** the skills are embedded in the agent's system prompt — do not re-inject. The agent always operates in full mode.
