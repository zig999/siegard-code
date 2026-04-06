# Cleanup Protocol

Archives temporary artifacts after they have been consumed. Never deletes -- always moves to `_temp/`.

## Cleanup triggers

| Trigger | Artifacts archived |
|---------|-------------------|
| **Post-Planner** | `improve##.md`, `bug##.md` -> `_temp/` |
| **Post-Story** | `us-XX-delivery.md`, `us-XX-qa.md` -> `_temp/` |
| **Post-Epic** | `ui-epic-XX.md` -> `_temp/` |

## What is NOT archived

These artifacts remain in place permanently:
- `backlog.md` -- Story tracking reference
- `us-XX-pending-items.md` -- Infrastructure/dependency blockers
- `tech-debt.md` -- Technical debt registry
- `log-orchestrator-dev.md` -- Execution log

## Archive directory

`{SESSIONS_DIR}/{SESSION}/_temp/` -- All archived artifacts are moved here with their original filenames preserved.

## Why archive instead of delete?

Archived artifacts serve as an audit trail and can be referenced for debugging or post-mortem analysis.
