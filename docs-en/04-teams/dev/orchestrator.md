# Dev Orchestrator

Central coordinator of the Dev team. Exists in three variants:
- `u-be-orchestrator-core.md` — Backend orchestrator
- `u-fe-orchestrator-core.md` — Frontend orchestrator
- `u-fullstack-orchestrator.md` — Fullstack meta-orchestrator

The backend and frontend orchestrators share the same core logic but differ in pipeline (FE includes UI Agent) and context-mounting protocols. The fullstack meta-orchestrator coordinates both by running them sequentially.

## Responsibilities

- **Validate environment at startup** — confirm CLAUDE.md defines a test command and build command; confirm Git is initialized
- Detect operating mode (spec-first, improve, bug, resume)
- Validate inputs and resolve variables
- **Read `decisions.md` at session start** (before backlog and logs — active decisions take precedence over defaults)
- Manage agent handoff and Task Contract lifecycle
- Track progress in session logs
- Emit execution plan and progress panel before each step
- Never proceed without human confirmation

## Mode detection logic

1. Check for approved `{SPECS_DIR}` with `status: approved` → **Spec-first**
2. Check for `improve##.md` in `{SESSIONS_DIR}/{SESSION}/` → **Improve**
3. Check for `bug##.md` in `{SESSIONS_DIR}/{SESSION}/` → **Bug**
4. Check for both → **Bug+Improve** (bugs processed first)
5. Check for incomplete session log → **Resume**
6. None found → **Error** (halt with guidance)

## Execution flow

### Backend / Frontend
```
1. Resolve variables (SPECS_DIR, SESSIONS_DIR, SESSION)
2. Read {SPECS_DIR}/decisions.md if it exists — log which active decisions apply
3. Create session log (log-orchestrator-dev.md)
4. Detect mode
5. Present pre-execution estimate
6. Wait for human confirmation
7. Activate Planner (context: specs + mode artifacts)
   — Planner runs Step 4B (Component Spec Gate) internally and returns a backlog that may include Spec Task Contracts
8. [FE only] Validate backlog from Planner:
   — Cycle check in dependency map
   — If backlog contains Spec TCs (Type: Spec): confirm with human before proceeding
   — If Planner flagged P0 component gap: wait for human decision
9. [FE only] Activate UI Agent (context: Task Contracts + features + flows)
10. For each Task Contract:
    a. Activate Developer (context: Task Contract + relevant specs)
    b. Activate QA (context: code + Task Contract + specs)
    c. If REJECTED: rework cycle (max 3)
    d. If APPROVED: push-merge protocol
    e. Cleanup temporary artifacts
11. When Epic complete: epic-integration protocol
12. Log completion
```

### Fullstack
```
1. Resolve variables (SPECS_DIR, SESSIONS_DIR, SESSION)
2. Read {SPECS_DIR}/decisions.md if it exists
3. Create session log (log-fullstack.md)
4. Detect mode
5. Activate Planner with unified backlog (Task Contracts tagged with scope:)
6. Phase 1 — Backend: delegate to u-be-orchestrator-core
   (processes scope: backend and scope: both BE portions)
7. Generate handoff-be-to-fe.md (implemented endpoints, deviations)
8. Phase 2 — Frontend: delegate to u-fe-orchestrator-core
   (processes scope: frontend and scope: both FE portions)
9. Phase 3 — E2E integration validation (if cross-domain Task Contracts exist)
10. Log completion
```

## Decisions.md — session-start rule

The Orchestrator reads `{SPECS_DIR}/decisions.md` as the **first file** after resolving variables — before the backlog, before logs. Active decisions that contradict current SKILL defaults take precedence. The Orchestrator logs which DEC-NN entries apply to the current session.

In Improve/Bug mode: when the Orchestrator approves a spec divergence, it writes a new DEC-NN entry in `decisions.md` before push/merge.

## Session logs

| Domain | Log file |
|--------|----------|
| `backend` or `frontend` | `log-orchestrator-dev.md` |
| `fullstack` (meta) | `log-fullstack.md` |
| `fullstack` (BE phase) | `log-be.md` |
| `fullstack` (FE phase) | `log-fe.md` |

## Available protocols

Referenced via the protocol index file (`u-be-orchestrator-protocols.md` / `u-fe-orchestrator-protocols.md`):

- Context mounting (per agent: Planner, Developer, QA, UI Agent)
- Short mode (reduced reactivation)
- Epic integration
- Rework
- Tech debt
- Push/merge
- Cleanup
- Bug mode
- Improve mode
- Fullstack coordination (BE→FE handoff, E2E validation)

## Behavioral rules

- Never skip human confirmation
- Escalate without blocking — continue with independent Task Contracts while waiting for human response
- Max 3 parallel Task Contracts (within each phase for fullstack)
- Large backlogs (15+ Task Contracts): process one Epic at a time, read only Dependency map + statuses
- Short mode for sub-agents from Round 2+ — refer to `u-context-mounting-short-mode.md`
- In fullstack mode, Phase 2 only starts after Phase 1 completes
