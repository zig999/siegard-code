# orch-state — Subsystem Specification

> Version: 0.1.0 | Status: draft | Layer: permanent
> Technical contract: `orch-state.contract.md`
> Fidelity: prescriptive. Current-behavior claims cite `dist/.claude/lib/orch_core.py`.

## 1. Overview

| Aspect | Value |
|--------|-------|
| Objective | Derive all engine state by replaying the log (INV-01); own the task state machine and idempotency/ordering guarantees. |
| Core entity | `OrchState` — the reduced view (tasks, phases, escalation, circuit_breaker, anomalies, last_seq). |
| Bounded context | Reduction (strict/tolerant/per-workflow), the task state machine, the snapshot cache. |
| Out of scope | Persistence (orch-log); deciding what to append (orch-dispatch/control); phase-gate policy (orch-phases). |

## 2. Actors

| Actor | Description | Permissions |
|-------|-------------|-------------|
| orchestrator | Derives state each cycle | run strict `reduce_all`, `current_phase`, `detect_mode` |
| monitor / diagnostics | Read-only tooling | run tolerant `reduce_all_tolerant` |
| system (reducer) | Internal | apply events, write/validate snapshot |

## 3. Use Cases

### UC-01 — Reduce (strict)
**Actor:** orchestrator
**Pre:** log readable; hash chain intact.
**Post:** an `OrchState` reflecting every event; the engine's authoritative derivation.
**Main flow:** load snapshot if valid → replay the tail (else full replay) → return state.
**Alternative flows:** `Na` illegal transition → IllegalTransition (ERR-04), reduction aborts (a bad log is rejected by design). `Nb` broken chain → CorruptedLogError (ERR-03).
**Related contract:** `reduce_all` / CLI `reduce.py`. (`orch_core.py:2249`)

### UC-02 — Reduce (tolerant, diagnostic)
**Actor:** monitor / classify_run_status
**Pre:** log readable.
**Post:** `(state, violations)` — partial state plus every illegal transition, each recorded and skipped.
**Main flow:** replay; on IllegalTransition, append a `Violation` and skip that event; continue.
**Alternative flows:** `Na` broken chain → CorruptedLogError still propagates (trust is gone).
**Constraint:** DIAGNOSTIC only — the engine MUST use UC-01. (`orch_core.py:2312`)

### UC-03 — Reduce a single workflow
**Actor:** orchestrator / tooling
**Pre:** `workflow_id` given.
**Post:** state derived from only that workflow's events (isolation: a corrupt sibling cannot block it).
**Related contract:** `reduce_workflow` / `reduce.py --workflow`. (`orch_core.py:2354`)

### UC-04 — Derive current phase
**Actor:** orchestrator
**Post:** the active phase name derived from the log (INV-12), or null.
**Related contract:** `current_phase.py` (default or `--from-stdin`).

### UC-05 — Detect run mode
**Actor:** orchestrator
**Post:** the operation mode (e.g. standard vs improve) derived from the log.
**Related contract:** `detect_mode.py`.

### UC-06 — Write / validate snapshot cache
**Actor:** system (reducer)
**Post:** a snapshot at a seq boundary enabling O(tail) reduction; validated by seq+hash before reuse, else full replay.
**Main flow:** on replay reaching `SNAPSHOT_EVERY_N_EVENTS`, persist `{state, boundary_offset, boundary_hash}`; on load, re-read boundary event and compare seq+hash; mismatch → discard, full replay.
**Related contract:** `_load_reduce_snapshot:2191` / `_write_reduce_snapshot:2226`; `ORCH_SNAPSHOT=0` disables.

## 4. Business Rules

### BR-01 — Deterministic replay (enforces INV-01, INV-05)
State is a pure function of the ordered event stream; the same log yields the same `OrchState`. Strict and snapshot paths produce identical state. Related UC: UC-01. (`orch_core.py:2249`)

### BR-02 — Idempotency no-op (enforces INV-04)
A duplicate event keyed `(task_id, attempt, event_type)` is an audited no-op, never a fatal replay error: an already-terminal task ignores a repeat terminal; a duplicate claim by the same worker is recorded in `anomalies` and skipped. Related UC: UC-01. (`_handle_task_completed` terminal no-op `:1884`, `_handle_task_claimed` anomaly `:1828-1835`)

### BR-03 — Superseded-attempt straggler no-op
A `task_completed`/`task_failed` whose `event.attempt < task.attempts` is residue from a retried attempt → no-op, not fatal. Related UC: UC-01. (`_handle_task_completed:1891`, `_handle_task_failed:1963`)

### BR-04 — Progress heartbeat resets liveness (F1)
`task_progress` for the current attempt of a RUNNING task advances `last_event_at`; progress on a non-running task or a superseded attempt is a no-op. This is what makes heartbeats reset the staleness timer consumed by orch-resilience. Related UC: UC-01. (`_handle_task_progress`, added F1)

### BR-05 — False-positive reconciliation (F2)
A `task_completed` over a `FAILED` task is accepted as `FAILED → COMPLETED` (and recorded in `anomalies` as `reconciled_false_positive_completion`) **only** when the prior failure reason ∈ {`stale_timeout`, `worker_exited_without_terminal`} (synthesized terminals). Any other `completed`-over-`FAILED`, or `completed` over a never-claimed task, still raises IllegalTransition. Related UC: UC-01. (`_handle_task_completed`, F2; ERR-04)

### BR-06 — Illegal transitions abort strict reduction
Every handler raises IllegalTransition on an unexpected source status; strict `reduce_all` propagates it (rejecting a bad log is a feature). Tolerant reduction records + skips instead. Related UC: UC-01, UC-02. (`_handle_task_*` handlers `:1795-2027`)

### BR-07 — Snapshot validate-or-fallback
A cached snapshot is used only after its boundary event is re-read and matches by seq + hash; any mismatch triggers a full replay. Both paths yield identical state. Related UC: UC-06. (`orch_core.py:2249`)

## 5. State Machine

### ST-01 — Task state machine

```
                 task_created
                      |
                      v
                 [ PENDING ] --promote(deps done + phase active)--> [ READY ]
                      |                                                  |
        task_skipped  |                                                  | task_claimed
                      v                                                  v
                 [ SKIPPED ]* <--task_skipped-- [READY]            [ RUNNING ] --task_progress--> (self, F1)
                                                                      |   |   \
                                             task_completed           |   |    \ task_failed
                                                    v                 |   |     v
                                              [ COMPLETED ]*          |   |  [ FAILED ] --task_scheduled_retry--> [ SCHEDULED ]
                                                                      |   |     |                                      |
                                        F2: task_completed (synth) ---+   |     | task_dlq                             | task_retried
                                        FAILED -> COMPLETED               |     v                                      v
                                                                          |  [ DLQ ]*                             [ PENDING ] (attempt+1)
                                                             task_dlq ----+
                                    (RUNNING/PENDING/SCHEDULED -> DLQ on cascade)
```
`*` = terminal (`is_terminal`: COMPLETED, SKIPPED, DLQ). `FAILED` is deliberately non-terminal.

| From | Event | To | Condition | Handler |
|------|-------|----|-----------|---------|
| (none) | task_created | PENDING | — | `_handle_task_created:1795` |
| PENDING | (promote) | READY | deps complete + phase active | `_try_promote_to_ready:1701` |
| READY | task_claimed | RUNNING | worker not already claimed | `_handle_task_claimed:1818` |
| RUNNING | task_progress | RUNNING | current attempt (F1) | `_handle_task_progress:1847` |
| RUNNING | task_completed | COMPLETED | — | `_handle_task_completed:1877` |
| RUNNING | task_failed | FAILED | — | `_handle_task_failed:1950` |
| FAILED | task_completed | COMPLETED | synthesized reason (F2) | `_handle_task_completed` (reconcile `:1903-1906`) |
| FAILED | task_scheduled_retry | SCHEDULED | — | `_handle_task_scheduled_retry:1980` |
| SCHEDULED | task_retried | PENDING | bump attempts | `_handle_task_retried:1995` |
| PENDING/READY | task_skipped | SKIPPED | — | `_handle_task_skipped:1928` |
| FAILED/RUNNING/PENDING/SCHEDULED | task_dlq | DLQ | — | `_handle_task_dlq:2013` |

ST-02 (phase state machine) is owned by orch-phases; the reducer implements it there.

## 6. Error Behaviors

| Situation | Raised | ERR | Description |
|-----------|--------|-----|-------------|
| Illegal transition (strict) | `IllegalTransition` | ERR-04 | enriched with seq/task/type; aborts `reduce_all` |
| Illegal transition (tolerant) | recorded `Violation` | ERR-04 | skipped, reduction continues |
| Broken chain / bad JSON | `CorruptedLogError` | ERR-03 | propagates in both strict and tolerant |
| Unknown event type | `UnknownEventType` | ERR-05 | replay rejects |

## 7. Cross-Domain Dependencies

| Domain | Type | Description |
|--------|------|-------------|
| orch-log | consumes | reads the event stream |
| orch-dispatch | produces (indirect) | its events drive task-state transitions |
| orch-resilience | synchronizes | reads `last_event_at` (F1), `last_failure_reason` (F2), `attempts` |
| orch-phases | synchronizes | phase handlers update phase state; exit checkers read derived state |
| orch-control | consumes | derives run_status, escalation, circuit_breaker from state |

## 8. Out of Scope

- Log persistence and integrity (orch-log).
- Retry eligibility / backoff (orch-resilience).
- Phase-gate evaluation (orch-phases).

## 9. Local Glossary

| Term | Definition |
|------|------------|
| Anomaly | A recorded, non-fatal irregularity (`state.anomalies`): duplicate claim, F2 reconciliation. |
| Boundary event | The last event covered by a snapshot; validated by seq + hash. |
| Violation | A tolerant-reduce record of a skipped illegal transition. |

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Initial orch-state spec (UC-01..06, BR-01..07, ST-01) | — |
