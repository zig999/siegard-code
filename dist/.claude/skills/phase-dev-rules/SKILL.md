---
name: phase-dev-rules
description: Exit criteria checkers and worker routing table for the dev (implementation) phase. Consumed by orchestrator-dev.md to dispatch workers via select_worker.py and evaluate phase transition gates (check_all_impl_tasks_terminal, check_all_deliveries_qa_ready, check_no_open_prohibitions). Not user-invocable — orchestrators call scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# phase-dev-rules

Phase rules skill for the `dev` (implementation) phase.
Provides exit criteria checkers and worker routing table consumed by `orchestrator-dev.md`.

## Contract

The orchestrator calls this skill's scripts directly. No inter-skill communication envelope needed.
Every script returns a JSON object to stdout and exits 0 on success or 1 on error.

---

## Phase identity

| Field | Value |
|-------|-------|
| `phase_name` | `dev` |
| `order` | `2` |
| `required` | `true` |
| `worker_default` | `u-be-developer` |

---

## Worker routing table

Maps `task.type` + `stack` to worker sub-agent. Stack is resolved by `orchestrator-dev` from
`handoff-manifest.yaml` before calling this script (Decision D2).

For fullstack projects, orchestrator-dev spawns two planning tasks with explicit split stacks
(`fullstack_be` and `fullstack_fe`) so both planners run in parallel.

| task.type | stack | worker subagent_type |
|-----------|-------|----------------------|
| `planning` | `be` | `u-be-planner` |
| `planning` | `fe` | `u-fe-planner` |
| `planning` | `fullstack_be` | `u-be-planner` |
| `planning` | `fullstack_fe` | `u-fe-planner` |
| `planning` | `fullstack` | `u-be-planner` (legacy fallback) |
| `impl` | `be` | `u-be-developer` |
| `impl` | `fe` | `u-fe-developer` |
| `impl` | `fullstack` | `u-be-developer` |
| `spec` | `be` | `u-be-developer` |
| `spec` | `fe` | `u-fe-spec-writer` |
| `spec` | `fullstack` | `u-fe-spec-writer` |
| `*` (default) | any | `u-be-developer` |

---

## scripts/select_worker.py

Returns the worker sub-agent name for a given task type and stack.

### Usage

```bash
python3 .claude/skills/phase-dev-rules/scripts/select_worker.py \
  --task-type <type> \
  --stack <be|fe|fullstack|fullstack_be|fullstack_fe>
```

### Output (exit 0)

```json
{"worker": "u-be-developer", "task_type": "impl", "stack": "be", "phase": "dev"}
```

### Error (exit 1, stderr)

```json
{"status": "error", "reason": "internal_error", "detail": "<message>"}
```

---

## Exit criteria

All three criteria must be met before the dev phase can transition. DLQ tasks block transition —
a task in DLQ represents a failure, not a completed deliverable.

| Criterion | Script | Description |
|-----------|--------|-------------|
| `all_impl_tasks_terminal` | `scripts/check_all_impl_tasks_terminal.py` | All dev tasks in `completed`; zero DLQ tasks |
| `all_deliveries_qa_ready` | `scripts/check_all_deliveries_qa_ready.py` | Every `delivery.md` has `qa_ready: true` |
| `no_open_prohibitions` | `scripts/check_no_open_prohibitions.py` | No `delivery.md` has a non-empty `prohibition_violations` list |

See `exit-criteria.json` for the machine-readable declaration.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCH_PROJECT_DIR` | `.` | Project root — used to resolve delivery.md artifact paths |

---

## scripts/check_backlog_scope.py

Post-planner backlog scope guard (L4) — NOT an exit criterion: orchestrator-dev
runs it in Step 4.0, after the planning task completes and BEFORE creating any
impl task. Derives the change scope from triage (`lib/spec_scope.py`, the same
single source as the SDD gates) and scans each Task Contract file for
`domains/<slug>/` references. Blocks when any TC references ONLY out-of-scope
domains — an `/u-improve` must not be re-broadened by planning. Conservative:
scope `None` (u-spec/greenfield) passes trivially; a TC with no domain
references is allowed (cannot attribute); ≥1 in-scope reference is allowed.

```bash
python3 .claude/skills/phase-dev-rules/scripts/check_backlog_scope.py \
  --backlog <session_dir>/backlog/backlog.json --workflow-id <wid>
```

Output (exit 0 ok / exit 1 blocked):
```json
{"status": "ok", "check": "backlog_scope", "scoped": true,
 "scope_domains": ["billing"], "tcs_checked": 4, "violations": [], "unreadable": []}
```

Blocked flow (orchestrator-dev Step 4.0): one planner revision with the
violations injected into the prompt → still blocked → `E22_backlog_scope_violation`.

---

## scripts/check_all_impl_tasks_terminal.py

Criterion: every task in the `dev` phase has status `completed`. DLQ tasks block the criterion
(a failed task is not a deliverable). Not met if there are no dev tasks.

```bash
python3 .claude/skills/phase-dev-rules/scripts/check_all_impl_tasks_terminal.py
```

Output schema:
```json
{
  "criterion": "all_impl_tasks_terminal",
  "met": true,
  "evidence": {
    "total": 10,
    "terminal": 10,
    "non_terminal": [],
    "dlq": [],
    "dlq_blocks_criterion": false
  }
}
```

---

## scripts/check_all_deliveries_qa_ready.py

Criterion: every `delivery.md` artifact path listed in `task_completed` events for the `dev`
phase contains the pattern `qa_ready: true`.

```bash
python3 .claude/skills/phase-dev-rules/scripts/check_all_deliveries_qa_ready.py
```

Output schema:
```json
{
  "criterion": "all_deliveries_qa_ready",
  "met": true,
  "evidence": {
    "total": 5,
    "ready": 5,
    "not_ready": []
  }
}
```

`met` is `false` if no delivery artifacts are found (tasks completed with no artifacts).

---

## scripts/check_no_open_prohibitions.py

Criterion: no `delivery.md` artifact contains a non-empty `prohibition_violations` list.

A prohibition violation is detected when the file contains the pattern:
`prohibition_violations:` followed by at least one list item (`- ` on the next non-blank line).

```bash
python3 .claude/skills/phase-dev-rules/scripts/check_no_open_prohibitions.py
```

Output schema:
```json
{
  "criterion": "no_open_prohibitions",
  "met": true,
  "evidence": {
    "total": 5,
    "clean": 5,
    "violations": []
  }
}
```
