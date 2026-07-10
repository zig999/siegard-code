# Orchestration Spec — Event Catalog

> Version: 0.1.0 | Status: draft | Layer: permanent
> Source of truth: `EventType` enum (`lib/orch_core.py:325`). Every EV below MUST
> equal an enum member; the reducer effect is the `_HANDLERS` entry
> (`lib/orch_core.py:1985`) or "audit-only (no reducer effect)".
> Required `data` fields: `_REQUIRED_DATA_FIELDS` (`lib/orch_core.py:547`).

The log is the single source of truth (INV-01). Every state fact is derived by
replaying these events. An event is immutable once appended; corrections are new
events (INV-03). Idempotency key: `(task_id, attempt, event_type)` (INV-04).

## Group A — Task lifecycle (owned by orch-dispatch / orch-resilience)

| EV | event_type | Producer | Reducer effect | Consumers |
|----|-----------|----------|----------------|-----------|
| EV-01 | `task_created` | phase-orchestrator | Create task `PENDING`; promote to `READY` if phase active + deps done | dispatch, state |
| EV-02 | `task_claimed` | orchestrator (dispatch) | `READY → RUNNING`; set worker_id, claimed_at, last_event_at | state, on_subagent_stop |
| EV-03 | `task_progress` | worker (`emit.py`) | Heartbeat: advance `last_event_at` for current attempt of a RUNNING task (F1) | stale reaper, liveness gate |
| EV-04 | `task_completed` | worker (`emit.py`) | `RUNNING → COMPLETED`; F2 reconciles `FAILED → COMPLETED` when prior failure was synthesized | state, phase exit checkers |
| EV-05 | `task_failed` | worker / reaper / hook | `RUNNING → FAILED`; record reason, retryable | resilience, DLQ triage |
| EV-06 | `task_scheduled_retry` | orchestrator / reaper / hook (F3) | `FAILED → SCHEDULED`; set next_retry_at | dispatch (due_retries) |
| EV-07 | `task_retried` | orchestrator | `SCHEDULED → PENDING`; bump attempts; re-promote | dispatch |
| EV-08 | `task_dlq` | orchestrator | `FAILED/RUNNING/PENDING/SCHEDULED → DLQ` (terminal) | phase exit (blocks), dlq_triage |
| EV-09 | `task_skipped` | orchestrator | `PENDING/READY → SKIPPED` (terminal, declarative truncation) | phase exit |

## Group B — Phase lifecycle (owned by orch-phases)

| EV | event_type | Producer | Reducer effect | Consumers |
|----|-----------|----------|----------------|-----------|
| EV-10 | `phase_declared` | meta-orchestrator | Register workflow phase set | control, state |
| EV-11 | `phase_entered` | phase-orchestrator | Mark phase `ACTIVE`; set entered_at | dispatch, exit checkers |
| EV-12 | `phase_exit_criterion_met` | phase-orchestrator | Record a satisfied exit criterion | phase exit |
| EV-13 | `phase_exit_approved` | phase-orchestrator | Mark phase `EXIT_APPROVED` (precondition for transition) | control |
| EV-14 | `phase_transitioned` | meta-orchestrator | Advance current phase; append-precondition enforced (INV-11) | control, state |
| EV-15 | `phase_paused` | orchestrator | Mark phase `PAUSED` | control |
| EV-16 | `phase_resumed` | orchestrator | Mark phase `ACTIVE` (from paused) | control |

## Group C — Control & decision (owned by orch-control / orch-dispatch)

| EV | event_type | Producer | Reducer effect | Consumers |
|----|-----------|----------|----------------|-----------|
| EV-17 | `dispatch_decision` | orchestrator | Audit-only (batch/rationale/constraints) | audit, observability |
| EV-18 | `context_budget_evaluated` | orchestrator | Audit-only | cost gate |
| EV-19 | `operation_mode_declared` | orchestrator | Audit-only (mode) | detect_mode |
| EV-20 | `orchestrator_heartbeat` | orchestrator | Audit-only; consumed by `detect_stale_orchestrator` | stale-orchestrator detection |
| EV-21 | `spec_pipeline_return` | sdd-orchestrator | Audit-only (spec_change_status) | improve flow |

## Group D — Resilience (owned by orch-resilience)

| EV | event_type | Producer | Reducer effect | Consumers |
|----|-----------|----------|----------------|-----------|
| EV-22 | `circuit_breaker_tripped` | orchestrator / circuit_breaker.py | Set `state.circuit_breaker = tripped` | control (blocks dispatch) |

## Group E — Human loop (owned by orch-control)

| EV | event_type | Producer | Reducer effect | Consumers |
|----|-----------|----------|----------------|-----------|
| EV-23 | `escalation` | orchestrator | Set `state.escalation`; may set run_status `escalated` | meta, operator |
| EV-24 | `human_response` | operator (via meta) | Clear escalation; `escalated → active`; may reset breaker | control |

## Group F — Handoff & test suite

| EV | event_type | Producer | Reducer effect | Consumers |
|----|-----------|----------|----------------|-----------|
| EV-25 | `handoff_receipt` | dev-orchestrator | Audit-only; records manifest consumption | handoff validator |
| EV-26 | `suite_run_started` | test-orchestrator | Audit-only | test phase |
| EV-27 | `suite_run_completed` | test-orchestrator | Audit-only | test exit checkers |

## Group G — Infrastructure & audit (owned by orch-log)

| EV | event_type | Producer | Reducer effect | Consumers |
|----|-----------|----------|----------------|-----------|
| EV-28 | `snapshot` | reducer cache | Audit-only marker (state cache boundary) | reduce_all |
| EV-29 | `log_recovered` | operator (recovery) | Audit-only marker (truncation record) | integrity |
| EV-30 | `preflight_failed` | preflight.py | Audit-only | infra gate |

## Producer scope (coverage note)

Not every EV is produced by a UC inside the six spec'd domains — some producers sit
at the boundary:
- **Worker-emitted** (EV-03 `task_progress`, EV-04 `task_completed`, and worker-path
  EV-05 `task_failed`): produced by leaf workers via `emit.py` (orch-report skill),
  which are not one of the six domains but are constrained by orch-dispatch BR-04
  (identity) and orch-log UC-01 (append guard-rail).
- **Deferred test phase** (EV-26/EV-27): consumed by the `test` phase checkers, whose
  orchestrator (`orchestrator-test.md`) is deferred (`extras/phases.md`).
- **Control/audit** (EV-18 `context_budget_evaluated`, EV-21 `spec_pipeline_return`,
  EV-25 `handoff_receipt`, EV-30 `preflight_failed`): produced by orchestrators/scripts
  as audit markers; no reducer effect. These are in-scope by ownership (orch-control /
  orch-log) but are not modeled by a dedicated UC.

The "every EV produced and consumed by ≥1 UC" target (spec-map) is therefore met for
the task/phase/human-loop core; the boundary producers above are the tracked exceptions.

## Invariants referenced

- INV-01 (log is truth), INV-03 (append-only), INV-04 (idempotency key), INV-05
  (deterministic ordering by `(priority, seq)`), INV-08 (evidence mandatory),
  INV-10 (phase transition is an auditable event), INV-11 (exit criteria in code).

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Full EventType catalog (30 EV), grouped, with reducer effect | — |
