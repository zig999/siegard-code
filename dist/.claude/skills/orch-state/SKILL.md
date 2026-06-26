---
name: orch-state
description: Reduce the event log to derived state. Provides reduce.py (full OrchState JSON), summary.py (compact summary), current_phase.py (active phase), and detect_mode.py (run mode). Single source of derived state for orchestrators (P1/P2 — log is the truth, state is derived). Not user-invocable — orchestrators run the scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# orch-state

State inspection skill: reduce event log to OrchState, print summaries, query current phase.

## scripts/reduce.py

Replays all events and prints the full `OrchState` as a JSON object. Exit 0 on success, 1 on error.

```bash
python3 .claude/skills/orch-state/scripts/reduce.py
```

Output schema (top-level keys):

| Key | Type | Description |
|-----|------|-------------|
| `workflow_id` | string\|null | Workflow identifier |
| `run_status` | string | `active`, `escalated`, etc. |
| `current_phase` | string\|null | Active phase name |
| `tasks` | object | Map of task_id → TaskState |
| `phases` | object | Map of phase name → PhaseState |
| `escalation` | object\|null | Escalation payload if present |
| `circuit_breaker` | object\|null | Circuit breaker state if present |
| `last_seq` | int | Last event seq processed |
| `last_snapshot_seq` | int | Seq of last snapshot event |

## scripts/summary.py

Prints a human-readable summary to stdout. Not JSON — intended for operator inspection.

```bash
python3 .claude/skills/orch-state/scripts/summary.py
```

Example output:
```
Workflow : wf_001
Status   : active
Phase    : dev
Last seq : 42

Tasks
─────
  pending              ████████░░░░░░░░░░░░    4 / 10
  completed            ██████████████░░░░░░    7 / 10

Tasks by phase
──────────────
  dev                  pending=4, completed=6

Phases
──────
  ▶ 1. dev                  active
    2. qa                   pending
```

## scripts/current_phase.py

Prints the current phase and its status as JSON. Exit 0 always (errors also JSON).

```bash
python3 .claude/skills/orch-state/scripts/current_phase.py
```

Output when a phase is active:
```json
{"current_phase": "dev", "status": "active", "order": 1}
```

Output when no phase has been entered:
```json
{"current_phase": null, "status": null}
```
