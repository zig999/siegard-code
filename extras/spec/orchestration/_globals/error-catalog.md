# Orchestration Spec — Error & Failure Catalog

> Version: 0.1.0 | Status: draft | Layer: permanent
> The engine's analog of `error-codes.md`. Three closed taxonomies: reducer/library
> **exceptions**, structured task **failure/skip reasons**, and orchestrator
> **escalation codes**. Every code used in any domain spec MUST be registered here.

## 1. Exceptions (`lib/orch_core.py:35`)

Raised by the log/reducer; all subclass `OrchError`.

| ERR | Exception | Raised when | Handling |
|-----|-----------|-------------|----------|
| ERR-01 | `LockTimeoutError` | flock not acquired within `LOCK_TIMEOUT_S` | caller retries / aborts cycle |
| ERR-02 | `EventValidationError` | `data` missing required fields, or invalid enum (tier/reason) | append rejected at write-path |
| ERR-03 | `CorruptedLogError` | broken hash chain or invalid JSON in log | integrity fail; recovery required |
| ERR-04 | `IllegalTransition` | event implies a forbidden state transition | strict `reduce_all` aborts; tolerant records + skips |
| ERR-05 | `UnknownEventType` | event_type not in `EventType` | append/reduce rejected |
| ERR-06 | `BlobIntegrityError` | externalized blob hash mismatch | read fails |
| ERR-07 | `BlobNotFoundError` | blob reference cannot be resolved | read fails |
| ERR-08 | `ConfigError` | `.orch/config.json` invalid JSON | callers fall back to `{}` / enum defaults |
| ERR-09 | `PreconditionViolation` | append-time precondition returns a rejection reason | append rejected (write-path guard) |

## 2. Failure reasons (`_VALID_FAILURE_REASONS`, `lib/orch_core.py:582`)

Closed enum for `task_failed.data.reason` / `task_dlq.data.reason`. **Synthesized**
reasons are emitted only by the framework (reaper/hook), never by a worker — this
distinction keys the F2 false-positive reconciliation.

| ERR | reason | Origin | Retry semantics |
|-----|--------|--------|-----------------|
| ERR-10 | `worker_exited_without_terminal` | **synthesized** (on_subagent_stop) | structural — capped at 1 retry |
| ERR-11 | `stale_timeout` | **synthesized** (reaper) | structural — capped at 1 retry |
| ERR-12 | `cascade_from_dep` | orchestrator | non-retryable (dep in DLQ) |
| ERR-13 | `max_attempts_exceeded` | orchestrator | non-retryable → DLQ |
| ERR-14 | `non_retryable` | orchestrator | non-retryable → DLQ |
| ERR-15 | `select_worker_failed` | orchestrator | non-retryable |
| ERR-16 | `context_budget_exceeded` | orchestrator | non-retryable |
| ERR-17 | `delivery_artifact_missing` | orchestrator | retryable |
| ERR-18 | `missing_input_spec_files` | worker | structural |
| ERR-19 | `schema_violation` | worker | non-retryable |
| ERR-20 | `validation_failed` | worker | retryable |
| ERR-21 | `requirement_missing` | worker | non-retryable |
| ERR-22 | `improve_scope_missing` | worker | non-retryable |
| ERR-23 | `internal_error` | worker | retryable |
| ERR-24 | `dev_impact:stop_domain_task_contracts` | planner | control-flow (handoff-driven) |

Skip reasons (`_VALID_SKIP_REASONS`, `lib/orch_core.py:604`): `implementation_only_no_spec_change`,
`targeted_mode_step_not_in_scope`, `phase_short_circuit`.

> CONF-02 (RESOLVED, v2.15.0): `should_retry` used to list `subagent_invalid_response`
> in its structural-reason set, but that value is **not** in `_VALID_FAILURE_REASONS` —
> it is a meta→phase-orchestrator envelope/escalation concept (code
> `E13_subagent_invalid_response`, ERR-40), never a `task_failed` reason, so it could
> never match a task's `last_failure_reason`. It was removed from `should_retry`; the
> structural set now equals the real synthesized-reason enum {stale_timeout,
> worker_exited_without_terminal}.

## 3. Escalation codes (E-codes)

Emitted as `escalation.data.code`. `E99*` are human-gate codes (a gate is not a
failure). `E18` is an auto-approval. Curated from framework usage across
`agents/` and `skills/`.

| ERR | code | Severity | Meaning |
|-----|------|----------|---------|
| ERR-30 | `E03_*` (spec cycle limit) | critical | spec rejection/validation cycles exhausted |
| ERR-31 | `E04_critical_task_dlq` | critical | a critical-tier task entered DLQ |
| ERR-32 | `E05_rejection_cycle_limit` | warning | reviewer rejection limit reached |
| ERR-33 | `E06_dispatch_loop_limit` | warning | dispatch loop guard tripped |
| ERR-34 | `E07_context_budget_exceeded` / `E07_planning_failed` | warning | budget/planning failure |
| ERR-35 | `E08_exit_criteria_not_met` | warning | phase exit criteria unmet at gate |
| ERR-36 | `E09_spec_divergences_found` | warning | delivery diverged from spec |
| ERR-37 | `E10_phase_orchestrator_error` | critical | phase orchestrator internal error |
| ERR-38 | `E11_spec_input_missing` | critical | required spec input absent |
| ERR-39 | `E12_state_reduction_failed` | critical | `reduce_all` could not derive state (illegal transition) |
| ERR-40 | `E13_dlq_blocks_exit` / `E13_subagent_invalid_response` / `E13_improve_scope_unusable` | warning | DLQ blocks phase exit; invalid subagent response; unusable improve scope |
| ERR-41 | `E14_improve_spec_confirmation` | info | improve spec confirmation required |
| ERR-42 | `E15_session_overwrite_guard` | warning | session overwrite prevented |
| ERR-43 | `E16_shared_build_failure` | critical | shared build failed |
| ERR-44 | `E17_suite_parser_degraded` | warning | test-suite parser degraded |
| ERR-45 | `E18_auto_approval_granted` | info | automatic exit approval granted |
| ERR-46 | `E19_qa_mode_classifier_failed` | warning | QA mode classifier failed |
| ERR-47 | `E20_manifest_stack_unresolved` | critical | handoff manifest stack could not be resolved |
| ERR-48 | `E21_qa_not_on_integrated_main` | warning | QA not run on integrated main |
| ERR-49 | `E22_backlog_scope_violation` | warning | planner backlog exceeded declared scope |
| ERR-50 | `E99_human_approval_required` / `E99_human_confirmation_required` / `E99_human_test_intervention_required` | info | human gate — awaiting operator response |

### 3b. Preflight fail-fast (not an escalation event)

| ERR | code | Where | Meaning |
|-----|------|-------|---------|
| ERR-51 | `E_NO_BASH` | `preflight.py` (`check_bash_available:97`, reasons `:113-128`) | the Bash tool is unavailable to an orchestrator; the cycle fails fast at Step 0 (INV/orch-control BR-03). Not an `escalation` event — a preflight refusal string. |

## 4. Cross-check rules (Phase 2 validator)

1. Every `reason` used in a spec exists in §2; every escalation `code` in §3.
2. A `task_completed` reconciling a `FAILED` (F2) is permitted **only** when the prior
   reason ∈ {`stale_timeout`, `worker_exited_without_terminal`} (§2 synthesized set).
3. `E12_state_reduction_failed` (ERR-39) is the escalation raised on `ERR-04`
   (`IllegalTransition`) at the control layer — the two must stay linked.

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Exceptions, failure/skip reasons, escalation E-codes | — |
