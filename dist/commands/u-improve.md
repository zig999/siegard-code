---
description: Receives an improvement task, classifies its spec impact, defines execution scope, and orchestrates handoff to /u-dev. Usage: /u-improve [SESSION] (e.g., /u-improve fix-kpi-card)
---

Read the following file:
1. .claude/skills/u-improve/SKILL.md

## Variable Resolution

Extract from `$ARGUMENTS`:
- **Last argument** = `SESSION`

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in `CLAUDE.md` (project root) → use *(canonical source)*
2. None → **stop**: "Configure `specs_dir:` in CLAUDE.md before continuing."

**Resolving `SESSIONS_DIR` (priority):**
1. `sessions_dir:` field in `CLAUDE.md` (project root) → use *(canonical source)*
2. None → **stop**: "Configure `sessions_dir:` in CLAUDE.md before continuing."

**Resolving `SESSION`:**
1. Last argument (string without `/` or `\`)
2. If not provided: list existing sessions in `{SESSIONS_DIR}`, then ask: "Which session? (existing or new name)"

Create `{SESSIONS_DIR}/{SESSION}/` if it does not exist.

## Execution

Follow the skill execution flow defined in `.claude/skills/u-improve/SKILL.md`.
