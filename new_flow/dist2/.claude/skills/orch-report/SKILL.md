# orch-report

Worker reporting skill: emit task progress and completion events to the orchestration log.

## allowed-tools

```
Bash(python3 *)
```

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
  --kind progress --task-id t_001 --data '{"message":"running tests"}'

# Report success
ORCH_WORKER_ID=worker-42 python3 .claude/skills/orch-report/scripts/emit.py \
  --kind completed --task-id t_001 \
  --data '{"phase":"dev","artifacts":["src/foo.py"],"summary":"implemented foo"}'

# Report failure
ORCH_WORKER_ID=worker-42 python3 .claude/skills/orch-report/scripts/emit.py \
  --kind failed --task-id t_001 \
  --data '{"phase":"dev","reason":"spec_unclear","retryable":true}'
```
