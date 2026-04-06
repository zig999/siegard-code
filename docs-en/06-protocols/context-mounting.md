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
| Front Spec | All approved `.back.md` + all `openapi.yaml` + design system |
| Validator | All artifacts (incremental or final scope) |

### Dev team -- Backend

| Agent | Context loaded |
|-------|---------------|
| Planner | Use Cases + glossary + personas + conventions |
| Developer | `openapi.yaml` + `.back.md` + `error-codes.md` + current Story |
| QA | Code + Story + relevant specs |

### Dev team -- Frontend

| Agent | Context loaded |
|-------|---------------|
| Planner | Use Cases + glossary + personas + conventions + screens + flows |
| UI Agent | Stories + `.screen.md` + `.flow.md` + design system |
| Developer | `ui-epic-XX.md` + `.screen.md` + `.flow.md` + `openapi.yaml` + current Story |
| QA | Code + Story + relevant specs + design system |

## Separate protocols

Each agent has its own context-mounting protocol file in the `protocols/` directory:
- `u-be-context-mounting-planner.md`
- `u-be-context-mounting-developer.md`
- `u-be-context-mounting-qa.md`
- `u-fe-context-mounting-planner.md`
- `u-fe-context-mounting-developer.md`
- `u-fe-context-mounting-qa.md`
- `u-fe-context-mounting-ui.md`
