# Orchestration Spec — Spec Map (Phase 0 output)

> Version: 0.1.0 | Status: draft | Layer: semi-permanent
> Maps engine code to target spec artifacts and inventories the planned UC/BR/INV/ST/EV
> per domain. This is the Phase-1 work list and the Phase-2 coverage baseline.
> Fidelity is **prescriptive**: the inventory below states the intended contract;
> Phase 2 records where current code diverges.

## Invariant registry (INV — from CLAUDE.md P1–P12)

| INV | Statement | Owning domain |
|-----|-----------|---------------|
| INV-01 | Log is the truth; all state is derived | orch-log |
| INV-02 | Orchestrator is a pure function of the log; no own state | orch-control |
| INV-03 | Append-only; corrections via new events | orch-log |
| INV-04 | Idempotency by key `(task_id, attempt, event_type)` | orch-state |
| INV-05 | Deterministic ordering; ties by `(priority, seq)` | orch-state |
| INV-06 | Least privilege; workers get only needed tools | orch-dispatch |
| INV-07 | Robustness via hooks; critical guarantees outside the LLM | orch-resilience |
| INV-08 | Evidence mandatory; every decision cites its events | orch-control |
| INV-09 | Every task belongs to exactly one phase | orch-phases |
| INV-10 | Phase transition is an auditable event | orch-phases |
| INV-11 | Exit criteria in testable code, not prompts | orch-phases |
| INV-12 | Current phase derived from the log, not stored | orch-phases |

## Domain 1 — orch-log

**Code:** `lib/orch_core.py` (Event 470–528; append_event 1293; _append_event_locked 1343; LogLock 150; read_events 650+; verify; claim_task 1414; blob externalization), `skills/orch-log/scripts/{append,claim,read,verify}.py`.

| Artifact | Planned inventory |
|----------|-------------------|
| `orch-log.spec.md` | UC: append event, claim task, read (filtered), verify chain, externalize blob, recover log. BR: hash-chain continuity, idempotency no-op, blob threshold, lock timeout. INV-01, INV-03, INV-04. ST: (none) EV owned: EV-28/29/30. |
| `orch-log.contract.md` | CLI: `append.py`, `claim.py`, `read.py`, `verify.py`. Lib: `append_event`, `claim_task`, `read_events(_filtered)`, `verify_chain(_cached)`. Event envelope schema (seq, event_id, ts, agent, event_type, task_id, attempt, data, prev_hash, hash). |

## Domain 2 — orch-state

**Code:** `lib/orch_core.py` (_HANDLERS 1985; apply_event 2012; reduce_all 2183; reduce_all_tolerant 2246; reduce_workflow; snapshot cache; TaskStatus 413; PhaseStatus 432), `skills/orch-state/scripts/{reduce,summary,current_phase,detect_mode}.py`.

| Artifact | Planned inventory |
|----------|-------------------|
| `orch-state.spec.md` | UC: reduce (strict), reduce (tolerant/diagnostic), reduce per-workflow, derive current phase, detect mode, snapshot write/validate. BR: straggler no-op, duplicate-terminal no-op, **F2 false-positive reconciliation**, snapshot validate-or-fallback. INV-04, INV-05. **ST-01 Task state machine** (pending→ready→running→{completed,failed,skipped,dlq}; failed→scheduled→pending; F1 progress heartbeat; F2 failed→completed). **ST-02 Phase state machine** (pending→active→exit_approved→completed; paused/resumed). EV: consumes all. |
| `orch-state.contract.md` | CLI: `reduce.py` (+`--workflow`), `summary.py`, `current_phase.py`, `detect_mode.py`. Lib: `apply_event`, `reduce_all`, `reduce_all_tolerant`, `reduce_workflow`. OrchState shape. |

## Domain 3 — orch-dispatch

**Code:** `lib/orch_core.py` (claim_task; register_worker 3170; get_active_workers; _try_promote_to_ready 1701; dispatch_policy), `agents/orchestrator-*.md` (dispatch steps), `skills/phase-*-rules/scripts/select_worker.py`.

| Artifact | Planned inventory |
|----------|-------------------|
| `orch-dispatch.spec.md` | UC: create task, promote to ready, claim & dispatch, register/unregister worker, select worker (routing), resolve dispatch concurrency. BR: claim requires READY, dep-gated promotion, max_concurrent cap, worker identity (`ORCH_WORKER_ID`), duplicate-claim no-op. INV-06, INV-09. EV owned: EV-01, EV-02, EV-17. |
| `orch-dispatch.contract.md` | CLI: `select_worker.py`. Lib: `claim_task`, `register_worker`, `get_active_workers`, `unregister_worker`. Worker registry entry schema. Backlog/task_contract references. |

## Domain 4 — orch-resilience

**Code:** `lib/orch_core.py` (should_retry 2932; backoff_seconds 2886; RetryPolicy 2851; **schedule_retry_if_due** ~2959; stale_threshold_seconds 2473; worker_liveness_expired 2505; stale_tasks 2529; reap_stale_tasks 2559; due_retries; circuit breaker; detect_stale_orchestrator 2372), `hooks/{on_stop,on_subagent_stop}.py`, `scripts/{check_stale,circuit_breaker,dlq_triage}.py`.

| Artifact | Planned inventory |
|----------|-------------------|
| `orch-resilience.spec.md` | UC: reap stale task, synthesize terminal on stop, **schedule retry atomically (F3/F4)**, evaluate retry eligibility, compute backoff, trip circuit breaker, route to DLQ, detect stale orchestrator, recover from crash. BR: **F1 progress resets timer**, structural-reason retry cap (≤1), stale threshold resolution order, liveness-gated synthesis (INV-07), breaker window/threshold, non-retryable→DLQ. INV-07. **ST-03 Circuit breaker** (closed→tripped→reset). EV owned: EV-05, EV-06, EV-08, EV-22. |
| `orch-resilience.contract.md` | CLI: `check_stale.py`, `circuit_breaker.py`, `dlq_triage.py`. Lib: `reap_stale_tasks`, `schedule_retry_if_due`, `should_retry`, `backoff_seconds`, `worker_liveness_expired`, `detect_stale_orchestrator`. Hook contracts (stdin/exit). |

## Domain 5 — orch-phases

**Code:** `skills/phase-*-rules/` (select_worker, check_*.py, exit-criteria.json), `extras/phases.md`, phase handlers in `lib/orch_core.py`.

| Artifact | Planned inventory |
|----------|-------------------|
| `orch-phases.spec.md` | UC: declare phases, enter phase, evaluate exit criteria, approve exit, transition phase, pause/resume. BR: exit criteria in code (INV-11), transition append-precondition (approved+evidence+human/E18 for review→test), one-task-one-phase (INV-09), current phase derived (INV-12). INV-09/10/11/12. **ST-02 Phase state machine** (shared with orch-state, owned here). EV owned: EV-10..EV-16. |
| `orch-phases.contract.md` | CLI: `check_*.py` (per phase) — the checker protocol (JSON out, exit 0, `{criterion,met,evidence,details}`). `select_worker.py` routing tables per phase. exit-criteria.json schema. |

## Domain 6 — orch-control

**Code:** `agents/orchestrator.md` (meta), `agents/orchestrator-{sdd,dev,review,test}.md`, heartbeat/escalation/human_response handlers, `skills/orch-infra/`, `hooks/on_stop.py`, `scripts/preflight.py`.

| Artifact | Planned inventory |
|----------|-------------------|
| `orch-control.spec.md` | UC: run meta cycle (preflight→integrity→circuit→dispatch), emit heartbeat, escalate, process human response, recover session, fail-fast on `E_NO_BASH`. BR: orchestrator is pure function of log (INV-02), evidence-cited decisions (INV-08), foreground/Bash requirement, heartbeat cadence, escalation→run_status mapping. INV-02, INV-08. **ST-04 run_status** (empty/active/partial/completed/completed_with_dlq/escalated/awaiting_human/failed/needs_review/stale_orchestrator — 10 values; authoritative list in `orch-control.spec.md` §5). EV owned: EV-20, EV-23, EV-24. |
| `orch-control.contract.md` | CLI: `preflight.py`, `run_integrity.py`, `run_circuit_check.py`, `classify_run_status.py`. Meta-orchestrator step protocol. Escalation/human_response envelope schemas. |

## Flows (process flows)

| FLOW | Title | Spans domains |
|------|-------|---------------|
| FLOW-01 | Dispatch cycle (preflight → reduce → select batch → claim → spawn → collect) | control, dispatch, log, state |
| FLOW-02 | Retry / backoff cycle (fail → schedule → due → retried → re-claim) | resilience, dispatch, state |
| FLOW-03 | Stale reaping + false-positive reconciliation (F1–F4) | resilience, state |
| FLOW-04 | Crash recovery (session end → on_stop reap → next invocation resumes) | control, resilience, log |
| FLOW-05 | Phase transition + gate (exit criteria → approved → transitioned) | phases, control |

## Coverage targets & method

- Every EV in `event-catalog.md` is **produced** and **consumed** by at least one UC.
- Every INV-01..12 is enforced by ≥1 BR that cites it.
- Every `.spec.md` claim describing current behavior cites `path:line`.
- Every escalation code / failure reason used is registered in `error-catalog.md`.
- Phase-2 validator emits VALID/INVALID per domain + a doc↔code conformance backlog
  (prescriptive gaps: where intended contract ≠ current code).

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Module→artifact map, INV registry, per-domain inventory, flows | — |
