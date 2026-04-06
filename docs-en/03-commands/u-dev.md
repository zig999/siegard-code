# /u-dev -- Development Command

Orchestrates a complete development session with planning, implementation, and QA.

## Usage

```
/u-dev [SPECS_DIR] [SESSIONS_DIR] {SESSION}
/u-dev [SPECS_DIR] {SESSION}
```

## Pipeline

### Backend
```
Planner -> Developer -> QA & Docs
```

### Frontend
```
Planner -> UI Agent -> Developer -> QA & Docs
```

The pipeline is selected automatically based on the `domain:` field in CLAUDE.md.

## Mode detection

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Spec-first** | Approved specs exist in `{SPECS_DIR}` | Full pipeline with spec-anchored Stories |
| **Improve** | `improve##.md` exists in `{SESSIONS_DIR}/{SESSION}/` | Stories generated from improvement requests |
| **Bug** | `bug##.md` exists in `{SESSIONS_DIR}/{SESSION}/` | Bug fix pipeline (lean or full based on type) |
| **Bug+Improve** | Both `improve##.md` and `bug##.md` exist | Bugs processed first, then improvements |
| **Error** | No specs, no improve, no bug artifacts | Halts with guidance on required input |

## Session initialization

Before any agent activation, the orchestrator:
1. Resolves all variables (SPECS_DIR, SESSIONS_DIR, SESSION)
2. Creates `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md`
3. Detects operating mode
4. Presents pre-execution estimate with token/time projections
5. Waits for human confirmation before proceeding

## Parallelism

- Up to **3 independent Stories** can be processed in parallel
- Story status transitions: `Backlog` -> `In development` -> `In testing` -> `Done` -> `Merged`
- The orchestrator never proceeds to the next step without human confirmation

## Estimates

- **Per Story (spec-first)**: ~14K tokens, 10-18 min
- **Per Story (improve)**: ~10K tokens, 8-13 min
