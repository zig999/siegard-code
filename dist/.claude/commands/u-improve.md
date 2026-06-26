---
description: Receives an improvement task, classifies its spec impact, persists scope to the session log (write-before-confirm), and auto-invokes the spec pipeline when needed. Usage: /u-improve [workflow_id] ["improvement task"] (e.g., /u-improve fix-kpi-card "tighten error states on KPI card")
---

Read the following file:
1. .claude/skills/u-improve/SKILL.md

## Variable Resolution

Extract from `$ARGUMENTS`:
- **Quoted string** = `IMPROVEMENT_TASK` (optional — natural-language description of the improvement)
- **Last non-quoted argument** = `workflow_id` (human-readable identifier for this workflow; must not contain `/` or `\`)
- **`--recalculate` flag** = `RECALCULATE_MODE` (optional — re-derives classification from existing session without restarting)

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in `CLAUDE.md` (project root) → use *(canonical source)*
2. None → **stop**: "Configure `specs_dir:` in CLAUDE.md before continuing."

**Resolving `ORCH_PROJECT_DIR`:**
Derive from `pwd` at command invocation (absolute path to project root).

**Resolving `workflow_id`:**
1. Last non-quoted argument (string without `/` or `\`)
2. If not provided: list existing workflows in `$ORCH_PROJECT_DIR/.orch/sessions/`, then ask: "Which workflow? (existing or new name)"

> Session directory: `$ORCH_PROJECT_DIR/.orch/sessions/<workflow_id>/` — created automatically by the orchestrator. No manual directory creation needed.

**Resolving `IMPROVEMENT_TASK`:**
1. Quoted string in `$ARGUMENTS` → pass to the SKILL as inline input (skip Step 1 prompt)
2. None → SKILL Step 1 will prompt the human for it

**Resolving `RECALCULATE_MODE`:**
1. `--recalculate` present in `$ARGUMENTS` → `RECALCULATE_MODE = true`
2. Not present → `RECALCULATE_MODE = false`

When `RECALCULATE_MODE = true`:
- `workflow_id` is **required** — stop with error if not provided
- `IMPROVEMENT_TASK` is **ignored** — existing `improvement_task` from session is used
- The SKILL enters Recalculate Mode (see SKILL.md § Recalculate Mode)

## Execution

Follow the skill execution flow defined in `.claude/skills/u-improve/SKILL.md`. The SKILL is responsible for:
- write-before-confirm (Steps 3a/3b run before any human prompt)
- emitting `phase_declared` to `.orch/log.jsonl` when the human types `confirm`
- invoking the meta-orchestrator (`orchestrator`) directly via the Agent tool
- session guard (Step 0) — detecting and blocking silent overwrites of active sessions

This command does not print shell-paste instructions.
