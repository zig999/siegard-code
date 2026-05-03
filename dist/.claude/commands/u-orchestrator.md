---
description: Resumes or advances any workflow from its current state in the event log. Invokes the meta-orchestrator and handles phase transitions automatically. Usage: /u-orchestrator {workflow_id} (e.g., /u-orchestrator fix-kpi-card)
---

## Variable Resolution

Extract from `$ARGUMENTS`:
- **First argument** = `workflow_id` (human-readable identifier; must not contain `/` or `\`)

**Resolving `ORCH_PROJECT_DIR`:**
Derive from `pwd` at command invocation (absolute path to project root).

**Resolving `workflow_id`:**
1. First argument
2. If not provided: list existing workflows in `$ORCH_PROJECT_DIR/.orch/sessions/`, then ask: "Which workflow? (existing or new name)"

---

## Execution

Read `.claude/agents/orchestrator.md` before proceeding. This command is a thin wrapper — all routing logic lives in the meta-orchestrator.

Invoke the meta-orchestrator (`.claude/agents/orchestrator.md`) with:
- `ORCH_PROJECT_DIR` = absolute path to the project root (resolved from `pwd`)
- `workflow_id` = value resolved above — scopes the session to `$ORCH_PROJECT_DIR/.orch/sessions/<workflow_id>`

### Re-invocation loop

The orchestrator handles one phase per invocation. After each call, evaluate the returned status:

| Returned status | Action |
|-----------------|--------|
| `phase_advanced` | Show one-line status (`Phase {completed_phase} complete → entering {next_phase}`), then **re-invoke the orchestrator immediately** with the same parameters. |
| `escalated` | Surface the escalation to the human. Stop — await human response before re-invoking. |
| `completed` | Show the completion report. Stop. |
| `blocked` | Surface the blocked report to the human. Stop. |
| `error` | Surface the error to the human. Stop. |

**Safety limit:** re-invoke at most 10 times. If the loop reaches 10 iterations without a terminal status, stop and report: `{"status": "error", "reason": "reinvocation_limit_reached", "iterations": 10}`.
