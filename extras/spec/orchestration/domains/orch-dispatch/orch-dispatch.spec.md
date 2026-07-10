# orch-dispatch — Subsystem Specification

> Version: 0.1.0 | Status: draft | Layer: permanent
> Technical contract: `orch-dispatch.contract.md`
> Fidelity: prescriptive. Current-behavior claims cite code paths.

## 1. Overview

| Aspect | Value |
|--------|-------|
| Objective | Turn ready work into running workers: create tasks, promote by dependency, claim atomically, route to the right worker, cap concurrency, and enforce least privilege (INV-06). |
| Core entity | `TaskState` (dispatch view) + the worker registry entry. |
| Bounded context | Task creation, promotion, claim/spawn, worker registry, routing, concurrency. |
| Out of scope | The atomic claim primitive (orch-log UC-02); retry/failure (orch-resilience); phase gates (orch-phases). |

## 2. Actors

| Actor | Description | Permissions |
|-------|-------------|-------------|
| phase-orchestrator | Creates and dispatches tasks for its phase | append `task_created`; `claim_task`; register workers; spawn agents |
| worker | Leaf agent | claim identity via `ORCH_WORKER_ID`; emit progress/terminal only |

## 3. Use Cases

### UC-01 — Create task
**Actor:** phase-orchestrator
**Pre:** the task's phase is declared; `type`, `tier`, `spec`, `deps` known.
**Post:** a `task_created` event; task enters PENDING and auto-promotes to READY if eligible.
**Related contract:** `append.py task_created` / event schema. Fields: `phase, tier, type, spec, deps` (+ optional `stack, workflow_id`).

### UC-02 — Promote to READY
**Actor:** system (reducer, on each relevant event)
**Post:** PENDING → READY when the task's phase is active AND all deps are terminal-complete.
**Alternative flows:** `1a` phase not active OR deps incomplete → stays PENDING.
**Related contract:** `_try_promote_to_ready` (`orch_core.py:1701`), `_deps_complete:1672`, `_phase_is_active:1697`.

### UC-03 — Claim and dispatch
**Actor:** phase-orchestrator
**Pre:** a READY task selected in the dispatch batch.
**Post:** an atomic claim (orch-log UC-02) followed by a worker spawn; a worker registry entry is written before the spawn.
**Main flow:**
1. Select a batch of READY tasks honoring deps and concurrency (UC-06).
2. For each: `claim_task` (atomic). If refused (`not_ready`/`task_not_found`), drop it — do NOT spawn.
3. `register_worker` (registry entry with `worker_id, task_id, attempt, phase`).
4. Spawn the routed worker (UC-05) with `ORCH_WORKER_ID` exported.
**Alternative flows:** `2a` claim refused → task dropped from batch (loser of double-dispatch race).
**Related contract:** `claim_task`, `register_worker`.

### UC-04 — Register / unregister worker
**Actor:** phase-orchestrator
**Post:** registry entry created at claim; removed after Step 6.4 confirms a terminal event in state.
**Related contract:** `register_worker:3302`, `unregister_worker:3419`, `get_active_workers:3428`.

### UC-05 — Select worker (routing)
**Actor:** phase-orchestrator
**Post:** the concrete worker agent for `(task.type, task.stack)` per the phase routing table.
**Related contract:** `phase-{name}-rules/scripts/select_worker.py`. (See `extras/phases.md` routing tables.)

### UC-06 — Resolve dispatch concurrency
**Actor:** phase-orchestrator
**Post:** a batch no larger than the phase's `max_concurrent`; critical-tier tasks first.
**Related contract:** `dispatch_policy` config (dev default `max_concurrent: 2`, `orch_core.py:2727`).

## 4. Business Rules

### BR-01 — Claim requires READY (enforces INV-05 substrate)
`claim_task` appends `task_claimed` only when the task is `READY` at claim time; otherwise it returns a structured refusal and no worker is spawned. Related UC: UC-03. (orch-log UC-02, `orch_core.py:1426`)

### BR-02 — Dependency- and phase-gated promotion (enforces INV-09)
A task promotes to READY only when its phase is active and every dependency is in a terminal-complete state. Related UC: UC-02. (`_try_promote_to_ready:1701`)

### BR-03 — Duplicate claim by same worker is a no-op
A repeat `task_claimed` for an already-RUNNING task by the same `worker_id` is recorded in `anomalies` and skipped, never a fatal transition (double-dispatch residue). Related UC: UC-03. (`_handle_task_claimed:1818`)

### BR-04 — Worker identity is fixed by the framework
A worker's event identity comes from `ORCH_WORKER_ID` (or registry fallback by `task_id+attempt`); the caller cannot override it. Related UC: UC-03, UC-04. (orch-report `emit.py`)

### BR-05 — Concurrency cap
No more than `max_concurrent` workers run per phase (dev default 2); critical-tier tasks are dispatched before standard/bulk. Related UC: UC-06. (`orch_core.py:2727`)

### BR-06 — Least privilege (enforces INV-06)
Each worker agent is granted only the tools it needs via `allowed-tools` frontmatter; read-only leaf workers may run in background, orchestrators require foreground (Bash). Related UC: UC-05. (CLAUDE.md P6; W01–W06 gate)

## 5. State Machine

N/A — dispatch drives transitions in ST-01 (orch-state) via the events it emits; it owns no separate machine.

## 6. Error Behaviors

| Situation | Result | ERR | Description |
|-----------|--------|-----|-------------|
| Claim of non-READY task | refusal `not_ready:<status>` | — | task dropped from batch |
| Claim of missing task | refusal `task_not_found` | — | task dropped |
| Worker routing failure | `task_failed(select_worker_failed)` | ERR-15 | non-retryable |
| Missing `ORCH_WORKER_ID` and no registry match | `emit.py` refuses | — | worker cannot emit |

## 7. Cross-Domain Dependencies

| Domain | Type | Description |
|--------|------|-------------|
| orch-log | synchronizes | atomic `claim_task`; append `task_created` |
| orch-state | produces | its events drive ST-01 |
| orch-phases | consumes | routing + concurrency come from phase rules |
| orch-resilience | synchronizes | dispatches due retries; consumes reaper/hook terminals |

## 8. Out of Scope

- Atomic claim primitive internals (orch-log).
- Retry scheduling and DLQ (orch-resilience).
- Exit-criteria evaluation (orch-phases).

## 9. Local Glossary

| Term | Definition |
|------|------------|
| Batch | The set of READY tasks an orchestrator claims+spawns in one cycle. |
| Registry entry | `.orch/workers/<worker_id>.json` written at claim, removed after a confirmed terminal. |
| Stack | `be` / `fe` / `fullstack` — routes to the language-specific worker. |

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Initial orch-dispatch spec (UC-01..06, BR-01..06) | — |
