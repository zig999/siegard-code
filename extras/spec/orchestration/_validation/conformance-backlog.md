# Orchestration Spec — Conformance Backlog (Phase 2)

> Version: 0.1.0 | Status: open | Layer: semi-permanent
> The prescriptive dividend: places where the **intended contract** (as specified)
> differs from the **current engine code**. These are NOT spec errors — the spec states
> the intended behavior; the code diverges. Each is a candidate engine fix (like F1–F4).

| ID | Severity | Domain | Gap | Evidence | Suggested resolution |
|----|----------|--------|-----|----------|----------------------|
| CONF-01 | ~~High~~ **RESOLVED (v2.14.0)** | orch-resilience | ~~The circuit breaker never appended `circuit_breaker_tripped`; `state.circuit_breaker` was always None, blocking was ephemeral, reset unreachable.~~ Fixed via option (a): `trip_circuit_if_due` (`orch_core.py`) appends `circuit_breaker_tripped` when the window first crosses the threshold, called from `run_circuit_check.py`. The breaker is now **sticky** — persisted in `state.circuit_breaker`, blocked until a manual reset (`circuit_breaker.py --reset` → `human_response`), and no longer relaxes on age-out. Reset tool + `on_stop` metric now live. | `trip_circuit_if_due` (`orch_core.py`); `run_circuit_check.py` (append on `should_trip`); config comment `orch_core.py:2699-2708` | Done. ST-03 now matches code. Tests: `tests/orch/test_conf01_circuit_trip.py` (7). |
| CONF-02 | ~~Medium~~ **RESOLVED (v2.15.0)** | orch-resilience / globals | ~~`should_retry` treated `subagent_invalid_response` as a structural reason, absent from `_VALID_FAILURE_REASONS`.~~ Resolved via drop: `subagent_invalid_response` removed from the `should_retry` structural set. It is a meta→phase-orchestrator concept (escalation E13, own retry logic in `orchestrator.md`), never a `task_failed` reason, so the entry was dead code. The structural set now equals {stale_timeout, worker_exited_without_terminal}. | `should_retry` (`orch_core.py`); `orchestrator.md:498-564` (real usage as an envelope reason + E13) | Done. Tests: `test_retry.py` (structural loops + `test_subagent_invalid_response_is_not_a_structural_task_reason`). |
| CONF-03 | Low | orch-state | `TaskStatus.CANCELLED` is an orphan: no `task_cancelled` event, no transition, not in `is_terminal`. | `TaskStatus` enum (`cancelled`); no handler references it | Wire an event + transition, or remove the enum member. |
| CONF-04 | Low | orch-log | `verify_chain_cached` (the O(tail) cached-verify path) has **no CLI exposure**; `verify.py` always calls `verify_chain`. | `verify.py` (calls `verify_chain` only); `verify_chain_cached` `orch_core.py:931` | Expose a `--mode cached` (or let `run_integrity.py` remain the only cached caller and note it library-only). |
| CONF-05 | ~~High~~ **RESOLVED (v2.16.0)** | orch-control | ~~Only `orchestrator-dev` emitted `orchestrator_heartbeat`; sdd/review/test never did, though `orch-control` UC-01/UC-02 mandate a heartbeat every phase-orchestrator cycle. `detect_stale_orchestrator` therefore could not distinguish a stalled orchestrator from a live one in those phases — the root of the 7.4h nightly stall in the `consulta-web-report` execution.~~ Fixed: sdd (Step 5.0), review and test (Step 4.0) now emit `orchestrator_heartbeat {phase}` at the top of every dispatch iteration, mirroring `orchestrator-dev`. The in-prompt `stale_timeout` synthesis in review/test (an F-03 violation) was replaced by the deterministic `check_stale.py` reaper. B(a) resume-in-band is emergent: `on_stop.py` + `check_stale.py` already consumed the heartbeat-absence signal — emitting the heartbeat was the only missing piece. | `orchestrator-{sdd,review,test}.md` (heartbeat emit at loop top); `detect_stale_orchestrator` phase filter (`orch_core.py:2476`); `on_stop.py:253-276` | Done. Tests: `tests/test_orchestrator_heartbeat_conformance.py` (heartbeat presence + canonical phase per orchestrator; F-03 no-in-prompt-synthesis guard). |

## Notes

- CONF-01 **resolved in v2.14.0** (sticky persisted breaker): `trip_circuit_if_due`
  appends the trip; `state.circuit_breaker` is now real, reset is reachable, and the
  `on_stop` metric reflects it. It mirrored the F1/F2 pattern (contract promised behavior
  the code did not realize) — and was fixed the same way.
- CONF-02 **resolved in v2.15.0** (dead structural-reason entry removed).
- CONF-05 **resolved in v2.16.0** (heartbeat conformance across all phase orchestrators).
  Raised from the `consulta-web-report` performance audit — the prescriptive spec
  (orch-control UC-01/UC-02) had already mandated the behavior the code omitted in 3 of 4
  phases; same F1/F2 pattern (contract promised, code diverged).
- CONF-03/04 remain open — latent inconsistencies with no observed incident; low urgency.
- None of these block the specs from being VALID — they are the *reason* to write
  prescriptive specs: the intended contract surfaced real drift in the engine.

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | CONF-01..04 raised from the prescriptive validation pass | — |
| 0.2.0 | 2026-07-10 | consulta-web-report-audit | minor | CONF-05 raised and resolved (v2.16.0) — heartbeat conformance in sdd/review/test | — |
