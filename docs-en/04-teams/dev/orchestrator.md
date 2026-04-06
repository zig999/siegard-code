# Dev Orchestrator

Central coordinator of the Dev team. Exists in two variants:
- `u-be-orchestrator-core.md` -- Backend orchestrator
- `u-fe-orchestrator-core.md` -- Frontend orchestrator

Both share the same core logic but differ in pipeline (FE includes UI Agent) and context-mounting protocols.

## Responsibilities

- Detect operating mode (spec-first, improve, bug, resume)
- Validate inputs and resolve variables
- Manage agent handoff and Story lifecycle
- Track progress in `log-orchestrator-dev.md`
- Emit execution plan and progress panel before each step
- Never proceed without human confirmation

## Mode detection logic

1. Check for approved `{SPECS_DIR}` with `status: approved` -> **Spec-first**
2. Check for `improve##.md` in `{SESSIONS_DIR}/{SESSION}/` -> **Improve**
3. Check for `bug##.md` in `{SESSIONS_DIR}/{SESSION}/` -> **Bug**
4. Check for both -> **Bug+Improve** (bugs processed first)
5. Check for incomplete `log-orchestrator-dev.md` -> **Resume**
6. None found -> **Error** (halt with guidance)

## Execution flow

```
1. Resolve variables (SPECS_DIR, SESSIONS_DIR, SESSION)
2. Create log-orchestrator-dev.md
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

## Behavioral rules

- Never skip human confirmation
- Escalate without blocking
- Max 3 parallel Stories
- Long context management for 15+ Story backlogs (compress per-Story logs)
