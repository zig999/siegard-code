# Dev Artifacts

Files generated during the development pipeline.

## Artifacts by agent

### Planner
- **`backlog.md`** (permanent) -- Contains personas, Epics, Task Contracts (TC-XX) with `execution_contract` YAML blocks, status, dependencies, and journey maps

### UI Agent (frontend only)
- **`ui-epic-XX.md`** (archived post-Epic) -- Visual specifications per Epic: screen maps, component tables, state tables, interactions

### Developer
- **`us-XX-delivery.md`** (archived post-Task Contract) -- Delivery file documenting what was implemented, tests written, and spec compliance
- **`us-XX-infra-pending-items.md`** (permanent) -- Infrastructure dependency blockers
- **`us-XX-backend-pending-items.md`** (permanent, frontend only) -- Backend API dependencies

> The `us-XX` prefix is kept for historical compatibility — XX matches the Task Contract sequence number.

### QA & Docs
- **`us-XX-qa.md`** (archived post-Task Contract) -- QA report with test results, coverage, bugs found, and approval/rejection status

### Orchestrator
- **`tech-debt.md`** (permanent) -- Technical debt registry accumulated during the session
- **`log-orchestrator-dev.md`** (permanent) -- Execution log with all actions, statuses, and escalations
- **`log-fullstack.md`** (permanent, fullstack only) -- Meta-orchestrator log tracking phase transitions
- **`log-be.md`** (permanent, fullstack only) -- Backend phase execution log
- **`log-fe.md`** (permanent, fullstack only) -- Frontend phase execution log
- **`handoff-be-to-fe.md`** (permanent, fullstack only) -- Summary of implemented BE endpoints and deviations, consumed by the FE phase
- **`e2e-validation.md`** (permanent, fullstack only) -- E2E integration validation results

## Archive behavior

| Trigger | Artifacts moved to `_temp/` |
|---------|---------------------------|
| Post-Planner | `improve##.md`, `bug##.md` |
| Post-Task Contract (QA approved) | `us-XX-delivery.md`, `us-XX-qa.md` |
| Post-Epic (all Task Contracts done) | `ui-epic-XX.md` |

Permanent artifacts (`backlog.md`, `pending-items`, `tech-debt.md`, logs) are never archived.
