# /u-dev -- Development Command

Orchestrates a complete development session with planning, implementation, and QA.

## Usage

```
/u-dev [SPECS_DIR] [SESSIONS_DIR] {SESSION}
/u-dev [SPECS_DIR] {SESSION}
```

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

The pipeline is selected automatically based on the `domain:` field in CLAUDE.md (`frontend`, `backend`, or `fullstack`).

In fullstack mode, a **Meta-Orchestrator** coordinates both phases sequentially -- backend runs first so that API contracts are implemented and tested before frontend consumes them. Each phase delegates to the existing domain orchestrators, which retain full autonomy.

## Mode detection

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Spec-first** | Approved specs exist in `{SPECS_DIR}` | Full pipeline with spec-anchored Task Contracts |
| **Improve** | `improve##.md` exists in `{SESSIONS_DIR}/{SESSION}/` | Task Contracts generated from improvement requests |
| **Bug** | `bug##.md` exists in `{SESSIONS_DIR}/{SESSION}/` | Bug fix pipeline (lean or full based on type) |
| **Bug+Improve** | Both `improve##.md` and `bug##.md` exist | Bugs processed first, then improvements |
| **Error** | No specs, no improve, no bug artifacts | Halts with guidance on required input |

## Session initialization

Before any agent activation, the orchestrator:
1. Resolves all variables (SPECS_DIR, SESSIONS_DIR, SESSION)
2. Creates the session log:
   - `log-orchestrator-dev.md` for backend/frontend sessions
   - `log-fullstack.md` for fullstack sessions (plus `log-be.md` and `log-fe.md` per phase)
3. Detects operating mode
4. Presents pre-execution estimate with token/time projections
5. Waits for human confirmation before proceeding

## Parallelism

- Up to **3 independent Task Contracts** can be processed in parallel within each phase
- Task Contract status transitions: `Backlog` -> `In development` -> `In testing` -> `Done` -> `Merged`
- The orchestrator never proceeds to the next step without human confirmation
- In fullstack mode, Phase 2 (FE) only starts after Phase 1 (BE) completes

## Scope field (fullstack)

In fullstack sessions, each Task Contract in the backlog includes a `scope:` field (`backend`, `frontend`, or `both`). Task Contracts with `scope: both` are split by the Planner into linked pairs -- one backend and one frontend -- with an explicit dependency (FE depends on BE).

## Estimates

- **Per Task Contract (spec-first)**: ~14K tokens, 10-18 min
- **Per Task Contract (improve)**: ~10K tokens, 8-13 min
- **Fullstack overhead**: E2E integration validation adds ~3K tokens when cross-domain Task Contracts exist
