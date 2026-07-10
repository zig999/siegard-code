# orch-resilience — Technical Contract

> Stack: Python 3.10+ stdlib + Claude Code hooks | Version: 0.1.0 | Status: draft | Layer: permanent
> Business spec: `orch-resilience.spec.md`

## 1. Stack and Patterns

| Aspect | Value | Note |
|--------|-------|------|
| Reaper | Python `reap_stale_tasks` | Step 5.0 (`check_stale.py`) + session end (`on_stop.py`) |
| Liveness | `worker_liveness_expired` | same threshold as reaper |
| Retry | `should_retry` + `backoff_seconds` + `schedule_retry_if_due` | atomic scheduling (F3/F4) |
| Breaker | `circuit_breaker.py` + `state.circuit_breaker` | reset via `human_response` |

## 2. Data Model

### RetryPolicy (`orch_core.py:2856`; `for_tier:2863`)

`{ max_attempts, base_delay_s, cap_s }`; tier defaults `critical{5,15,600} / standard{3,30,600} / bulk{1,0,0}`; `for_task` applies `overrides_by_task_type` over the tier base.

### task_scheduled_retry data

`{ phase, next_retry_at(ISO), backoff_seconds(number), previous_failure_seq(int) }`.

### Config (`.orch/config.json`)

```json
"stale_policy": {
  "defaults_by_tier": {"critical":600,"standard":300,"bulk":120},
  "overrides_by_task_type": {"spec-writer":1200,"spec-back":1200,"spec-front":1200,
    "spec-reviewer":900,"spec-validator":900,"spec-compliance":900,"spec-triage":600,
    "impl":1200,"planning":900,"qa":900,"test-run":1800,
    "security-review":900,"architecture-review":900}
}
```

## 3. CLI Contracts

| Script | Args | stdout |
|--------|------|--------|
| `check_stale.py` | `[--now <ISO>]` | `{"stale_count":N,"failed":[...],"stale_orchestrator":<dict\|null>}` exit 0 |
| `circuit_breaker.py` | `--reset --confirm --operator <id> \| --status` | manual reset/status tool; emits `human_response(reset_circuit_breaker)`; does NOT window-check or append `circuit_breaker_tripped` (see CONF-01) |
| `run_circuit_check.py` (orch-infra) | — | window evaluation via `evaluate_circuit_state` (`orch_core.py:3133`); on `should_trip` it appends `circuit_breaker_tripped` (`trip_circuit_if_due`, v2.14.0/CONF-01) then returns `status:blocked` |
| `dlq_triage.py` | — | DLQ classification (`transient_issue` / …) for operator |

### Hook contracts

| Hook | Trigger | Behavior |
|------|---------|----------|
| `on_subagent_stop.py` | any subagent stop | for each expired registered worker with no terminal: synthesize `task_failed` + `schedule_retry_if_due`; else defer/unregister |
| `on_stop.py` | session end | reap stale + write diagnostics; never blocks shutdown (`except: pass`) |

## 4. Library Contract (`orch_core`)

| Function | Signature | Pre / Post | Raises |
|----------|-----------|-----------|--------|
| `reap_stale_tasks` | `(now=None) -> list[str]` | fails stale RUNNING tasks + schedules retries | never (reaper swallows) |
| `schedule_retry_if_due` | `(task_id, previous_failure_seq, now=None, config=None) -> str\|None` | atomic retry when FAILED+eligible | never |
| `should_retry` | `(task, policy) -> bool` | retry eligibility | — |
| `backoff_seconds` | `(attempts, base_delay_s=30.0, cap_s=600.0, jitter_range=(0.8,1.2)) -> float` | exp backoff + jitter | — |
| `stale_threshold_seconds` | `(task, config=None) -> int` | override→tier→enum | — |
| `worker_liveness_expired` | `(task, now, config=None) -> bool` | silent past threshold | — |
| `stale_tasks` | `(state, now, config=None) -> list[TaskState]` | RUNNING + past threshold | — |
| `detect_stale_orchestrator` | `(state, events, now, threshold=900) -> dict\|null` | actionable diagnostic | — |

## 5. Constants

| Constant | Value | Role |
|----------|-------|------|
| `ORCHESTRATOR_STALE_SECONDS` | 900 | stalled-orchestrator window |
| Tier stale defaults | 600 / 300 / 120 | critical / standard / bulk |

## 6. Out of Scope

- F2 reconciliation of the false-positive completion (orch-state contract).
- Log append internals (orch-log contract).

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | RetryPolicy, stale/retry CLI + library, hook contracts, F3/F4 | — |
