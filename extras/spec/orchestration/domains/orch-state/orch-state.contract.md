# orch-state — Technical Contract

> Stack: Python 3.10+ stdlib | Version: 0.1.0 | Status: draft | Layer: permanent
> Business spec: `orch-state.spec.md`

## 1. Stack and Patterns

| Aspect | Value | Note |
|--------|-------|------|
| Reduction | pure function over events | strict `reduce_all`, tolerant `reduce_all_tolerant`, per-workflow `reduce_workflow` |
| Cache | `.orch/state/snapshot.json` | seq+hash validated; `ORCH_SNAPSHOT=0` disables |
| Dispatch of handlers | `_HANDLERS` table | `orch_core.py:2049` |

## 2. Data Model

### OrchState (derived; not persisted except as snapshot)

| Field | Type | Description |
|-------|------|-------------|
| `tasks` | map[task_id → TaskState] | all tasks and their derived status |
| `phases` | map[name → PhaseState] | phase lifecycle |
| `current_phase` | string \| null | derived active phase (INV-12) |
| `escalation` | object \| null | active escalation, if any |
| `circuit_breaker` | object \| null | tripped breaker state |
| `anomalies` | list[object] | non-fatal irregularities (duplicate claim, F2 reconcile) |
| `failure_timestamps` | list[ts] | for circuit-breaker windowing |
| `last_seq` | int | highest applied seq |

### TaskState (key fields)

| Field | Type | Notes |
|-------|------|-------|
| `status` | `TaskStatus` | pending/ready/running/scheduled/completed/skipped/failed/dlq/cancelled |
| `attempts` | int | 0 until first failure; set by `task_failed`, re-set by `task_retried` |
| `last_event_at` | ts | advanced by transitions + `task_progress` (F1) |
| `last_failure_reason` | string \| null | keys F2 reconciliation |
| `worker_id`, `claimed_at`, `failed_at` | — | provenance |
| `evidence` | list[seq] | seqs justifying the state (INV-08) |

> Conformance gap (CONF-03): `TaskStatus.CANCELLED` exists in the enum but is an
> **orphan** — no `task_cancelled` event, no handler transition into/out of it, and it
> is not in `is_terminal`. ST-01 does not model it. Either wire an event + transition or
> remove the enum member. Tracked in the backlog.

### Violation (tolerant reduce)

`{ seq, task_id, event_type, workflow_id, phase, message }` (`orch_core.py:2296`).

## 3. CLI Contracts (`skills/orch-state/scripts/`)

| Script | Args | stdout |
|--------|------|--------|
| `reduce.py` | `[--workflow <id>]` | full `OrchState` JSON; on illegal transition `{"status":"error","reason":"illegal_transition","detail":...}` exit 1 |
| `summary.py` | — | compact summary; exit 1 with `ERROR: illegal transition` on abort |
| `current_phase.py` | `[--from-stdin]` | `{"current_phase": <name|null>}`; illegal → `{"status":"error","reason":"illegal_transition","detail":...}` exit 1 |
| `detect_mode.py` | — | `{"mode": "new"|"resume", "workflow_id": ..., "last_seq": <n when log exists>}` (`detect_mode.py:16-49`) |

## 4. Library Contract (`orch_core`)

| Function | Signature | Pre / Post | Raises |
|----------|-----------|-----------|--------|
| `apply_event` | `(state, event) -> OrchState` | mutates + returns; unknown-effect types skipped (last_seq still advances) | IllegalTransition, UnknownEventType |
| `reduce_all` | `() -> OrchState` | strict; snapshot-accelerated | IllegalTransition, CorruptedLogError |
| `reduce_all_tolerant` | `() -> tuple[OrchState, list[Violation]]` | diagnostic; records+skips illegal | CorruptedLogError |
| `reduce_workflow` | `(workflow_id) -> OrchState` | isolates one workflow | IllegalTransition, CorruptedLogError |

## 5. Domain Events consumed

All EV-01..EV-30. Reducer-effecting: EV-01..EV-16, EV-22, EV-23, EV-24. Audit-only
(no reducer effect, `last_seq` still advances): EV-17..21, EV-25..30.

## 6. Out of Scope

- Log I/O and hash chain (orch-log contract).
- Retry policy and thresholds (orch-resilience contract).

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | OrchState/TaskState/Violation, CLI + library contracts | — |
