# orch-resilience — Subsystem Specification

> Version: 0.1.0 | Status: draft | Layer: permanent
> Technical contract: `orch-resilience.contract.md`
> Fidelity: prescriptive. Current-behavior claims cite `dist/.claude/lib/orch_core.py` and `hooks/`.

## 1. Overview

| Aspect | Value |
|--------|-------|
| Objective | Keep the workflow live under failure: detect hung workers, synthesize missing terminals, schedule retries, cap and route dead work, and put critical guarantees in code, not the LLM (INV-07). |
| Core entity | Retry policy + circuit-breaker state + stale/liveness thresholds. |
| Bounded context | Stale reaping, liveness synthesis, retry eligibility/backoff/scheduling, circuit breaker, DLQ routing, stalled-orchestrator detection, crash recovery. |
| Out of scope | The state machine itself (orch-state); persistence (orch-log); dispatch (orch-dispatch). |

## 2. Actors

| Actor | Description | Permissions |
|-------|-------------|-------------|
| reaper | `stale-monitor` (Python, Step 5.0 / session end) | append `task_failed(stale_timeout)` + `task_scheduled_retry` |
| hook | `on_subagent_stop` / `on_stop` | synthesize terminal + schedule retry; session-end reap |
| orchestrator | Cycle control | trip breaker; route to DLQ; process due retries |

## 3. Use Cases

### UC-01 — Reap stale task
**Actor:** reaper
**Pre:** a task is RUNNING and silent past its stale threshold.
**Post:** `task_failed(stale_timeout, retryable=true)`; and, if eligible, an atomic `task_scheduled_retry` (UC-03).
**Main flow:** `reduce_all` → `stale_tasks(now)` → for each: append failure → `schedule_retry_if_due`.
**Alternative flows:** `Na` a task within threshold (heartbeat via F1) is not reaped.
**Related contract:** `reap_stale_tasks` / `check_stale.py`. (`orch_core.py:2625`)

### UC-02 — Synthesize terminal on worker stop
**Actor:** hook (`on_subagent_stop`)
**Pre:** a registered worker with no terminal AND silent past its liveness threshold.
**Post:** `task_failed(worker_exited_without_terminal)` + atomic retry (UC-03).
**Alternative flows:** `Pa` worker still within its window → deferred (do NOT reap a possibly-live sibling — SIEGARD BUG-1). `Pb` terminal already present → unregister only.
**Related contract:** `hooks/on_subagent_stop.py`, `worker_liveness_expired`.

### UC-03 — Schedule retry atomically (F3/F4)
**Actor:** reaper / hook
**Pre:** a `task_failed` was just appended for a currently-FAILED task.
**Post:** if `should_retry`, a `task_scheduled_retry` in the SAME Python call → task reaches SCHEDULED; else the task stays FAILED for DLQ routing.
**Main flow:** re-derive state → if `status == FAILED` and `should_retry(task, policy)` → compute backoff → append `task_scheduled_retry(next_retry_at, backoff_seconds, previous_failure_seq)`.
**Alternative flows:** `Na` task not FAILED (already advanced) → no-op. `Nb` non-retryable / structural cap → no-op (leave FAILED). Never raises.
**Related contract:** `schedule_retry_if_due`. (added F3/F4)

### UC-04 — Evaluate retry eligibility
**Actor:** system
**Post:** true/false per rules: `retryable=false` → false; structural reason (`stale_timeout`, `worker_exited_without_terminal`, `subagent_invalid_response`) with `attempts ≥ 2` → false; `attempts ≥ max_attempts` → false; else true.
**Related contract:** `should_retry` (`orch_core.py:2936`).

### UC-05 — Compute backoff
**Actor:** system
**Post:** `min(base·2^(attempts-1), cap) · U(0.8, 1.2)` seconds.
**Related contract:** `backoff_seconds` (`orch_core.py:2890`).

### UC-06 — Trip circuit breaker
**Actor:** orchestrator
**Pre:** failure rate in the window exceeds threshold.
**Post:** `circuit_breaker_tripped`; dispatch blocked until reset.
**Alternative flows:** reset via `human_response(action=reset_circuit_breaker)`. (`_handle_human_response:2034`, reset branch `:2044`)
**Related contract:** `circuit_breaker.py`, EV-22.

### UC-07 — Route to DLQ
**Actor:** orchestrator
**Pre:** a task is non-retryable or has exhausted attempts, or a dependency is in DLQ.
**Post:** `task_dlq` (terminal); phase exit is blocked until triaged.
**Related contract:** `dlq_triage.py`, EV-08.

### UC-08 — Detect stalled orchestrator
**Actor:** reaper / on_stop
**Pre:** active phase has non-terminal tasks but no `orchestrator_heartbeat` within `ORCHESTRATOR_STALE_SECONDS`.
**Post:** an actionable diagnostic (pending_task_ids, command `/u-orchestrator`). Detection only — no destructive auto-recovery.
**Related contract:** `detect_stale_orchestrator` (`orch_core.py:2438`). Threshold `ORCHESTRATOR_STALE_SECONDS = 900` (`:464`).

### UC-09 — Crash recovery
**Actor:** system (next invocation)
**Post:** a SCHEDULED task (from UC-03) is resumed by the next orchestrator cycle via due-retry dispatch; the log is intact and state re-derives.
**Related contract:** `due_retries`; FLOW-04.

## 4. Business Rules

### BR-01 — Stale threshold resolution order
`stale_threshold_seconds(task)` resolves: (1) `stale_policy.overrides_by_task_type[type]`; (2) `defaults_by_tier[tier]`; (3) `Tier.default_stale_seconds` (critical 600 / standard 300 / bulk 120). Shipped spec-* overrides: writer/back/front 1200, reviewer/validator/compliance 900. Related UC: UC-01, UC-02. (`orch_core.py:2539`)

### BR-02 — Heartbeat governs staleness (F1)
Staleness is measured as `now - last_event_at`, and `last_event_at` is advanced by `task_progress` (orch-state BR-04). A worker emitting progress within its window is never reaped. Related UC: UC-01, UC-02.

### BR-03 — Liveness-gated synthesis (enforces INV-07)
The SubagentStop hook synthesizes a terminal ONLY once the worker is silent past the SAME threshold the reaper uses (`worker_liveness_expired`); it never reaps a worker whose last event is recent. Related UC: UC-02. (`orch_core.py:2571`)

### BR-04 — Structural-reason retry cap
Structural failures (`stale_timeout`, `worker_exited_without_terminal`, `subagent_invalid_response`) are retried at most once (no retry at `attempts ≥ 2`); further occurrences go to DLQ. Related UC: UC-04. (`should_retry:2944`)

### BR-05 — Atomic retry scheduling (F3/F4, enforces INV-07)
The reaper and hook emit `task_scheduled_retry` in the same Python call as the failure when retryable; the task never stalls in FAILED because an LLM turn ended before Step 5.5. Non-retryable failures stay FAILED for DLQ. Related UC: UC-03. (`schedule_retry_if_due`)

### BR-06 — Non-retryable and cascade routing
`retryable=false`, exhausted attempts, or a dependency in DLQ route the task to DLQ (`cascade_from_dep`); DLQ is terminal and blocks phase exit. Related UC: UC-07. (`_handle_task_dlq:2013`)

### BR-07 — Detection, not destruction
`detect_stale_orchestrator` and the reaper surface actionable signals; `verify_and_recover` (destructive) stays manual. Related UC: UC-08. (`orch_core.py:2438`)

## 5. State Machine

### ST-03 — Circuit breaker

```
[ closed ] --failure rate > threshold in window--> [ tripped ] --human_response(reset)--> [ closed ]
```

| From | Event | To | Condition |
|------|-------|----|-----------|
| closed | circuit_breaker_tripped | tripped | window failure count ≥ threshold |
| tripped | human_response(reset_circuit_breaker) | closed | operator reset |

While `tripped`, dispatch is blocked (orch-control gate).

> CONF-01 (RESOLVED, v2.14.0): the persisted model above is now realized in code.
> `trip_circuit_if_due` (`orch_core.py`), called from `run_circuit_check.py` when the
> window first crosses the threshold, appends `circuit_breaker_tripped` — so
> `state.circuit_breaker` becomes non-None, the breaker stays blocked via
> `already_tripped` until a manual reset (`circuit_breaker.py --reset` →
> `human_response`, `_handle_human_response:2044`), and it no longer relaxes on
> age-out. Idempotent (`should_trip` excludes `already_tripped`).

## 6. Error Behaviors

| Situation | Result | ERR | Description |
|-----------|--------|-----|-------------|
| Stale RUNNING task | `task_failed(stale_timeout)` | ERR-11 | synthesized by reaper; retryable |
| Worker stop, no terminal, expired | `task_failed(worker_exited_without_terminal)` | ERR-10 | synthesized by hook |
| Attempts exhausted | `task_failed(max_attempts_exceeded)` → DLQ | ERR-13 | non-retryable |
| Dependency in DLQ | `task_failed(cascade_from_dep)` → DLQ | ERR-12 | cascade |
| Failure-rate breach | `circuit_breaker_tripped` | ERR — | dispatch halted |
| Critical task in DLQ | escalation `E04_critical_task_dlq` | ERR-31 | operator gate |

## 7. Cross-Domain Dependencies

| Domain | Type | Description |
|--------|------|-------------|
| orch-state | consumes | reads `status`, `attempts`, `last_event_at` (F1), `last_failure_reason` (F2) |
| orch-log | produces | appends synthesized terminals + scheduled retries |
| orch-dispatch | synchronizes | dispatches due retries; consumes DLQ routing |
| orch-control | synchronizes | breaker blocks dispatch; stalled-orchestrator diagnostic surfaced in cycle |

## 8. Out of Scope

- The reconciliation of a false-positive completion (orch-state BR-05 / F2) — resilience *causes* the synthesized failure; orch-state reconciles it.
- Distributed/process-level kill of a live worker — infeasible in the harness (no PID); mitigated by liveness-gating (BR-03) + atomic retry (BR-05).

## 9. Local Glossary

| Term | Definition |
|------|------------|
| Structural failure | A failure meaning the agent could not execute (stale/exit/invalid response); capped at 1 retry. |
| Due retry | A SCHEDULED task whose `next_retry_at` has passed. |
| Liveness window | The silence threshold before a stop synthesizes a terminal (= stale threshold). |

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Initial orch-resilience spec (UC-01..09, BR-01..07, ST-03); F1–F4 embedded | — |
