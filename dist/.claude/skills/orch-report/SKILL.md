---
name: orch-report
description: Worker reporting skill — emit task_progress, task_completed, and task_failed events to the orchestration log via emit.py. Event types are restricted by a hard in-code guard-rail; worker identity comes from ORCH_WORKER_ID and cannot be overridden by the caller. Loaded by every worker as its only write path to the log. Not user-invocable.
user-invocable: false
allowed-tools: Bash(python3 *)
---

# orch-report

Worker reporting skill: emit task progress and completion events to the orchestration log.

## Security boundary

`emit.py` enforces a hard guard-rail: **only `task_progress`, `task_completed`, and `task_failed` are accepted**. Any other event type is rejected unconditionally. This constraint is enforced in code, independent of the calling prompt.

Worker identity is read from the `ORCH_WORKER_ID` environment variable. The caller cannot override it.

## scripts/emit.py

### Usage

```bash
ORCH_WORKER_ID=<worker-id> python3 .claude/skills/orch-report/scripts/emit.py \
  --kind progress|completed|failed \
  --task-id <id> \
  [--attempt <n>] \
  [--data '<json-object>']
```

### Environment variables (set by orchestrator in spawn prompt)

| Variable | Required | Description |
|----------|----------|-------------|
| `ORCH_WORKER_ID` | Yes | Worker identity — used as `agent` field in every emitted event |
| `ORCH_TASK_ID` | Yes | Task assigned to this worker invocation |
| `ORCH_ATTEMPT` | Yes | Current attempt number (1-based) |
| `ORCH_PROJECT_DIR` | Yes | Absolute path to project root — used to resolve artifact paths |
| `SPECS_DIR` | Phase-specific | Relative path to specs directory (set by sdd/dev/review orchestrators) |

Workers **must** export all five variables as shell env vars before calling `emit.py`.

### Why `phase` is required in every event

All three event types (`task_progress`, `task_completed`, `task_failed`) require `phase` in their `data` payload. This is intentional, not redundant:

- The `on_subagent_stop` hook synthesizes `task_failed` when a worker stops silently. It needs `phase` to build a valid payload without replaying the log (which may be unavailable or slow).
- `task_claimed` also carries `phase` for the same reason — the registry entry written by `register_worker()` stores it for hook recovery.

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `ORCH_WORKER_ID` | Yes (env) | Worker identifier — set by orchestrator before spawning |
| `--kind` | Yes | `progress`, `completed`, or `failed` |
| `--task-id` | Yes | Task being reported on |
| `--attempt` | No | Attempt number, default `1` |
| `--data` | No | JSON object payload, default `{}` |

### Kind → event_type mapping

| Kind | Event type emitted |
|------|--------------------|
| `progress` | `task_progress` |
| `completed` | `task_completed` |
| `failed` | `task_failed` |

### `--data` schema by kind

**`progress`** — intermediate status update:
```json
{
  "phase": "<phase name — required>",
  "note":  "<human-readable status string>"
}
```

**`completed`** — terminal success:
```json
{
  "phase":     "<phase name — required>",
  "artifacts": ["<relative path to output file — required, may be empty list>"],
  "summary":   "<one-line outcome — optional>"
}
```
`artifacts` paths are relative to `ORCH_PROJECT_DIR` — **absolute paths and `..` traversals are rejected by `emit.py`**. Exit criteria scripts read these paths to evaluate phase completion. Use the conventions below:
- Dev workers: `<session_dir>/delivery/<task_id>-delivery.md`
- QA workers: `<specs_dir>/qa/<task_id>-qa.md`
- Planning workers: `<session_dir>/backlog/backlog.json`

**`failed`** — terminal failure:
```json
{
  "phase":     "<phase name — required>",
  "reason":    "<error code or short description — required>",
  "retryable": true,
  "error":     "<optional detailed error message>"
}
```
Set `retryable: false` only for permanent failures (spec ambiguity, missing input, permission). Leave `true` for transient errors (tool failure, timeout, context overflow). The `error` field is optional but recommended — the reducer stores it in `task.last_error` for diagnostics and DLQ triage.

### Output

On success (exit 0): JSON object of the created event.

On error (exit 1): JSON error envelope:
```json
{"status": "error", "reason": "<code>", "detail": "<message>"}
```

Error reason codes:
- `missing_env` — `ORCH_WORKER_ID` not set
- `invalid_json` — `--data` is not valid JSON or not an object
- `validation_error` — payload fails schema validation
- `internal_error` — unexpected I/O or lock failure

### Examples

```bash
# Report progress
ORCH_WORKER_ID=worker-42 python3 .claude/skills/orch-report/scripts/emit.py \
  --kind progress --task-id t_001 --data '{"phase":"dev","note":"running tests"}'

# Report success
ORCH_WORKER_ID=worker-42 python3 .claude/skills/orch-report/scripts/emit.py \
  --kind completed --task-id t_001 \
  --data '{"phase":"dev","artifacts":["src/foo.py"],"summary":"implemented foo"}'

# Report failure
ORCH_WORKER_ID=worker-42 python3 .claude/skills/orch-report/scripts/emit.py \
  --kind failed --task-id t_001 \
  --data '{"phase":"dev","reason":"spec_unclear","retryable":true}'
```
