# Dev Orchestrator

Central coordinator of the Dev team. Exists in three variants:
- `u-be-orchestrator-core.md` -- Backend orchestrator
- `u-fe-orchestrator-core.md` -- Frontend orchestrator
- `u-fullstack-orchestrator.md` -- Fullstack meta-orchestrator

The backend and frontend orchestrators share the same core logic but differ in pipeline (FE includes UI Agent) and context-mounting protocols. The fullstack meta-orchestrator coordinates both by running them sequentially.

## Responsibilities

- Detect operating mode (spec-first, improve, bug, resume)
- Validate inputs and resolve variables
- Manage agent handoff and Story lifecycle
- Track progress in session logs
- Emit execution plan and progress panel before each step
- Never proceed without human confirmation

## Mode detection logic

1. Check for approved `{SPECS_DIR}` with `status: approved` -> **Spec-first**
2. Check for `improve##.md` in `{SESSIONS_DIR}/{SESSION}/` -> **Improve**
3. Check for `bug##.md` in `{SESSIONS_DIR}/{SESSION}/` -> **Bug**
4. Check for both -> **Bug+Improve** (bugs processed first)
5. Check for incomplete session log -> **Resume**
6. None found -> **Error** (halt with guidance)

## Execution flow

### Backend / Frontend
```
1. Resolve variables (SPECS_DIR, SESSIONS_DIR, SESSION)
2. Create session log (log-orchestrator-dev.md)
3. Detect mode
4. Present pre-execution estimate
5. Wait for human confirmation
6. Activate Planner (context: specs + mode artifacts)
7. [FE only] Activate UI Agent (context: Stories + screens + flows)
8. For each Story:
   a. Activate Developer (context: Story + relevant specs)
   b. Activate QA (context: code + Story + specs)
   c. If REJECTED: rework cycle (max 3)
   d. If APPROVED: push-merge protocol
   e. Cleanup temporary artifacts
9. When Epic complete: epic-integration protocol
10. Log completion
```

### Fullstack
```
1. Resolve variables (SPECS_DIR, SESSIONS_DIR, SESSION)
2. Create session log (log-fullstack.md)
3. Detect mode
4. Activate Planner with unified backlog (stories tagged with scope:)
5. Phase 1 -- Backend: delegate to u-be-orchestrator-core
   (processes scope: backend and scope: both BE portions)
6. Generate handoff-be-to-fe.md (implemented endpoints, deviations)
7. Phase 2 -- Frontend: delegate to u-fe-orchestrator-core
   (processes scope: frontend and scope: both FE portions)
8. Phase 3 -- E2E integration validation (if cross-domain stories exist)
9. Log completion
```

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
- Escalate without blocking
- Max 3 parallel Stories (within each phase for fullstack)
- Long context management for 15+ Story backlogs (compress per-Story logs)
- In fullstack mode, Phase 2 only starts after Phase 1 completes
