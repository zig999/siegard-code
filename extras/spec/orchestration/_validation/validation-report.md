# Orchestration Spec — Validation Report (Phase 2)

> Version: 0.1.0 | Status: complete | Layer: semi-permanent
> Method: Siegard's cross-validation applied reflexively — internal consistency
> (ID cross-refs, event-catalog completeness, invariant coverage, prohibited terms)
> + doc↔code conformance (prescriptive: intended contract vs current code).
> Verification: 4 independent adversarial passes over the 23 artifacts and the code.

## Verdict per domain

| Domain | Verdict | Notes |
|--------|---------|-------|
| orch-log | **VALID** | 3 wrong-cites + 2 CLI-output mismatches corrected; CONF-04 (cached-verify CLI) recorded |
| orch-state | **VALID** | ST-01 handler cites + BR cites corrected; detect_mode/current_phase output corrected; CONF-03 (orphan `cancelled`) recorded |
| orch-dispatch | **VALID** | 2 wrong-cites corrected |
| orch-resilience | **VALID (w/ conformance)** | 9 wrong-cites corrected; CONF-01 (circuit breaker never persists a trip event) + CONF-02 (`subagent_invalid_response` reason) recorded |
| orch-phases | **VALID** | stale `(planned)` marker corrected; all guard/checker claims confirmed |
| orch-control | **VALID** | human_response cite + run_status source corrected |

No domain is INVALID: internal cross-references, invariant coverage, and state-machine
declarations are sound (see below). All defects were either spec-authoring errors (now
fixed) or code-side conformance gaps (backlog).

## Internal consistency (clean)

| Check | Result |
|-------|--------|
| ID cross-refs (UC/BR/INV/ST/EV/ERR/FL/FLOW) | OK — every reference resolves; no dangling INV-13 / ST-05 / out-of-range ERR |
| Invariant coverage INV-01..12 | OK — each enforced by ≥1 BR |
| State-machine declarations ST-01..04 | OK — every referenced state declared; no orphan transitions |
| Prohibited vague terms | OK — only conditional `may` (permissive, not vague); accepted |
| Surviving placeholders | OK — none |

## Corrections applied (spec-authoring errors)

Cause: many line citations drifted because the F1–F4 code changes (this session) shifted
`orch_core.py` by ~50–70 lines *after* the numbers were gathered, and some were cited
from memory. All corrected to the current file.

- **Line cites fixed:** append_event 1293→1305; `_validate_event_data` 611→623; blob ops
  re-paired (is_blob_ref 1140 / externalize 1150 / load 1167); all ST-01 handlers
  (created 1795, claimed 1818, progress 1847, completed 1877, failed 1950,
  scheduled_retry 1980, retried 1995, skipped 1928, dlq 2013); straggler guards
  1891/1963; `_HANDLERS` 2049; snapshot 2191/2226; dispatch_policy 2727; should_retry
  2936; backoff_seconds 2890; stale_threshold 2539; worker_liveness 2571; reap 2625;
  detect_stale 2438; RetryPolicy 2856; `_handle_human_response` 2034 (reset 2044);
  `_handle_task_dlq` 2013.
- **CLI-output mismatches fixed:** `verify.py` mode `{strict,audit}` + real output keys;
  `claim.py` `{claimed, event/reason}` shape; `detect_mode.py` values `new/resume`;
  `current_phase.py` illegal-output shape; `circuit_breaker.py` role (reset/status, not
  window-check); `backoff_seconds` param `jitter_range`.
- **Consistency gaps fixed:** `E_NO_BASH` registered (ERR-51); ST-04 count reconciled
  (7→10); event-catalog producer-scope note added; `(planned)` test-checker marker
  corrected.

## Confirmed-correct (high-value spot checks)

reduce_all 2249 · reduce_all_tolerant 2312 · reduce_workflow 2354 · Violation 2296 ·
`_precond_phase_transitioned` 1254 (+ full review→test human/E18 gate) · PhaseStatus 432 ·
ORCHESTRATOR_STALE_SECONDS 464 · MAX_INLINE_PAYLOAD 3500 · LOCK_TIMEOUT_S 10.0 ·
stale overrides (spec-* 1200/900) · RetryPolicy tier defaults 5·15·600 / 3·30·600 / 1·0·0 ·
schedule_retry_if_due (F3/F4) behavior · F1 heartbeat + F2 reconciliation (`_SYNTHESIZED_FAILURE_REASONS` 617-620).

## Outcome

23 artifacts, 6 domains → all VALID. Code-side conformance gaps CONF-01..04 are the
prescriptive dividend of this pass; see `conformance-backlog.md`.

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Phase-2 validation: 6/6 VALID, cites + CLI shapes corrected, CONF-01..04 raised | — |
