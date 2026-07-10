# Orchestration Spec — Glossary

> Version: 0.1.0 | Status: draft | Layer: permanent
> Controlled vocabulary for the orchestration-engine specification. Alphabetical.
> A domain spec may define local terms, but this global glossary wins on conflict.

| Term | Definition | Context |
|------|------------|---------|
| Append-only log | The single JSONL file (`.orch/log.jsonl`) to which events are only appended, never mutated; the sole source of truth (INV-01). | orch-log |
| Attempt | The 1-based execution count of a task; bumped by `task_retried`. Idempotency and straggler guards key on `(task_id, attempt)`. | orch-dispatch |
| Backoff | Delay before a retry: `min(base·2^(attempts-1), cap)·U(0.8,1.2)` (`backoff_seconds`). | orch-resilience |
| Circuit breaker | A tripped state that blocks further dispatch after a failure-rate threshold in a window; reset via `human_response`. | orch-resilience |
| Claim | Atomic `READY → RUNNING` transition under the global log lock (`claim_task`); the only guard against double-dispatch of a READY task. | orch-dispatch |
| DLQ | Dead-letter queue — terminal status for a task that cannot be retried; blocks phase exit until triaged. | orch-resilience |
| Event | An immutable record appended to the log; typed by `EventType` (EV catalog). | orch-log |
| Exit criterion | A phase-gate check implemented as Python (`check_*.py`), not prose (INV-11); emits `phase_exit_criterion_met` when satisfied. | orch-phases |
| Hash chain | Each event stores `prev_hash` + `hash` (SHA-256 of canonical JSON); `verify.py` walks it to prove integrity. | orch-log |
| Idempotency key | `(task_id, attempt, event_type)` — a duplicate is an audited no-op, never a fatal replay error (INV-04). | orch-state |
| Invariant | An architectural guarantee (P1–P12), prefixed `INV-NN`; stronger than a BR; BRs cite the INV they enforce. | globals |
| Least privilege | Each worker is granted only the tools it needs (INV-06); enforced in agent frontmatter `allowed-tools`. | orch-dispatch |
| Liveness gate | The `worker_liveness_expired` check the SubagentStop hook uses before synthesizing a terminal — same threshold as the reaper. | orch-resilience |
| Meta-orchestrator | The top-level `orchestrator.md` agent; a pure function of the log (INV-02) that dispatches phase orchestrators. | orch-control |
| Reaper | The stale-monitor path (`reap_stale_tasks`) that fails RUNNING tasks silent past their threshold, from Python. | orch-resilience |
| Reconciliation | Accepting a `FAILED → COMPLETED` when the FAILED was a synthesized false positive (F2); recorded as an anomaly. | orch-state |
| Reducer | The pure function that replays events into `OrchState`; strict (`reduce_all`) aborts on illegal transition, tolerant (`reduce_all_tolerant`) records + skips. | orch-state |
| Snapshot | A validated cache of derived state at a seq boundary (`.orch/state/snapshot.json`) enabling O(tail) reduction. | orch-state |
| Stale threshold | The silence window past which a RUNNING task is stale; resolved by task-type override → tier default → enum. | orch-resilience |
| Straggler | A late event from a superseded attempt (`event.attempt < task.attempts`); an idempotent no-op. | orch-state |
| Synthesized terminal | A `task_failed` emitted by the framework (reaper/hook), not the worker; reasons `stale_timeout` / `worker_exited_without_terminal`. | orch-resilience |
| Task tier | `critical` / `standard` / `bulk` — sets default max_attempts and stale threshold. | orch-dispatch |
| Worker | A leaf agent that claims one task, emits progress/terminal via `emit.py`, and produces artifacts. | orch-dispatch |
| Worker registry | `.orch/workers/*.json` entries the orchestrator writes at claim and removes after a confirmed terminal. | orch-dispatch |

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Initial controlled vocabulary | — |
