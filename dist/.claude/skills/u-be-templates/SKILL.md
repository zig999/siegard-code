---
name: u-be-templates
description: Canonical artifact templates for backend dev-phase workers — delivery.md, qa-report.md, session-decisions.md, infra-pending-items.md. Consumed by u-be-developer and u-be-qa, which read templates by path when producing per-task artifacts. Resource bundle — no scripts. Not user-invocable.
user-invocable: false
---

# u-be-templates

Resource bundle: backend dev-phase artifact templates. Templates are read by path (`.claude/skills/u-be-templates/<file>`); the directory listing is authoritative.

## Index

| Template | Produces | Primary consumer |
|---|---|---|
| `delivery.md` | per-task delivery report | u-be-developer |
| `qa-report.md` | per-task QA report | u-be-qa |
| `session-decisions.md` | session decision record | u-be-developer |
| `infra-pending-items.md` | pending infrastructure items handoff | u-be-developer |

## Constraints

- Producers MUST resolve every placeholder; none may survive into generated artifacts
- Structural changes here are contract changes for the consuming agents — update both in the same commit
