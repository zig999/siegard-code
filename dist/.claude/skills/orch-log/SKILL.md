---
name: orch-log
description: Append, read, and verify the append-only orchestration event log (.orch/log.jsonl). Provides append.py (lock + hash chain + schema validation), claim.py (atomic check-and-claim for task dispatch), read.py (filtered queries), and verify.py (hash-chain integrity). Loaded by orchestrators and workers that emit or inspect events. Not user-invocable — callers run the scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# orch-log

Event log skill: append, read, and verify the orchestration JSONL log.

## scripts/append.py

Emits an event to the append-only log with lock, hash chain, and schema validation.

### Usage

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent <agent-id> \
  --event-type <type> \
  [--task-id <id>] \
  [--attempt <n>] \
  [--data '<json-object>']
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--agent` | Yes | Agent identifier emitting the event |
| `--event-type` | Yes | Event type (see valid types below) |
| `--task-id` | No | Task ID (omit for phase/workflow events) |
| `--attempt` | No | Attempt number, default `1` |
| `--data` | No | JSON object payload, default `{}` |

### Output

On success (exit 0): JSON object of the created event written to stdout.

On error (exit 1): JSON error envelope:
```json
{"status": "error", "reason": "<code>", "detail": "<message>"}
```

Error reason codes:
- `invalid_json` — `--data` is not valid JSON or not an object
- `unknown_event_type` — `--event-type` not in the 21-type enum
- `validation_error` — payload fails schema validation
- `internal_error` — unexpected I/O or lock failure

### Example

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent orchestrator \
  --event-type task_created \
  --task-id t_001 \
  --data '{"phase":"dev","tier":"standard","type":"impl","spec":"implement X","deps":[]}'
```

## scripts/claim.py

Atomically claims a task for dispatch: re-derives the task's status from the log INSIDE the append lock and appends `task_claimed` only when the task is still `ready`. Closes the double-dispatch race — two concurrent orchestrator instances racing on the same batch serialize on the lock; the loser receives `claimed: false` instead of writing a duplicate claim.

Orchestrators MUST use this script (not `append.py`) to emit `task_claimed`.

### Usage

```bash
python3 .claude/skills/orch-log/scripts/claim.py \
  --agent <agent-id> \
  --task-id <id> \
  [--attempt <n>] \
  --data '{"phase":"<phase>","worker_type":"<type>","worker_id":"<id>"}'
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--agent` | Yes | Orchestrator identifier emitting the claim |
| `--task-id` | Yes | Task ID to claim |
| `--attempt` | No | Attempt number, default `1` |
| `--data` | Yes (fields) | JSON object; `phase`, `worker_type`, `worker_id` are required by schema |

### Output

Exit 0 (both are expected outcomes — check the `claimed` field):
```json
{"claimed": true,  "event": {...}}
{"claimed": false, "reason": "not_ready:running"}
```

`claimed: false` means the task is no longer eligible (another instance claimed it, or it left `ready`). The caller MUST drop the task from its dispatch batch and NOT spawn a worker. Reason codes: `task_not_found`, `not_ready:<status>`.

Exit 1: `{"status": "error", "reason": "invalid_json" | "validation_error" | "state_underivable" | "internal_error", "detail": "..."}`.

## scripts/read.py

Reads events from the log with optional filters. Each matching event is printed as one JSON line to stdout.

### Usage

```bash
python3 .claude/skills/orch-log/scripts/read.py \
  [--from-seq N] \
  [--tail N] \
  [--task-id <id>] \
  [--event-type <type>] \
  [--phase <phase>]
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `--from-seq N` | Return events with seq >= N (default: 0 = all) |
| `--tail N` | Return only the last N events (applied after other filters) |
| `--task-id` | Filter by task ID |
| `--event-type` | Filter by event type |
| `--phase` | Filter by data.phase field |

Multiple filters are applied as AND. Output: one JSON object per line (empty output = no matches). Exit 0 on success, 1 on corrupted log.

### Examples

```bash
# All events
python3 .claude/skills/orch-log/scripts/read.py

# Last 20 events
python3 .claude/skills/orch-log/scripts/read.py --tail 20

# All task_created events in phase dev
python3 .claude/skills/orch-log/scripts/read.py --event-type task_created --phase dev
```

## scripts/verify.py

Verifies hash-chain integrity of the log. Output is a single JSON object.

### Usage

```bash
python3 .claude/skills/orch-log/scripts/verify.py [--mode strict|audit]
```

### Modes

| Mode | Behavior | Exit code |
|------|----------|-----------|
| `strict` (default) | Stops at first error | 0 ok, 1 error |
| `audit` | Collects all errors, never modifies log | Always 0 |

### Output schema

```json
{
  "ok": true,
  "message": "...",
  "mode": "strict",
  "events_verified": 42,
  "first_error_seq": null,
  "error_details": []
}
```

Use `audit` for investigation; use `strict` at orchestrator startup (architecture rule R1).

## Valid event types

Task lifecycle (8):
```
task_created   task_claimed       task_progress         task_completed
task_failed    task_scheduled_retry  task_retried       task_dlq
```

Phase lifecycle (7):
```
phase_declared         phase_entered              phase_exit_criterion_met
phase_exit_approved    phase_transitioned         phase_paused
phase_resumed
```

Management and operations (6):
```
circuit_breaker_tripped   escalation   human_response
snapshot                  log_recovered   preflight_failed
```
