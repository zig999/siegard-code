---
name: phase-_example
description: Scaffold template for phase-{name}-rules skills. Copy the directory to phase-{name}-rules, replace {name} placeholders, implement the exit-criteria checkers and select_worker.py routing, and declare exit-criteria.json. Reference template only — never dispatched at runtime. Not user-invocable.
user-invocable: false
allowed-tools: Bash(python3 *), Read, Glob, Grep
---

# phase-{name}-rules

Phase rules skill for `{name}` phase. Provides exit criteria checkers, worker routing table,
and phase-specific constraints consumed by the orchestrator.

## Contract

### Input (from orchestrator)

The orchestrator calls this skill's scripts directly. No inter-skill communication envelope needed.

### Output

Every script in `scripts/` returns a JSON object to stdout and exits 0 on success or 1 on error.

---

## Phase identity

| Field | Value |
|-------|-------|
| `phase_name` | `{name}` |
| `order` | `{N}` |
| `required` | `true` |
| `worker_default` | `{worker-agent-name}` |

---

## Worker routing table

Maps `task.type` to worker sub-agent. Consumed by the orchestrator dispatcher (Step 5).

| task.type | worker subagent_type |
|-----------|----------------------|
| `{type_a}` | `{worker-a}` |
| `{type_b}` | `{worker-b}` |
| `*` (default) | `{worker-default}` |

---

## scripts/select_worker.py

Returns the worker sub-agent name for a given task type.

### Usage

```bash
python3 .claude/skills/phase-{name}-rules/scripts/select_worker.py \
  --task-type <type>
```

### Output

On success (exit 0):
```json
{"worker": "<subagent-name>", "task_type": "<type>", "phase": "{name}"}
```

On error (exit 1):
```json
{"status": "error", "reason": "unknown_task_type", "detail": "<message>"}
```

---

## scripts/check_{criterion_name}.py

Evaluates one exit criterion. Replace `{criterion_name}` with the actual criterion identifier
(e.g. `all_impl_tasks_terminal`, `all_specs_approved`, `no_open_critical_findings`).

One script per criterion. Each script is independent and has no side effects.

### Usage

```bash
python3 .claude/skills/phase-{name}-rules/scripts/check_{criterion_name}.py
```

### Output schema

```json
{
  "criterion": "{criterion_name}",
  "met": true,
  "evidence": {
    "total": 0,
    "passing": 0,
    "failing": []
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `criterion` | string | Criterion identifier (matches key in exit-criteria.json) |
| `met` | bool | `true` if criterion is satisfied |
| `evidence` | object | Supporting data — structure varies by criterion |

On error (exit 1):
```json
{"status": "error", "reason": "<code>", "detail": "<message>"}
```

Error reason codes:
- `log_missing` — `.orch/log.jsonl` not found
- `internal_error` — unexpected runtime error

---

## exit-criteria.json

Declares all exit criteria for this phase. The orchestrator evaluates each criterion by calling
the corresponding `check_{criterion_id}.py` script.

See `exit-criteria.json` in this directory.

---

## references/

Phase-specific reference documents. Optional — add files here when the phase has domain-specific
rules, templates, or vocabulary that workers need to consume.

| File | Purpose |
|------|---------|
| _(empty in this template)_ | _(add as needed)_ |
