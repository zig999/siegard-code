# Implementation Progress

Last updated: 2026-04-21

## Status summary

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Setup | ✅ Complete |
| 1 | `orch_core.py` — foundation | ✅ Complete + reviewed (1.8 deferred) |
| 2 | CLI skills | ✅ Complete (2.4 skipped — depende de 1.8 deferida) |
| 3 | Orchestrator single-phase | ✅ Complete (3.7 snapshot part deferred with 1.8) |
| 4 | Robustness | 🔄 In progress (4.1 done) |
| 5 | Phase lifecycle | ⏳ Not started |
| 6 | Production workers | ⏳ Not started |
| 7 | Hardening | ⏳ Not started |

---

## Phase 1 — `orch_core.py` ✅ (reviewed and hardened)

All tasks implemented and reviewed in `new_flow/dist2/.claude/lib/orch_core.py`.

**Test suite: 216 tests, 96% coverage.**

| Task | Description | Status | Tests |
|------|-------------|--------|-------|
| 1.1 | `Event` dataclass, `EventType`, `TaskStatus`, `PhaseStatus`, `Tier` enums | ✅ | `test_event.py` |
| 1.2 | Constants, paths, `LogLock`, `ensure_dirs` | ✅ | `test_locking.py` |
| 1.3 | `append_event` with hash chain | ✅ | `test_append.py` |
| 1.4 | `read_events`, `last_event`, `read_events_filtered` | ✅ | `test_read.py` |
| 1.5 | `verify_chain` (strict and audit modes), `VerifyResult` | ✅ | `test_verify.py` |
| 1.6 | `externalize_blob`, `load_blob_data`, `is_blob_ref` | ✅ | `test_blobs.py` |
| 1.7 | Reducer: `apply_event`, `reduce_all`, `TaskState`, `PhaseState`, `OrchState` | ✅ | `test_reducer.py` |
| 1.8 | Snapshots: `save_snapshot`, `latest_snapshot`, `reduce_incremental` | ⏩ Deferred | — |
| — | Integration tests: full orchestrator→worker→log round-trip | ✅ | `test_integration.py` |

**Task 1.8 deferred:** premature optimization. `reduce_all()` is sufficient. Add after Phase 3 with real performance data.

---

## Bugs fixed during Phase 1 review

| ID | Description | Fix |
|----|-------------|-----|
| B1 | `apply_event` raised `UnknownEventType` for valid events with no handler (`task_progress`, etc.) | No-op for known types without handlers; raise only for truly unknown |
| B2 | `read_events_filtered(phase=...)` silently skipped externalized blob events | Resolve blob before applying phase filter |
| B3 | `_iter_events_from_path` stopped silently on corrupt middle JSON; `verify_chain` returned `ok=True` | Raise `CorruptedLogError`; `verify_chain` catches and records as `parse_error` |
| A1 | Blob paths stored as CWD-relative strings; broke on directory change | Store path relative to `ORCH_DIR` (e.g. `blobs/evt_XYZ.json`); resolve via `ORCH_DIR / ref` |
| A2 | `_handle_task_completed` mutated `state.escalation` before raising `IllegalTransition` | Raise without side effects; escalation mechanism deferred to Phase 4 |
| S1 | `import copy as _copy` unused | Removed |
| S2 | `from typing import Iterator` declared mid-module | Moved to top |
| S4 | `TaskStatus.CANCELLED` listed as terminal with no handler producing it | Removed from `is_terminal()` |
| S5 | `new_event_id()` docstring claimed Crockford base32; actually UUID hex | Corrected docstring |
| S6 | `EventType.values()` created new set on every call | Cached as module-level `frozenset` |
| S7 | `VerifyResult` placed in wrong section | Moved to verification section |

---

## Decisions and architecture notes

| Decision | Reason |
|----------|--------|
| Task 1.8 (snapshots) deferred | No orchestrator yet; `reduce_all()` is fast enough |
| Blob `_blob_ref` relative to `ORCH_DIR` | Portability: project moves and CI don't break blob resolution |
| Reducer handlers no-op for unknown types | `task_progress` is worker-emittable; `reduce_all()` must not crash on it |
| `phase_transitioned` uses `from_phase`/`to_phase` | Matches `event-schema.md §3.5` |
| `_HANDLERS` uses `EventType.ESCALATION` | `WORKFLOW_ESCALATED` doesn't exist in the 21-type enum |
| Reducer tests use manually constructed `Event` objects | Avoids schema validation coupling in unit tests |
| `apply_event` temporarily mutates `event.data` for blob resolution | try/finally ensures original is always restored |

---

## Phase 2 — CLI Skills (in progress)

Implement in order (each task depends on the previous).

| Task | Description | Deliverables | Status |
|------|-------------|--------------|--------|
| 2.1 | `orch-log` skill — `append.py` | `.claude/skills/orch-log/scripts/append.py`, `SKILL.md` | ✅ 8 tests |
| 2.2 | `orch-log` skill — `read.py`, `verify.py` | `.claude/skills/orch-log/scripts/read.py`, `verify.py` | ✅ 16 tests |
| 2.3 | `orch-state` skill — `reduce.py`, `summary.py`, `current_phase.py` | `.claude/skills/orch-state/scripts/` | ✅ 13 tests |
| 2.4 | `orch-state` skill — `snapshot.py` | `.claude/skills/orch-state/scripts/snapshot.py` | ⏩ Skipped (depende de 1.8, deferida) |
| 2.5 | `orch-report` skill — `emit.py` (guard-rail: blocks orchestrator events) | `.claude/skills/orch-report/scripts/emit.py` | ✅ 11 tests |
| 2.6 | Hook `on_subagent_stop.py` | `.claude/hooks/on_subagent_stop.py` | ✅ 9 tests |

**Critical constraint for Task 2.5:** the guard-rail in `emit.py` is a security boundary.
Workers may only emit: `task_progress`, `task_completed`, `task_failed`.
Any other type must be rejected, even if the caller prompt requests it.

---

## Directory layout (dist2)

```
new_flow/dist2/
├── .claude/
│   ├── lib/
│   │   └── orch_core.py          ← foundation library (Phase 1 ✅)
│   ├── skills/                   ← Phase 2 target
│   ├── hooks/                    ← Phase 2 target (on_subagent_stop.py)
│   ├── agents/                   ← Phase 3 target
│   └── scripts/                  ← Phase 4 target
└── tests/
    ├── conftest.py
    ├── test_event.py
    ├── test_locking.py
    ├── test_append.py
    ├── test_read.py
    ├── test_verify.py
    ├── test_blobs.py
    ├── test_reducer.py
    └── test_integration.py
```

---

## Phase 3 — Orchestrator single-phase (in progress)

| Task | Description | Deliverables | Status |
|------|-------------|--------------|--------|
| 3.1 | `orchestrator.md` mínimo (single-phase, sem spawning) | `.claude/agents/orchestrator.md` | ✅ Validated |
| 3.2 | `test-worker.md` (dummy worker) | `.claude/agents/test-worker.md` | ✅ Validated |
| 3.3 | Orchestrator spawna worker + processa resultado | Updated `orchestrator.md` | ✅ Validated |
| 3.4 | Múltiplas tasks e deps | Updated `orchestrator.md` | ✅ Validated |
| 3.5 | Detecção de stale tasks | `orch_core.stale_tasks()` + `orchestrator.md` | ✅ 12 tests |
| 3.6 | DLQ cascade por dep falhada | Updated `orchestrator.md` + reducer | ✅ 11 tests |
| 3.7 | `on_stop.py` + métricas (snapshot parte deferida com 1.8) | `.claude/hooks/on_stop.py` | ✅ 7 tests |

**Note on `phase_entered` schema:** requires both `phase` and `order` fields. Discovered during 3.1 manual validation.

---

## Phase 4 — Robustness (in progress)

| Task | Description | Deliverables | Status |
|------|-------------|--------------|--------|
| 4.1 | `backoff_seconds`, `RetryPolicy`, `should_retry`, `tasks_ready_for_retry`, `load_config` | `orch_core.py` + `test_retry.py` | ✅ 31 tests |
| 4.2 | `task_scheduled_retry` + `task_retried` in orchestrator + reducer | Updated `orchestrator.md` + `test_retry_reducer.py` | ✅ 12 tests |
| 4.3 | Circuit breaker — `evaluate_circuit_state()`, reset script | `orch_core.py` + `scripts/circuit_breaker.py` + `test_circuit_breaker.py` | ✅ 21 tests |
| 4.4 | `verify_and_recover` — `--recover --confirm` mode | `orch_core.py` + `verify.py` + `test_verify_and_recover.py` | ✅ 18 tests |
| 4.5 | `preflight.py` — local and remote checks | `scripts/preflight.py` | ⏳ Not started |
| 4.6 | DLQ triage + escalations (E03, E04, E06) | `scripts/dlq_triage.py` | ⏳ Not started |

**Test count: 385 total.**
