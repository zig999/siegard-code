# Orchestration Spec — Coverage Matrix (Phase 3)

> Version: 0.1.0 | Status: complete | Layer: semi-permanent
> Maps engine code modules to the spec artifact(s) that cover them, and records gaps.

## Code module → spec coverage

| Code module | Covered by | Coverage |
|-------------|-----------|----------|
| `lib/orch_core.py` — Event, append/claim/read/verify, LogLock, blobs | orch-log (spec+contract) | full |
| `lib/orch_core.py` — `_HANDLERS`, reducers, reduce_all/tolerant/workflow, snapshot | orch-state (spec+contract) | full |
| `lib/orch_core.py` — claim_task, promotion, worker registry | orch-dispatch (spec+contract) | full |
| `lib/orch_core.py` — should_retry, backoff, RetryPolicy, schedule_retry_if_due, stale/liveness, detect_stale, circuit | orch-resilience (spec+contract) | full (CONF-01 breaker gap) |
| `lib/orch_core.py` — phase handlers, `_precond_phase_transitioned` | orch-phases (spec+contract) | full |
| `skills/orch-log/scripts/*` | orch-log.contract §3 | full |
| `skills/orch-state/scripts/*` | orch-state.contract §3 | full |
| `skills/phase-*-rules/scripts/*` | orch-phases.contract §3 | full (test checkers present; test orchestrator deferred) |
| `hooks/on_subagent_stop.py`, `hooks/on_stop.py` | orch-resilience.contract §3, orch-control | full |
| `scripts/check_stale.py`, `circuit_breaker.py`, `dlq_triage.py` | orch-resilience.contract §3 | full |
| `scripts/preflight.py`, `classify_run_status.py`, `orch-infra/*` | orch-control (spec+contract) | full |
| `scripts/supervisor_tick.py`, `commands/u-supervise.md` | orch-control UC-08, orch-resilience BR-08 | full (E2 supervised auto-resume) |
| `agents/orchestrator*.md` | orch-control §4 (step protocol), orch-phases, orch-dispatch | structural (prompt bodies not line-spec'd) |
| `skills/orch-report/scripts/emit.py` (worker write path) | orch-dispatch BR-04, orch-log UC-01 | boundary (worker is a leaf agent, not a domain) |

## Identifier coverage

| Family | Count | Source |
|--------|-------|--------|
| EV (events) | 32 | event-catalog.md (+EV-31/32 supervised resume) |
| INV (invariants) | 12 | spec-map.md (P1–P12) |
| ST (state machines) | 4 | ST-01 task, ST-02 phase, ST-03 breaker, ST-04 run_status |
| ERR (failures) | 52 | error-catalog.md (9 exceptions + 15 reasons + 27 E-codes + E_NO_BASH) |
| UC (use cases) | 42 | 6 log-state-dispatch-phases(6 each) + resilience(9) + control(8) |
| FLOW / FL | 6 / 12 | flows/ |

## Known gaps (deferred, not covered)

| Gap | Reason |
|-----|--------|
| `orchestrator-test.md` (test phase) | deferred in the engine itself (`extras/phases.md`) — checkers exist, orchestrator not implemented |
| Worker internals (`u-*` leaf agents, `emit.py` guard-rail depth) | out of the 6-domain scope; the engine treats workers as opaque leaves |
| `spec_pipeline_return` / improve-flow control events | audit-only; modeled as EV, not as dedicated UCs |
| Agent prompt bodies | specified at the protocol/step level, not line-by-line (prompts, not code) |

## Open conformance items

CONF-01 (circuit breaker trip — RESOLVED v2.14.0) · CONF-02 (`subagent_invalid_response`
reason — RESOLVED v2.15.0) · CONF-03 (orphan `cancelled`) · CONF-04 (cached-verify CLI) ·
CONF-05 (heartbeat conformance in sdd/review/test — RESOLVED v2.16.0). See
`_validation/conformance-backlog.md`.

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Module→spec coverage, identifier counts, deferred gaps | — |
| 0.2.0 | 2026-07-10 | consulta-web-report-audit | minor | +supervisor_tick/u-supervise coverage; EV 30→32, ERR 51→52, UC 40→42, FLOW 5→6; CONF-05 resolved | — |
