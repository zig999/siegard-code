# Dev Team

The Dev Team implements code from approved specifications, improvements, or bug reports. It exists in three variants -- frontend, backend, and fullstack -- automatically selected by the orchestrator based on the project's `domain:` field.

## Agents

| Agent | Role | FE | BE | Fullstack | Input | Output |
|-------|------|----|----|-----------|-------|--------|
| **[Orchestrator](orchestrator.md)** | Pipeline coordination | Yes | Yes | Meta | Mode + artifacts | Session logs |
| **[Planner](planner.md)** | Backlog generation | Yes | Yes | Yes | Specs / improve / bug | `backlog.md` |
| **[UI Agent](ui-agent.md)** | Visual specification | Yes | -- | Phase 2 | Stories + screens + flows | `ui-epic-XX.md` |
| **[Developer](developer.md)** | Code implementation | Yes | Yes | Yes | Story + spec artifacts | Code + `us-XX-delivery.md` |
| **[QA & Docs](qa-docs.md)** | Testing and documentation | Yes | Yes | Yes | Code + Story | `us-XX-qa.md` |

## Pipeline

### Backend (`domain: backend`)
```
Planner -> Developer -> QA & Docs
```

### Frontend (`domain: frontend`)
```
Planner -> UI Agent -> Developer -> QA & Docs
```

### Fullstack (`domain: fullstack`)
```
Phase 1 (BE): Planner -> Developer -> QA & Docs
Phase 2 (FE): Planner -> UI Agent -> Developer -> QA & Docs
Phase 3 (optional): E2E Integration Validation
```

The frontend pipeline includes an additional **UI Agent** step that transforms Stories into detailed visual specifications before the Developer implements them.

In fullstack mode, a **Meta-Orchestrator** coordinates both domain pipelines sequentially. Backend runs first so that API contracts are implemented before frontend consumes them. Each phase delegates to the existing domain orchestrators unchanged.

## Mode detection

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Spec-first** | Approved specs exist | Full pipeline, Stories anchored to UC-NN |
| **Improve** | `improve##.md` exists | Stories from improvement requests |
| **Bug** | `bug##.md` exists | Bug fix pipeline (lean or full) |
| **Bug+Improve** | Both exist | Bugs first, then improvements |
| **Resume** | Incomplete session log | Resume from last Story status |
| **Error** | No input artifacts | Halts with guidance |

## Story lifecycle

```
Backlog -> In development -> In testing -> Done -> Merged
```

- Max **3 independent Stories** processed in parallel (within each phase for fullstack)
- QA rejection triggers **rework** (max 3 rounds before escalation)
- After approval, **push-merge** protocol handles git operations
- In fullstack mode, each Story includes a `scope:` field (`backend`, `frontend`, or `both`) that determines which phase processes it
