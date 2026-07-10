# orch-dispatch — Technical Contract

> Stack: Python 3.10+ stdlib + agent frontmatter | Version: 0.1.0 | Status: draft | Layer: permanent
> Business spec: `orch-dispatch.spec.md`

## 1. Stack and Patterns

| Aspect | Value | Note |
|--------|-------|------|
| Claim | `claim_task` under log lock | atomic check-and-append (orch-log) |
| Worker registry | `.orch/workers/*.json` | one file per active worker |
| Routing | `select_worker.py` per phase | `(type, stack) → worker agent` |
| Concurrency | `dispatch_policy` in config | dev default `max_concurrent: 2` |

## 2. Data Model

### Worker registry entry (`.orch/workers/<worker_id>.json`)

| Field | Type | Notes |
|-------|------|-------|
| `worker_id` | string | unique; also `ORCH_WORKER_ID` |
| `task_id` | string | claimed task |
| `attempt` | int | attempt claimed |
| `phase` | string | written at claim (avoids a reduce in the hook) |
| `registered_at` | ts | for `_infer_cause` elapsed hint |

### task_created data (event schema)

`{ phase, tier(critical|standard|bulk), type, spec, deps[] }` + optional `stack(be|fe|fullstack)`, `workflow_id`. (`_REQUIRED_DATA_FIELDS:547`)

## 3. CLI Contracts

| Script | Args | stdout |
|--------|------|--------|
| `phase-{name}-rules/scripts/select_worker.py` | task descriptor | `{"worker": "<agent-name>"}` or routing error |

Dispatch itself is orchestrated by the phase-orchestrator agents (Bash-driven), not a single CLI.

## 4. Library Contract (`orch_core`)

| Function | Signature | Pre / Post | Raises |
|----------|-----------|-----------|--------|
| `claim_task` | `(agent, task_id, attempt=1, data=None) -> (Event\|None, str\|None)` | atomic READY-check + claim | EventValidationError, IllegalTransition, LockTimeoutError |
| `register_worker` | `(...) -> None` | writes registry entry before spawn | OSError |
| `get_active_workers` | `() -> list[dict]` | current registry entries | — |
| `unregister_worker` | `(worker_id) -> None` | remove after confirmed terminal | — |
| `_try_promote_to_ready` | `(task, state) -> None` | PENDING→READY when eligible | — |

## 5. Config contract

```json
"dispatch_policy": { "dev": { "max_concurrent": 2 } }
```
Loaded by the orchestrator, clamped ≥ 1 by the dev state machine. (`orch_core.py:2727-2728`)

## 6. Out of Scope

- The `claim_task` internals (orch-log contract).
- Retry/backoff scheduling (orch-resilience contract).

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Registry entry + task_created schema, routing + library contracts | — |
