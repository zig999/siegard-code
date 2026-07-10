# Orchestration Spec — Conformance Backlog (Phase 2)

> Version: 0.1.0 | Status: open | Layer: semi-permanent
> The prescriptive dividend: places where the **intended contract** (as specified)
> differs from the **current engine code**. These are NOT spec errors — the spec states
> the intended behavior; the code diverges. Each is a candidate engine fix (like F1–F4).

| ID | Severity | Domain | Gap | Evidence | Suggested resolution |
|----|----------|--------|-----|----------|----------------------|
| CONF-01 | High | orch-resilience | The circuit breaker is specified (ST-03/UC-06) as a **persisted** state entered by a `circuit_breaker_tripped` event and reset by `human_response`. In code, **no path ever appends `circuit_breaker_tripped`** — `state.circuit_breaker` is never non-None at runtime; blocking is derived ephemerally at check time (`should_trip or already_tripped`), and the `circuit_breaker.py` reset tool is unreachable (aborts `no_cb_event`). | `evaluate_circuit_state` `orch_core.py:3133`; `run_circuit_check.py:74`; `circuit_breaker.py:108-113`; `_handle_circuit_breaker_tripped` `orch_core.py:2030` (only writer, never called from a trip path) | Either (a) make `run_circuit_check` append `circuit_breaker_tripped` when `should_trip` (persist the state; makes reset reachable), or (b) re-spec ST-03 as an ephemeral check-time gate and delete the dead reducer/reset path. Decision needed. |
| CONF-02 | Medium | orch-resilience / globals | `should_retry` treats `subagent_invalid_response` as a structural failure reason, but it is **absent from `_VALID_FAILURE_REASONS`** — a `task_failed` with that reason would be rejected at append. | `should_retry` structural set `orch_core.py:2951-2957`; `_VALID_FAILURE_REASONS` `orch_core.py:582`; only `E13_subagent_invalid_response` escalation exists | Either add `subagent_invalid_response` to `_VALID_FAILURE_REASONS`, or drop it from the `should_retry` structural set (it is currently unreachable as a reason). |
| CONF-03 | Low | orch-state | `TaskStatus.CANCELLED` is an orphan: no `task_cancelled` event, no transition, not in `is_terminal`. | `TaskStatus` enum (`cancelled`); no handler references it | Wire an event + transition, or remove the enum member. |
| CONF-04 | Low | orch-log | `verify_chain_cached` (the O(tail) cached-verify path) has **no CLI exposure**; `verify.py` always calls `verify_chain`. | `verify.py` (calls `verify_chain` only); `verify_chain_cached` `orch_core.py:931` | Expose a `--mode cached` (or let `run_integrity.py` remain the only cached caller and note it library-only). |

## Notes

- CONF-01 is the most consequential: the breaker "works" only as an ephemeral per-cycle
  gate; an operator cannot see or reset a persisted breaker, and `on_stop` metrics
  reading `state.circuit_breaker` always sees `None`. This mirrors the F1/F2 pattern
  (contract promised behavior the code did not realize).
- CONF-02/03/04 are latent inconsistencies with no observed incident; low urgency.
- None of these block the specs from being VALID — they are the *reason* to write
  prescriptive specs: the intended contract surfaced real drift in the engine.

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | CONF-01..04 raised from the prescriptive validation pass | — |
