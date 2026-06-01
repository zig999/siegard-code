# Escalation Codes — Master Reference

Cross-orchestrator reference for all escalation codes emitted in the workflow.
Each code appears in the event log as `escalation.data.code`.

> **Per-orchestrator tables** (in each orchestrator's `## Escalation codes` section) contain only the codes that orchestrator can emit. This file is the single source of truth for all codes.

---

## Code Table

| Code | Severity | Emitted By | Condition | Recovery Action |
|------|----------|------------|-----------|-----------------|
| `E04_critical_task_dlq` | critical | orchestrator-dev, orchestrator-test | Non-retryable impl or test task sent to DLQ | Inspect task spec at `task.spec`; resolve issue; re-invoke the relevant phase orchestrator |
| `E05_rejection_cycle_limit` | critical | orchestrator-sdd | `spec-writer` ≥ 3 attempts or `spec-validator` ≥ 2 attempts | Inspect spec for domain; manually resolve conflict; emit `human_response` to resume |
| `E06_dispatch_loop_limit` | critical | orchestrator-sdd | Dispatch loop reached 30 iterations without convergence — tasks stuck in ready/retry cycle | Inspect log for tasks with `status: ready` that are not progressing; check `select_worker.py`; reset stuck tasks and re-invoke |
| `E07_planning_failed` | critical | orchestrator-dev | Planning task failed and is non-retryable | Inspect `handoff-manifest.yaml`; verify SDD phase artifacts are complete; re-invoke |
| `E08_exit_criteria_not_met` | warning | orchestrator-sdd, orchestrator-dev, orchestrator-review, orchestrator-test | All tasks terminal but exit criteria not met | Review failing criterion detail in escalation evidence; fix and re-invoke |
| `E09_spec_divergences_found` | warning | orchestrator-review | QA found necessary spec divergences (`SPEC-DIVERGENCE:` markers) | Open CR for each divergence; update `openapi.yaml` or `.back.md`; re-invoke after CRs resolved |
| `E10_phase_orchestrator_error` | critical | orchestrator (meta) | Phase orchestrator returned `error` status and circuit breaker is tripped | Inspect log for the failing phase; run `circuit_breaker.py reset` after resolving; re-invoke |
| `E11_spec_input_missing` | critical | orchestrator-sdd | `spec-reviewer` failed non-retryably — required input files absent | Create missing `openapi.yaml` / `.spec.md` in `specs/<domain>/`; run spec-writer for domain; re-invoke |
| `E99_human_confirmation_required` | info | orchestrator-sdd | First dispatch gate — awaiting human confirmation to proceed | Emit `human_response` with `action: confirm_proceed` |
| `E99_human_approval_required` | info | orchestrator-review | QA verdicts collected — awaiting human approval before phase transition | Emit `human_response` with `action: approve`, `return_to_dev`, or `return_partial` |
| `E99_human_test_intervention_required` | warning | orchestrator-test | Test failures detected — human decision required | Emit `human_response` with `action: return_to_dev` or `action: accept_with_failures` |
| `E12_state_reduction_failed` | critical | orchestrator-sdd, orchestrator-dev, orchestrator-review, orchestrator-test | `reduce.py` exited with error — log may be corrupt or `orch_core.py` version mismatch | Run `python3 .claude/skills/orch-log/scripts/verify.py`; inspect tail of `.orch/log.jsonl` for malformed events; ensure deployed `orch_core.py` matches dist version |
| `E13_subagent_invalid_response` | critical | orchestrator (meta) | Phase orchestrator returned non-JSON or empty output — possible context overflow or agent startup failure | Re-invoke the orchestrator (transient tool errors often self-resolve); if persistent: inspect agent definition; reduce context by checkpointing |

---

## Severity Guide

| Severity | Meaning |
|----------|---------|
| `critical` | Pipeline halted; human intervention required before any work can resume |
| `warning` | Pipeline may continue but human review is strongly recommended |
| `info` | Normal gate requiring human input (not an error condition) |

---

## How to respond to an escalation

**Decision gates** (severity `info` — codes E99_*, E14, E15): respond by selecting an option in the conversation. The orchestrator captures your choice via `AskUserQuestion`, emits the `human_response` event to the log automatically, and resumes the workflow without requiring a separate invocation.

**Error conditions** (severity `warning` or `critical`): the workflow is stopped. Resolve the underlying issue as described in the escalation's `suggested_actions`, then re-invoke the orchestrator.

### Manual response (advanced / headless)

For programmatic or batch contexts where `AskUserQuestion` is not available:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent operator \
  --event-type human_response \
  --data '{"escalation_seq": <seq_of_escalation_event>, "action": "<action>", "notes": "<optional>"}'
```

Then re-invoke the relevant orchestrator to resume.

---

## Code allocation

| Range | Owner |
|-------|-------|
| E01–E03 | Reserved (DLQ triage — not yet allocated) |
| E04–E05 | Phase orchestrators (sdd, dev) |
| E06 | orchestrator-sdd (dispatch loop limit) |
| E07–E09 | Phase orchestrators (dev, review) |
| E10 | Meta-orchestrator |
| E11–E13 | Phase orchestrators (extended) + meta-orchestrator |
| E14–E17 | Reserved |
| E18–E19 | orchestrator-review (E18 auto-approval audit; E19 qa_mode classifier fallback) |
| E20 | orchestrator-review/dev (manifest stack unresolved — fail-closed, A3-F7) |
| E99 | Human confirmation / approval gates |
