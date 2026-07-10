# orch-control — Subsystem Specification

> Version: 0.1.0 | Status: draft | Layer: permanent
> Technical contract: `orch-control.contract.md`
> Fidelity: prescriptive. Cites `agents/orchestrator*.md`, `scripts/`, `orch_core.py`.

## 1. Overview

| Aspect | Value |
|--------|-------|
| Objective | Run the workflow as a pure function of the log: infra-check, derive state, dispatch, escalate, and hand off to the human — with every decision evidenced (INV-02, INV-08). |
| Core entity | The meta cycle + `run_status` classification + the escalation/human-response envelope. |
| Bounded context | Meta and phase orchestrators, heartbeat, escalation, human response, run-status classification, session recovery, foreground/Bash preflight. |
| Out of scope | Phase-gate rules (orch-phases); retry/breaker mechanics (orch-resilience). |

## 2. Actors

| Actor | Description | Permissions |
|-------|-------------|-------------|
| meta-orchestrator | Top-level control loop | run infra checks; declare/transition phases; spawn phase orchestrators |
| phase-orchestrator | Per-phase control | dispatch (orch-dispatch); emit heartbeat, escalation |
| operator | Human | `human_response` to escalations/gates |
| supervisor | Foreground watchdog (`/u-supervise` + `supervisor_tick.py`) | detect a stalled orchestrator; append `orchestrator_resume_requested`; re-invoke the meta, bounded by the resume budget |

## 3. Use Cases

### UC-01 — Run meta cycle
**Actor:** meta-orchestrator
**Pre:** Bash available (UC-06); log dir present.
**Post:** one cycle of: preflight → integrity → circuit check → derive state → dispatch/transition → heartbeat.
**Main flow:** `orch-infra` checks (preflight, integrity, circuit) → `reduce_all` → act on derived state → `orchestrator_heartbeat`.
**Alternative flows:** `Na` any infra check non-zero → cycle `blocked`. `Nb` breaker tripped → dispatch halted (orch-resilience ST-03).
**Related contract:** `orchestrator.md`, `orch-infra` scripts.

### UC-02 — Emit heartbeat
**Actor:** orchestrator
**Post:** `orchestrator_heartbeat {phase}` — the liveness signal `detect_stale_orchestrator` consumes.
**Related contract:** EV-20.

### UC-03 — Escalate
**Actor:** orchestrator
**Pre:** a condition needs a human or halts progress (see error-catalog E-codes).
**Post:** `escalation {code, severity, reason, evidence[]}`; may set `run_status` (UC-05).
**Related contract:** EV-23; escalation envelope.

### UC-04 — Process human response
**Actor:** operator (via meta)
**Post:** active escalation cleared; `escalated → active`; a `reset_circuit_breaker` action also clears the breaker + failure timestamps.
**Related contract:** `_handle_human_response:2034` (reset branch `:2044`); EV-24.

### UC-05 — Classify run status
**Actor:** meta / on_stop
**Post:** a `run_status` distinguishing "halt for human" from "genuine failure".
**Related contract:** `classify_run_status.py`; ST-04.

### UC-06 — Enforce foreground / Bash
**Actor:** meta-orchestrator
**Pre:** the Bash tool is available.
**Post:** if Bash is absent, fail fast with `E_NO_BASH` (Step 0) — orchestrators cannot run in a background sandbox.
**Related contract:** `preflight.py` `bash_available`; CLAUDE.md orchestration note.

### UC-07 — Recover session
**Actor:** next meta invocation
**Post:** state re-derived from the intact log; SCHEDULED tasks resumed (orch-resilience UC-09); stalled-orchestrator diagnostic acted on.
**Related contract:** FLOW-04.

### UC-08 — Supervised auto-resume
**Actor:** supervisor
**Pre:** an active phase has non-terminal tasks, no `orchestrator_heartbeat` within `ORCHESTRATOR_STALE_SECONDS`, AND no phase-task activity within the same window (TOTAL PHASE SILENCE — a live worker's `task_progress` advances `last_event_at` and keeps the phase alive, so it is not resumed).
**Post:** within the per-phase resume budget, `orchestrator_resume_requested` → a foreground re-invoke of the meta (non-destructive: the log is intact and state re-derives) → `orchestrator_resumed`. Budget exhausted → `escalation E23_resume_budget_exhausted` (run halts, awaiting_human). Bounded by `supervisor_policy` (orch-resilience BR-08).
**Related contract:** `scripts/supervisor_tick.py`, `commands/u-supervise.md`; EV-31/EV-32; ERR-52. Requires foreground Bash (UC-06 / `E_NO_BASH`). Automates FLOW-04 node K; destructive `verify_and_recover` stays manual (orch-resilience BR-07).

## 4. Business Rules

### BR-01 — Orchestrator is a pure function of the log (enforces INV-02)
The orchestrator holds no own state; every decision is derived from `reduce_all`. Re-invocation reconstructs identical control state. Related UC: UC-01, UC-07.

### BR-02 — Evidence-cited decisions (enforces INV-08)
Every dispatch/transition/escalation cites the events (`evidence` / `evidence_seq`) that justify it. Related UC: UC-03, orch-phases UC-05.

### BR-03 — Foreground requirement
The meta and phase orchestrators require the Bash tool; a background sandbox lacks it and stalls silently. Preflight’s `bash_available` fails fast with `E_NO_BASH`. Related UC: UC-06. (CLAUDE.md)

### BR-04 — Escalation → run_status mapping
`E99*` gates classify as `awaiting_human` (not a failure); critical escalations (e.g. `E04`) classify as `failed`; warnings as `needs_review`. Related UC: UC-05. (`classify_run_status.py:64,178,181`)

### BR-05 — Breaker blocks dispatch
While `state.circuit_breaker` is tripped, the cycle does not dispatch new work until reset (orch-resilience ST-03). Related UC: UC-01.

## 5. State Machine

### ST-04 — run_status (derived classification)

Not a transition machine — a classification of the whole run derived each cycle.

| run_status | Meaning | Source |
|------------|---------|--------|
| `empty` | no tasks | metrics |
| `active` | progressing | derived |
| `partial` | tasks incomplete, no halt | metrics |
| `completed` | all tasks completed | metrics |
| `completed_with_dlq` | all terminal, some DLQ | metrics |
| `escalated` | active escalation set | reducer |
| `awaiting_human` | active E99 gate | `classify_run_status` |
| `failed` | critical escalation | `classify_run_status` |
| `needs_review` | warning escalation | `classify_run_status` |
| `stale_orchestrator` | non-terminal tasks, no heartbeat | `detect_stale_orchestrator` |

> Source note: the `empty/partial/completed/completed_with_dlq/escalated` values are produced by `hooks/on_stop.py:_compute_metrics` (`:177`); `active` by `_m3_derive_run_status` (`orch_core.py:3754`); `awaiting_human/failed/needs_review/no_pending_escalation` by `classify_run_status.py`. There is no single `run_status` field in `orch_core.py`.

## 6. Error Behaviors

| Situation | Result | ERR | Description |
|-----------|--------|-----|-------------|
| Bash absent | fail fast `E_NO_BASH` | — | orchestrator cannot run |
| Infra check non-zero | cycle `blocked` | — | preflight/integrity/circuit gate |
| State reduction failed | escalation `E12_state_reduction_failed` | ERR-39 | illegal transition at control layer |
| Phase orchestrator error | escalation `E10_phase_orchestrator_error` | ERR-37 | internal error |
| Human gate | escalation `E99_*` | ERR-50 | awaiting operator |

## 7. Cross-Domain Dependencies

| Domain | Type | Description |
|--------|------|-------------|
| orch-state | consumes | derives all control state via `reduce_all` |
| orch-phases | synchronizes | declares/transitions phases |
| orch-dispatch | synchronizes | drives claim/spawn per cycle |
| orch-resilience | consumes | breaker gate + stalled-orchestrator diagnostic |
| orch-log | synchronizes | appends control/heartbeat/escalation events |

## 8. Out of Scope

- Exit-criteria checker internals (orch-phases).
- Retry/backoff/breaker mechanics (orch-resilience).

## 9. Local Glossary

| Term | Definition |
|------|------------|
| Meta cycle | One iteration of infra-check → derive → dispatch/transition → heartbeat. |
| Gate | A human-confirmation point via escalation + human_response. |
| E_NO_BASH | Fail-fast when the Bash tool is unavailable to an orchestrator. |

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Initial orch-control spec (UC-01..07, BR-01..05, ST-04) | — |
