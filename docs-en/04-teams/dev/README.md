# Dev Team

The Dev Team implements code from approved specifications, improvements, or bug reports. It exists in two variants -- frontend and backend -- automatically selected by the orchestrator based on the project's `domain:` field.

## Agents

| Agent | Role | FE | BE | Input | Output |
|-------|------|----|----|-------|--------|
| **[Orchestrator](orchestrator.md)** | Pipeline coordination | Yes | Yes | Mode + artifacts | `log-orchestrator-dev.md` |
| **[Planner](planner.md)** | Backlog generation | Yes | Yes | Specs / improve / bug | `backlog.md` |
| **[UI Agent](ui-agent.md)** | Visual specification | Yes | -- | Stories + screens + flows | `ui-epic-XX.md` |
| **[Developer](developer.md)** | Code implementation | Yes | Yes | Story + spec artifacts | Code + `us-XX-delivery.md` |
| **[QA & Docs](qa-docs.md)** | Testing and documentation | Yes | Yes | Code + Story | `us-XX-qa.md` |

## Pipeline

### Backend
```
Planner -> Developer -> QA & Docs
```

### Frontend
```
Planner -> UI Agent -> Developer -> QA & Docs
```

The frontend pipeline includes an additional **UI Agent** step that transforms Stories into detailed visual specifications before the Developer implements them.

## Mode detection

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Spec-first** | Approved specs exist | Full pipeline, Stories anchored to UC-NN |
| **Improve** | `improve##.md` exists | Stories from improvement requests |
| **Bug** | `bug##.md` exists | Bug fix pipeline (lean or full) |
| **Bug+Improve** | Both exist | Bugs first, then improvements |
| **Resume** | Incomplete `log-orchestrator-dev.md` | Resume from last Story status |
| **Error** | No input artifacts | Halts with guidance |

## Story lifecycle

```
Backlog -> In development -> In testing -> Done -> Merged
```

- Max **3 independent Stories** processed in parallel
- QA rejection triggers **rework** (max 3 rounds before escalation)
- After approval, **push-merge** protocol handles git operations
