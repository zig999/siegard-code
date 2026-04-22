# Reliability

## 1. Retry Policy

### Exponential backoff with jitter

```
delay = min(base_delay_s × 2^(attempt-1), cap_s)
backoff = delay × uniform(0.8, 1.2)
```

Deterministic calculation first, jitter applied after. This preserves reproducibility for the core delay while preventing thundering herd.

### Per-tier defaults

| Tier | max_attempts | base_delay_s | cap_s |
|------|-------------|-------------|-------|
| `critical` | 5 | 15 | 600 |
| `standard` | 3 | 30 | 600 |
| `bulk` | 1 | 0 | 0 |

Override per task_type in `.orch/config.json`:
```json
{
  "retry": {
    "tiers": {
      "critical": { "max_attempts": 7, "base_delay_s": 10, "cap_s": 300 }
    },
    "task_types": {
      "e2e-test": { "max_attempts": 5 }
    }
  }
}
```

### Retry decision flow

```
task_failed received
    │
    ├─ retryable=false ──────────────────────► task_dlq(non_retryable)
    │
    └─ retryable=true
           │
           ├─ attempts >= max_attempts ───────► task_dlq(max_attempts_exceeded)
           │
           └─ attempts < max_attempts
                  │
                  ▼
             emit task_scheduled_retry
             (next_retry_at = now + backoff)
             task.status = scheduled
                  │
             next orchestrator cycle:
             tasks_ready_for_retry() → emit task_retried(attempt+1)
             task.status = pending/ready
```

---

## 2. Circuit Breaker

### Purpose

Detects failure storms — rapid succession of task failures indicating a systemic problem (broken environment, bad deployment, quota exhaustion). Prevents spawning more workers when all are failing.

### Configuration (defaults)

| Parameter | Default | Description |
|-----------|---------|------------|
| `failure_threshold` | 50 | Failures in window before tripping |
| `window_minutes` | 10 | Rolling window size |

Override in `.orch/config.json`:
```json
{
  "circuit_breaker": {
    "failure_threshold": 20,
    "window_minutes":    5
  }
}
```

### Behavior when tripped

1. No new worker spawns
2. Already-running workers complete normally (not cancelled)
3. Scheduled retry tasks remain frozen
4. Phase orchestrator pauses; escalates E02 to meta-orchestrator
5. Orchestrator returns `{run_status: "escalated"}` to user

### Reset (manual only)

```bash
python3 .claude/scripts/circuit_breaker.py status
# {"status": "tripped", "failures_in_window": 52, ...}

python3 .claude/scripts/circuit_breaker.py --reset --confirm
# Emits circuit_breaker_reset event; spawning resumes next cycle
```

---

## 3. Stale Task Detection

A running task is stale when `now - last_event_at > tier.stale_seconds`.

| Tier | stale_seconds |
|------|--------------|
| `critical` | 300 (5 min) |
| `standard` | 600 (10 min) |
| `bulk` | 1800 (30 min) |

When stale detected:
1. Orchestrator emits `task_failed(retryable=true, reason="stale_no_heartbeat")`
2. Retry logic applies normally

Workers should emit `task_progress` regularly on long-running tasks to reset the stale timer.

---

## 4. Dead Letter Queue (DLQ)

### What lands in DLQ

- `retryable=false` failures
- Tasks that exceeded `max_attempts`
- Tasks whose dependencies are in DLQ (`dependency_dlq` cascade)

### DLQ entry

File: `.orch/dlq/<task_id>.json`
```json
{
  "task_id":      "dev_tc_007",
  "reason":       "max_attempts_exceeded",
  "attempt_count": 3,
  "last_error":   "spec_unclear: RS256 key path not specified",
  "dlq_seq":      88
}
```

### DLQ triage

```bash
python3 .claude/scripts/dlq_triage.py
```

Output: tasks categorized into buckets:

| Bucket | Meaning |
|--------|---------|
| `input_issue` | Task spec was invalid or ambiguous |
| `worker_issue` | Worker crashed (non-recoverable) |
| `permission_issue` | Access denied |
| `code_issue` | Implementation bug |
| `quota_issue` | Rate limit, budget, timeout |
| `transient_issue` | Network blip not retried |
| `unknown` | Uncategorized |

**Operator actions per DLQ task**:
- Fix spec + retry: resolve root cause, emit `task_retried` manually
- Cancel dependents: emit `task_dlq(dependency_dlq)` for blocked tasks
- Ignore: note in `human_response` event; proceed without the task

### DLQ cascade

When task T enters DLQ, all tasks that depend on T (directly or transitively) are automatically sent to DLQ with `reason="dependency_dlq"`. Orchestrator detects this via `get_orphaned_dep_ids()` at start of each cycle.

---

## 5. Crash Recovery

### Hook: `on_subagent_stop`

When a worker sub-agent stops (normally or abnormally) without emitting a terminal event, `on_subagent_stop.py` synthesizes one:

```json
{
  "event_type": "task_failed",
  "data": {
    "reason":         "worker_stopped_without_terminal_event",
    "retryable":      true,
    "synthesized_by": "hook_on_subagent_stop"
  }
}
```

This ensures the orchestrator never gets stuck waiting for a silent worker.

### Log integrity check

Every orchestrator cycle begins with:
```bash
python3 .claude/skills/orch-log/scripts/verify.py --mode strict
# {"ok": true, "events_verified": 342, ...}
```

If integrity fails: escalates E09. No task dispatch until log is clean.

### Tolerated truncation

`read_events()` silently ignores a truncated last line (e.g., crash mid-write). Orchestrator continues from last complete event — no manual intervention needed.

### Manual recovery (for mid-log corruption)

```bash
# 1. Investigate
python3 .claude/skills/orch-log/scripts/verify.py --mode audit
# {"ok": false, "first_error_seq": 150, "error_details": [...]}

# 2. Decide truncation point from output

# 3. Execute recovery — requires --confirm (never automatic)
python3 .claude/skills/orch-log/scripts/verify.py \
  --recover \
  --confirm \
  --from-seq 150 \
  --operator "alice@example.com"
# {"ok": true, "recovered": true, "seq": 351, "events_removed": 12, ...}
```

**What happens**:
- `log.jsonl` truncated at seq 149 (last valid event)
- Events 150+ archived to `log.jsonl.corrupt.<timestamp>`
- `log_recovered` event appended (auditable — includes operator, seqs, hash before/after)
- Next orchestrator cycle runs `verify_chain(strict)` → passes

Recovery is **always manual** — no automatic truncation. The `--confirm` flag is a deliberate safety gate.

---

## 6. Preflight Checks

Run before first orchestrator invocation:

```bash
python3 .claude/scripts/preflight.py
# {"status": "ok", "checks_passed": 12, "checks_failed": 0, ...}
```

Quick mode (skips remote checks):
```bash
python3 .claude/scripts/preflight.py --quick
```

Checks performed:

| Check | Failure action |
|-------|---------------|
| Python 3.10+ | Hard fail |
| `ORCH_PROJECT_DIR` set | Hard fail |
| `.orch/` directory writable | Hard fail |
| `orch_core.py` importable | Hard fail |
| `claude` CLI available | Soft warn |
| Agent tool spawnable | Soft warn |
| Env var propagation | Soft warn |
| Lock acquisition | Hard fail |
| Log integrity (if exists) | Hard fail |

Soft warns allow orchestrator to proceed; hard fails block it.
