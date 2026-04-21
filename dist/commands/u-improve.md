---
description: Receives an improvement task, classifies its spec impact, persists scope + handoff envelope to the session log (write-before-confirm), and auto-invokes /u-spec when needed. Usage: /u-improve [SESSION] ["improvement task"] (e.g., /u-improve fix-kpi-card "tighten error states on KPI card")
---

Read the following file:
1. .claude/skills/u-improve/SKILL.md

## Variable Resolution

Extract from `$ARGUMENTS`:
- **Quoted string** = `IMPROVEMENT_TASK` (optional — natural-language description of the improvement)
- **Last non-quoted argument** = `SESSION`

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in `CLAUDE.md` (project root) → use *(canonical source)*
2. None → **stop**: "Configure `specs_dir:` in CLAUDE.md before continuing."

**Resolving `SESSIONS_DIR` (priority):**
1. `sessions_dir:` field in `CLAUDE.md` (project root) → use *(canonical source)*
2. None → **stop**: "Configure `sessions_dir:` in CLAUDE.md before continuing."

**Resolving `SESSION`:**
1. Last non-quoted argument (string without `/` or `\`)
2. If not provided: list existing sessions in `{SESSIONS_DIR}`, then ask: "Which session? (existing or new name)"

**Resolving `IMPROVEMENT_TASK`:**
1. Quoted string in `$ARGUMENTS` (e.g., `"tighten error states"`) → pass to the SKILL as inline input (skip Step 1 prompt)
2. None → SKILL Step 1 will prompt the human for it

Create `{SESSIONS_DIR}/{SESSION}/` if it does not exist.

## Execution

Follow the skill execution flow defined in `.claude/skills/u-improve/SKILL.md`. The SKILL is responsible for write-before-confirm (Steps 3a/3b run before any human prompt) and for invoking `u-spec-orchestrator` directly via the Agent tool when the human types `confirm`. This command does not print shell-paste instructions.
