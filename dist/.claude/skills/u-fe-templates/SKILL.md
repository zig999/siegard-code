---
name: u-fe-templates
description: Canonical artifact templates for frontend dev-phase workers — delivery.md, qa-report.md, session-decisions.md, backend-pending-items.md, ui-epic.md. Consumed by u-fe-developer, u-fe-qa, and u-fe-planner, which read templates by path when producing per-task artifacts. Resource bundle — no scripts. Not user-invocable.
user-invocable: false
---

# u-fe-templates

Resource bundle: frontend dev-phase artifact templates. Templates are read by path (`.claude/skills/u-fe-templates/<file>`); the directory listing is authoritative.

## Index

| Template | Produces | Primary consumer |
|---|---|---|
| `delivery.md` | per-task delivery report | u-fe-developer |
| `qa-report.md` | per-task QA report | u-fe-qa |
| `session-decisions.md` | session decision record | u-fe-developer |
| `backend-pending-items.md` | pending backend items handoff | u-fe-developer |
| `ui-epic.md` | UI epic structure | u-fe-planner |

## Constraints

- Producers MUST resolve every placeholder; none may survive into generated artifacts
- Structural changes here are contract changes for the consuming agents — update both in the same commit
