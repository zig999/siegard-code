# Siegard Code — Principles & Rules

---

```yaml
# ─────────────────────────────────────────────────────────────
# BLOCK 1 — WORKFLOW STRUCTURE
# ─────────────────────────────────────────────────────────────

WORKFLOW_STRUCTURE:
  rule: workflow_is_divided_into_phases
  invariants:
    - the basic unit of workflow organization is a phase
    - each phase MUST have exactly one orchestrator
    - each phase contains a set of tasks or a defined workflow executed by workers

# ─────────────────────────────────────────────────────────────
# BLOCK 2 — ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

ORCHESTRATOR_AUTHORITY:
  rule: orchestrator_is_sole_authority_for_its_phase
  invariants:
    - the orchestrator is the only agent with authority over its phase
    - only the orchestrator may spawn workers
    - only the orchestrator may define the operation mode
    - operation mode MUST be declared in the log before any worker is spawned
    - no external agent may override or bypass orchestrator decisions

ORCHESTRATOR_EXECUTION:
  rule: orchestrator_does_not_execute_tasks
  invariants:
    - the orchestrator MUST NOT execute tasks directly
    - every task MUST be executed by a designated worker

# ─────────────────────────────────────────────────────────────
# BLOCK 3 — EXECUTION MODEL
# ─────────────────────────────────────────────────────────────

STEP_DEPENDENCIES:
  rule: each_step_depends_on_previous_step_reaching_terminal_state
  invariants:
    - a step may only begin after all its dependencies have reached a terminal state
    - terminal states are: completed | skipped
    - a skipped step counts as terminal for dependency evaluation purposes
    - the orchestrator MUST check dependencies before dispatching any task

DECLARATIVE_TRUNCATION:
  rule: orchestrator_may_skip_unimpacted_steps_in_restricted_mode
  invariants:
    - in restricted mode, the orchestrator may skip steps whose artifacts are not impacted
    - every skipped step MUST be logged with an explicit reason before execution advances

# ─────────────────────────────────────────────────────────────
# BLOCK 4 — DISPATCH GOVERNANCE
# ─────────────────────────────────────────────────────────────

WORKER_SCOPE:
  rule: each_worker_spawn_operates_on_exactly_one_unit_of_work
  invariants:
    - each worker spawn MUST operate on exactly one unit of work — never more than one
    - parallelism is achieved via N spawns × 1 unit each — never 1 spawn × N units
    - a worker MUST NOT modify artifacts outside its assigned scope

RESOURCE_LIMITS:
  rule: orchestrator_must_enforce_concurrent_worker_ceilings
  invariants:
    - the orchestrator MUST enforce concurrent worker ceilings before each dispatch
    - total concurrent workers MUST NOT exceed the ceiling defined for the current mode
    - if a session cost signal is received, the orchestrator MUST pause and escalate before spawning additional workers

SHARED_RESOURCE_ACCESS:
  rule: orchestrator_must_prevent_concurrent_writes_to_shared_resources
  invariants:
    - the orchestrator MUST NOT place two workers in the same batch if their outputs intersect on a shared file or resource
    - conflict detection for shared resources is the exclusive responsibility of the orchestrator
    - resources with isolated scope are safe for parallel writes (each worker on a distinct unit)

DISPATCH_AUDIT:
  rule: every_batch_must_be_preceded_by_a_dispatch_decision_event
  invariants:
    - before emitting task_claimed for any batch, the orchestrator MUST emit a dispatch_decision event
    - the event MUST include the full batch, rationale, and all applied constraints
    - a batch without a prior dispatch_decision event is a protocol violation

WORKER_CONTEXT_BUDGET:
  rule: orchestrator_must_estimate_context_size_before_spawning
  invariants:
    - the orchestrator MUST estimate context size before spawning each worker
    - if estimated context exceeds the threshold, the orchestrator MUST summarize or split the input before spawning
    - context overflow causes silent truncation in the LLM — risk of data loss, not graceful failure
    - any applied mitigation MUST be recorded in the log

ARTIFACT_CONTRACT:
  rule: inter_worker_handoffs_must_use_standardized_files
  invariants:
    - all data exchanged between workers MUST be transmitted via standardized files
    - free-form or unstructured handoffs are prohibited
    - handoff file format MUST be declared and schema-compliant before use

# ─────────────────────────────────────────────────────────────
# BLOCK 5 — LOG & STATE
# ─────────────────────────────────────────────────────────────

LOG_AS_TRUTH:
  rule: log_is_the_sole_authoritative_source_of_state
  invariants:
    - all orchestrator state MUST be derived by replaying the log
    - no state may be stored outside the log and treated as authoritative
    - in-memory state is a cache of the log — it must never diverge
    - any discrepancy between in-memory state and the log MUST be resolved in favor of the log

APPEND_ONLY_LOG:
  rule: log_events_are_immutable_after_append
  invariants:
    - no event may be modified or deleted after it is written
    - corrections MUST be expressed as new events, not edits to existing ones

HASH_CHAIN_INTEGRITY:
  rule: every_event_must_carry_a_verified_hash_chain
  invariants:
    - each event MUST include the hash of the preceding event (prev_hash)
    - each event MUST include its own computed hash
    - the chain MUST be validated before any state derivation is performed
    - a broken chain MUST trigger recovery, not silent continuation

STATE_DERIVATION_ONCE:
  rule: reduce_all_must_be_called_exactly_once_per_decision_cycle
  invariants:
    - the orchestrator MUST call reduce_all() exactly once per decision cycle
    - results MUST be reused within the same cycle — redundant invocations are a protocol violation
    - current_phase and derived fields MUST be read from the reduce_all() output, not from a secondary call

# ─────────────────────────────────────────────────────────────
# BLOCK 6 — WORKER LIFECYCLE
# ─────────────────────────────────────────────────────────────

TERMINAL_EVENT_GUARANTEE:
  rule: every_worker_invocation_must_end_with_exactly_one_terminal_event
  invariants:
    - every worker invocation MUST produce exactly one terminal event: task_completed or task_failed
    - this guarantee is enforced by hooks executing outside the LLM — not by prompt instructions
    - if a worker stops without emitting a terminal event, the hook MUST synthesize task_failed with retryable=true
    - a worker invocation without a terminal event is an integrity violation

WORKER_REGISTRY:
  rule: orchestrator_must_register_worker_before_spawn
  invariants:
    - the orchestrator MUST write a worker registry entry before invoking any worker
    - the registry entry MUST include at minimum: worker_id, task_id, and attempt
    - hooks MUST use the registry to detect missing terminal events — not environment variables or in-memory state
    - a worker spawned without a registry entry cannot be recovered by the hook

WORKER_IDEMPOTENCY:
  rule: worker_operations_must_be_safe_to_retry
  invariants:
    - workers MUST check for artifact existence before writing
    - all file-producing operations MUST be idempotent — a retry after partial execution MUST not corrupt output
    - a worker MUST NOT assume it is the first execution of its task

# ─────────────────────────────────────────────────────────────
# BLOCK 7 — FAILURE HANDLING
# ─────────────────────────────────────────────────────────────

RETRY_POLICY:
  rule: retry_behavior_is_governed_by_tier_and_retryable_flag
  invariants:
    - each task is assigned a tier (critical | standard | bulk) that defines its max attempt count and backoff base
    - retryable=false on task_failed vetoes retry; retryable=true permits retry within tier max_attempts
    - structural failures (malformed input, schema violation) MUST cap at one retry
    - backoff MUST include jitter to prevent thundering herd

CIRCUIT_BREAKER:
  rule: sustained_failure_rate_must_trigger_human_escalation
  invariants:
    - the circuit breaker MUST evaluate failure rate over a rolling time window
    - when the failure threshold is exceeded, the orchestrator MUST stop spawning workers and escalate
    - the circuit MUST NOT reset automatically — it requires an explicit human_response event

DLQ_ESCALATION:
  rule: dlq_entries_require_escalation_before_phase_completion
  invariants:
    - a task that exhausts all retries MUST be moved to the dead-letter queue (DLQ)
    - DLQ state is terminal within a session — it cannot transition back to pending without operator action
    - the orchestrator MUST NOT approve phase exit while any task remains in DLQ
    - every DLQ entry MUST produce an escalation event with a structured reason code

# ─────────────────────────────────────────────────────────────
# BLOCK 8 — QUALITY GATES
# ─────────────────────────────────────────────────────────────

EXIT_CRITERIA_IN_CODE:
  rule: phase_exit_requires_testable_script_validation
  invariants:
    - phase exit criteria MUST be implemented as executable scripts, not as inline LLM assertions
    - exit criterion scripts MUST be runnable independently of the orchestrator
    - a phase MUST NOT transition without a successful exit criterion script invocation
    - LLM-generated pass/fail judgements are not valid substitutes for script output

GATE_SCHEMA_UNIFORMITY:
  rule: all_gate_scripts_must_return_a_schema_uniform_within_their_category
  scope:
    infra_gate_scripts:
      examples: [run_preflight, run_integrity, run_circuit_check]
      schema: {status, check, timestamp}
      status_values: [ok, blocked]
      exit_on_block: 1
    exit_criterion_scripts:
      examples: [check_all_qa_verdicts_approved, check_no_open_critical_findings, check_documentation_verified, check_all_impl_tasks_terminal, check_all_deliveries_qa_ready, check_no_open_prohibitions, check_handoff_manifest_approved, check_all_domains_validated, check_error_codes_synced, check_all_test_tasks_terminal, check_all_tests_passed, check_no_critical_failures]
      schema: {criterion, met, evidence}
      met_values: [true, false]
      exit_on_block: 0
      rationale: exit-criterion scripts return semantic evidence required by the orchestrator to construct phase_exit_criterion_met events; they always exit 0 because criterion failure is not a gate-script error
  invariants:
    - every gate script MUST return exactly the schema defined for its category
    - infra-gate scripts MUST exit with code 1 when status == blocked
    - exit-criterion scripts MUST exit with code 0 even when met == false; non-zero exit reserved for internal_error
    - gate scripts MUST NOT emit free-form diagnostic text as their primary output
    - new gate scripts MUST be classified into one of the declared categories

HOOKS_ENFORCE_INVARIANTS:
  rule: critical_guarantees_are_enforced_by_hooks_not_prompts
  invariants:
    - any invariant whose violation would produce an unrecoverable state MUST be enforced by a hook
    - hooks execute outside the LLM and are not subject to hallucination or context loss
    - prompt-level instructions are insufficient for guarantees that must hold unconditionally
    - hooks MUST be idempotent and MUST NOT raise exceptions that interrupt the session

# ─────────────────────────────────────────────────────────────
# BLOCK 9 — AUDITABILITY
# ─────────────────────────────────────────────────────────────

EVIDENCE_TRAIL:
  rule: every_task_decision_must_cite_the_events_that_justify_it
  invariants:
    - every task state record MUST carry an ordered list of event sequence numbers that produced it
    - an orchestrator decision without a traceable event sequence is a protocol violation
    - evidence references MUST use event seq numbers — not timestamps or free-form descriptions

OPERATOR_IDENTITY:
  rule: destructive_operations_require_explicit_operator_identity
  invariants:
    - any operation that modifies or truncates the log MUST require an explicit operator identity
    - identity MUST be confirmed via a dedicated flag (e.g. --confirm) — not inferred from context
    - the identity and timestamp of every destructive operation MUST be recorded as a new event before execution

STRUCTURED_FAILURE_STATES:
  rule: failure_reasons_must_use_closed_enum_codes
  invariants:
    - all failure reasons MUST be selected from a closed enumeration of reason codes
    - free-form strings are not permitted as reason values in any structured output
    - unrecognized reason codes in inputs MUST be rejected, not silently accepted

PAYLOAD_EXTERNALIZATION:
  rule: oversized_payloads_must_be_externalized_with_hash_reference
  invariants:
    - any event payload exceeding the inline threshold MUST be written to an external blob file
    - the event MUST store the blob hash — not the raw content
    - blob integrity MUST be verifiable by recomputing the hash from the file
    - inline storage of oversized payloads is a protocol violation, not a degraded mode
```
