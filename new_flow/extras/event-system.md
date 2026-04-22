# Event System

## 1. Log Format

**File**: `.orch/log.jsonl` — one JSON object per line, append-only, never edited.

### Write protocol

Every append:
1. Acquires exclusive POSIX `flock` on `.orch/log.jsonl.lock`
2. Reads last line to compute next `seq` and `prev_hash`
3. Writes complete JSON line (atomically; < PIPE_BUF)
4. Calls `fsync()` before releasing lock
5. Releases lock

### Hash chain integrity

Each event's `hash` field = SHA-256 of its own canonical JSON (keys sorted, no whitespace, `hash` field excluded). The next event's `prev_hash` references it:

```
GENESIS ← event[0].hash ← event[1].prev_hash
         event[1].hash  ← event[2].prev_hash
         ...
```

Verification:
```bash
python3 .claude/skills/orch-log/scripts/verify.py --mode strict
# {"ok": true, "events_verified": 342, ...}
```

### Large payloads (blob externalization)

Payloads > 3500 bytes are externalized to avoid exceeding PIPE_BUF:

**In log** (reference):
```json
{
  "data": {
    "_blob_ref": "blobs/evt_XYZ.json",
    "_size": 15000,
    "_blob_hash": "sha256:abc123..."
  }
}
```

**On disk** (`.orch/blobs/evt_XYZ.json`): original payload. Verified via `_blob_hash` on load.

---

## 2. Base Event Envelope

All 21 event types share this schema:

```json
{
  "seq":        42,
  "event_id":   "evt_01HK7XZY8K9ABCDE01234",
  "ts":         "2026-04-20T10:00:42.123Z",
  "agent":      "orchestrator | worker-<id> | hook-on_subagent_stop | operator | system",
  "event_type": "<one of 21 types>",
  "task_id":    "t_0042 | null",
  "attempt":    1,
  "data":       {},
  "prev_hash":  "GENESIS | <hex64>",
  "hash":       "<hex64>"
}
```

| Field | Type | Notes |
|-------|------|-------|
| `seq` | int | Monotonic global counter; starts at 1 |
| `event_id` | string | `evt_` prefix + 26-char base32; globally unique |
| `ts` | string | ISO 8601 UTC, millisecond precision |
| `agent` | string | Identity of the emitter |
| `event_type` | string | One of the 21 types below |
| `task_id` | string\|null | null for global events (phase, circuit breaker, etc.) |
| `attempt` | int | Minimum 1; incremented on retry |
| `data` | object | Type-specific payload (see §4) |
| `prev_hash` | string | `"GENESIS"` for seq=1; SHA-256 hex of previous event |
| `hash` | string | SHA-256 hex of this event's canonical JSON (excluding hash field) |

---

## 3. Event Type Index

### Task lifecycle (8 types)

| Type | Emitter | Description |
|------|---------|------------|
| `task_created` | orchestrator | New task declared |
| `task_claimed` | orchestrator | Task assigned to a worker |
| `task_progress` | worker | Heartbeat / milestone update |
| `task_completed` | worker | Worker succeeded; lists artifacts |
| `task_failed` | worker \| hook | Worker failed; includes `retryable` |
| `task_scheduled_retry` | orchestrator | Backoff scheduled; `next_retry_at` set |
| `task_retried` | orchestrator | Backoff expired; task re-queued (attempt+1) |
| `task_dlq` | orchestrator | Task permanently failed; DLQ entry written |

### Phase lifecycle (7 types)

| Type | Emitter | Description |
|------|---------|------------|
| `phase_declared` | orchestrator | All phases of the workflow declared |
| `phase_entered` | meta-orchestrator | Phase becomes active |
| `phase_exit_criterion_met` | phase orchestrator | One exit criterion satisfied |
| `phase_exit_approved` | phase orchestrator | All exit criteria met; ready to transition |
| `phase_transitioned` | phase orchestrator | Prior phase completed; next phase announced |
| `phase_paused` | orchestrator | Phase paused (e.g., circuit breaker, escalation) |
| `phase_resumed` | orchestrator | Phase resumed after pause |

### Management / operational (6 types)

| Type | Emitter | Description |
|------|---------|------------|
| `circuit_breaker_tripped` | orchestrator | Failure threshold exceeded |
| `escalation` | orchestrator \| phase orch | Human intervention required |
| `human_response` | operator | Operator resolves escalation |
| `snapshot` | hook \| orchestrator | State checkpoint written |
| `log_recovered` | `verify_and_recover` | Log truncated and corruption archived |
| `preflight_failed` | `preflight.py` | Pre-run environment check failed |

---

## 4. Payload Schemas by Type

### `task_created`

```json
{
  "phase":    "sdd | dev | review | test",
  "tier":     "critical | standard | bulk",
  "type":     "spec-writer | impl | qa | planning | ...",
  "spec":     "Single-sentence or multiline task specification",
  "deps":     ["t_0001", "t_0002"],
  "priority": 50,
  "evidence": [12, 13, 15]
}
```

`evidence`: seqs of events that justify creating this task. Required.

### `task_claimed`

```json
{
  "worker_id": "worker-sdd-42",
  "evidence":  [18]
}
```

### `task_progress`

```json
{
  "message": "Running unit tests — 8/12 passing"
}
```

### `task_completed`

```json
{
  "phase":     "dev",
  "artifacts": ["src/auth/jwt.py", "tests/test_jwt.py"],
  "summary":   "Implemented JWT signing with RS256; 12 tests passing",
  "metrics": {
    "duration_seconds": 45.3,
    "tokens_in":        12000,
    "tokens_out":       8000
  }
}
```

`artifacts`: file paths only. Never inline content.

### `task_failed`

```json
{
  "phase":          "dev",
  "reason":         "spec_unclear: dependency X not specified",
  "retryable":      true,
  "synthesized_by": "hook_on_subagent_stop"
}
```

`retryable=true`: transient error (timeout, rate limit, tool failure).
`retryable=false`: permanent error (invalid spec, permission denied, missing input).
`synthesized_by`: present only when hook synthesized the event (worker stopped silently).

### `task_scheduled_retry`

```json
{
  "next_retry_at":        "2026-04-20T10:05:42.000Z",
  "backoff_seconds":      45.2,
  "reason":               "worker_transient_error",
  "previous_failure_seq": 38
}
```

### `task_retried`

```json
{
  "previous_attempt": 1,
  "evidence":         [38, 40]
}
```

### `task_dlq`

```json
{
  "phase":          "dev",
  "reason":         "max_attempts_exceeded | non_retryable | dependency_dlq",
  "attempt_count":  3,
  "last_error":     "spec_unclear: dependency X not specified"
}
```

### `phase_declared`

```json
{
  "workflow_id": "wf_2026_04_20_001",
  "phases": [
    { "name": "sdd",    "order": 1, "required": true },
    { "name": "dev",    "order": 2, "required": true },
    { "name": "review", "order": 3, "required": true },
    { "name": "test",   "order": 4, "required": false }
  ]
}
```

### `phase_entered`

```json
{
  "phase":   "dev",
  "from":    "sdd",
  "evidence": [89]
}
```

### `phase_exit_criterion_met`

```json
{
  "phase":     "dev",
  "criterion": "all_deliveries_qa_ready",
  "evidence":  [101, 102, 103]
}
```

### `phase_exit_approved`

```json
{
  "phase":    "dev",
  "criteria": ["all_impl_tasks_terminal", "all_deliveries_qa_ready", "no_open_prohibitions"],
  "evidence": [104, 106, 108]
}
```

### `phase_transitioned`

```json
{
  "from":     "dev",
  "to":       "review",
  "evidence": [109]
}
```

### `phase_paused`

```json
{
  "phase":  "dev",
  "reason": "circuit_breaker_tripped",
  "evidence": [55]
}
```

### `phase_resumed`

```json
{
  "phase":    "dev",
  "evidence": [61]
}
```

### `circuit_breaker_tripped`

```json
{
  "failures_in_window": 52,
  "window_minutes":     10,
  "threshold":          50,
  "evidence":           [50, 51, 52, 53, 54]
}
```

### `escalation`

```json
{
  "code":     "E03_max_rejections_exceeded",
  "phase":    "sdd",
  "task_id":  "t_0005",
  "question": "Spec writer has been rejected 3 times. Abort or reassign?",
  "options":  ["abort", "reassign", "override"],
  "evidence": [33, 34, 35]
}
```

Escalation codes: E01 (stale task), E02 (circuit breaker), E03 (max rejections), E04 (missing spec), E05 (dependency DLQ), E06 (worker refused), E07 (log corruption), E08 (preflight failed), E09 (hash chain broken), E10 (invalid handoff), E11 (quota exceeded), E12 (human gate required), E99 (custom confirmation).

### `human_response`

```json
{
  "escalation_seq": 60,
  "action":         "confirm_proceed | abort | return_to_dev | reassign",
  "operator":       "alice@example.com",
  "notes":          "Accepting spec as-is; downstream tests will catch issues"
}
```

### `snapshot`

```json
{
  "snapshot_path": ".orch/state/snapshot-00000342.json",
  "seq_covered":   342,
  "task_count":    12,
  "phase":         "dev"
}
```

### `log_recovered`

```json
{
  "seq_truncated_from":    150,
  "seq_truncated_to":      149,
  "events_removed":        12,
  "operator":              "alice@example.com",
  "corrupt_file_path":     ".orch/log.jsonl.corrupt.2026-04-20T10-30-45-123",
  "hash_before_truncation": "abc123..."
}
```

### `preflight_failed`

```json
{
  "checks_failed": [
    {
      "check":  "python_version",
      "reason": "Python 3.8 found; 3.10+ required",
      "detail": {}
    }
  ]
}
```
