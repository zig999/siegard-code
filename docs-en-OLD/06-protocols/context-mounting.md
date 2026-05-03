# Context Mounting Protocol

Selectively loads only the artifacts each agent needs, minimizing token usage and improving output quality.

## Why context mounting matters

Loading all artifacts for every agent would waste tokens and degrade output quality. Each agent receives only what it needs to perform its specific task.

## Context per agent

### Spec team

| Agent | Context loaded |
|-------|---------------|
| Writer | Requirement + `_global/conventions.md` + `_global/error-codes.md` + `_global/glossary.md` + templates |
| Reviewer | `openapi.yaml` + `.spec.md` |
| Back Spec | Approved `.spec.md` + `openapi.yaml` + `_global/error-codes.md` |
| Front Spec | All approved `.back.md` + all `openapi.yaml` + `TEMPLATE.feature.spec.md` + `TEMPLATE.component.spec.md` + `TEMPLATE.flow.md` + design system |
| Validator | All artifacts (incremental or final scope) |

### Dev team — Backend

| Agent | Context loaded |
|-------|---------------|
| Planner | Use Cases + glossary + personas + conventions + `decisions.md` (if exists) |
| Developer | `openapi.yaml` + `.back.md` + `error-codes.md` + current Task Contract |
| QA | Code + Task Contract + relevant specs |

### Dev team — Frontend

| Agent | Context loaded |
|-------|---------------|
| Planner | Use Cases + glossary + personas + `feature.spec.md` (§1+§2+§9) + flows + `decisions.md` (**mandatory** if exists — active decisions are constraints for Task Contract generation) |
| UI Agent | Task Contracts + `feature.spec.md` (all sections except §7 and §10) + relevant `component.spec.md` (§2+§3+§5) + design system |
| Developer | `feature.spec.md` (§1 Endpoints + §9 BDD Scenarios) + `ui-epic-XX.md` + `component.spec.md` (§2+§3+§4+§5; §6 Do/Don't read in full) + `openapi.yaml` + filtered `decisions.md` + current Task Contract |
| QA | Code + Task Contract + `feature.spec.md` §9 (primary) + `feature.spec.md` §2/§3/§5/§6 + `component.spec.md` §7 (if applicable) + design system |

### Fullstack sessions

In fullstack mode, context mounting follows the same per-agent rules above. The Meta-Orchestrator additionally provides:
- **BE orchestrator**: receives the scope filter instruction (process only `scope: backend` stories)
- **FE orchestrator**: receives the scope filter instruction (process only `scope: frontend` stories) plus `handoff-be-to-fe.md` with implemented endpoint details

## What each agent does NOT receive

| Agent | Excluded |
|-------|---------|
| UI Agent | §7 and §10 of feature specs (processed by Planner in gate step) |
| Developer | Full `component.spec.md` — only §2–§5; §6 is read directly. Full `feature.spec.md` — only §1 and §9. |
| Planner | Full feature spec — only §1, §2, §9 (endpoints, states, BDD) |

## Separate protocols

Each agent has its own context-mounting protocol file in the `protocols/` directory:
- `u-be-context-mounting-planner.md`
- `u-be-context-mounting-developer.md`
- `u-be-context-mounting-qa.md`
- `u-fe-context-mounting-planner.md`
- `u-fe-context-mounting-developer.md`
- `u-fe-context-mounting-qa.md`
- `u-fe-context-mounting-ui.md`
- `u-fullstack-coordination.md` (BE→FE handoff and E2E validation)
