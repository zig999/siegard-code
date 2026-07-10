---
description: Supervises a running workflow and auto-resumes a stalled phase orchestrator. Runs one supervision tick — detects a stalled orchestrator (active phase, non-terminal tasks, no heartbeat AND no worker activity within the threshold) and, within the resume budget, re-invokes the meta-orchestrator in the foreground. Meant to run on an interval via /loop (attended) or /schedule (unattended). Usage: /u-supervise {workflow_id}
---

## Variable Resolution

Extract from `$ARGUMENTS`:
- **First argument** = `workflow_id` (human-readable identifier; must not contain `/` or `\`)

**Resolving `ORCH_PROJECT_DIR`:** derive from `pwd` at command invocation (absolute path to project root).

**Resolving `workflow_id`:**
1. First argument
2. If not provided: list workflows in `$ORCH_PROJECT_DIR/.orch/sessions/`, then ask which one.

---

## Execution

This command re-invokes the meta-orchestrator, which **requires the Bash tool in the foreground**
(CLAUDE.md — a background/sandboxed context has no Bash and stalls silently). Never spawn the
orchestrator with `run_in_background`. This command IS the foreground driver; the Python tick only
detects and accounts.

### Step 0 — Foreground/Bash preflight (fail-fast `E_NO_BASH`)

```bash
python3 -c "
import sys, json; sys.path.insert(0, '.claude/scripts')
from preflight import check_bash_available
r = check_bash_available()
print(json.dumps({'ok': r.ok, 'reason': r.reason}))
"
```

If `ok` is false (`check_bash_available()` returns an `E_NO_BASH` reason), stop immediately with
`{"status": "blocked", "code": "E_NO_BASH", "reason": "supervisor requires foreground Bash"}`.
Do NOT attempt to re-invoke the orchestrator from a context without Bash — it would stall silently.

### Step 1 — Supervision tick

```bash
python3 .claude/scripts/supervisor_tick.py --workflow-id <workflow_id>
```

Parse the single JSON line: `{resume, escalate, phase, workflow_id, reason, budget_remaining}`.
The tick has already appended `orchestrator_resume_requested` (when `resume=true`) or the
`E23_resume_budget_exhausted` escalation (when `escalate=true`) — deterministically, in Python.

### Step 2 — Act on the decision

| Field | Action |
|-------|--------|
| `resume == true` | Go to Step 3 (re-invoke). |
| `escalate == true` | The run is now `escalated` (budget exhausted). Surface the E23 escalation to the human and **stop** — a persistently stuck workflow needs human attention, not another auto-resume. It clears only via `human_response` (a later manual `/u-orchestrator` also sees `escalated` and stops). |
| neither (`resume == false`) | Report `{"status": "ok", "action": "none", "reason": <reason>}` and stop. The interval driver will tick again later. |

### Step 3 — Re-invoke the meta-orchestrator (foreground)

**Race re-check (mandatory — close the window between the tick and the re-invoke):** re-derive
state and confirm the stall is still real before spawning:

```bash
python3 .claude/skills/orch-state/scripts/reduce.py
```

If the current phase now shows an `orchestrator_heartbeat` (or any task activity) newer than the
`orchestrator_resume_requested` just appended, the orchestrator recovered on its own — **skip the
re-invoke**, do NOT emit `orchestrator_resumed`, report `{"status": "ok", "action": "recovered"}`,
and stop.

Otherwise re-invoke the meta-orchestrator exactly as `/u-orchestrator` does — read
`.claude/agents/orchestrator.md` and invoke it (foreground, NOT `run_in_background`) with:
- `ORCH_PROJECT_DIR` = absolute project root (from `pwd`)
- `workflow_id` = value resolved above

The engine re-derives from the intact log and resumes dispatch (non-destructive — this is UC-08
resume, NOT the destructive `verify_and_recover`, which stays manual).

After the orchestrator returns, record the resume for budget accounting:

```bash
python3 .claude/skills/orch-log/scripts/append.py --agent supervisor \
  --event-type orchestrator_resumed --data '{"phase":"<phase>","workflow_id":"<workflow_id>"}'
```

Report `{"status": "ok", "action": "resumed", "phase": "<phase>", "orchestrator_status": <returned>}`.

---

## Running on an interval

- **Attended:** `/loop 20m /u-supervise <workflow_id>` — re-runs this tick every 20 min in the
  foreground session. Keep the interval coherent with `ORCHESTRATOR_STALE_SECONDS` (900s) so ticks
  are not redundant.
- **Unattended:** schedule `/u-supervise <workflow_id>` as a cloud/cron agent — each run is a fresh
  foreground session (with Bash), so Step 0 passes. Budget + cooldown + in-flight TTL
  (`supervisor_policy` in `.orch/config.json`) bound how often it acts and guarantee it escalates
  to a human instead of looping forever.
