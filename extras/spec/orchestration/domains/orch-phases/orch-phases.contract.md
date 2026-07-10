# orch-phases — Technical Contract

> Stack: Python 3.10+ stdlib | Version: 0.1.0 | Status: draft | Layer: permanent
> Business spec: `orch-phases.spec.md`

## 1. Stack and Patterns

| Aspect | Value | Note |
|--------|-------|------|
| Exit criteria | `check_*.py` per phase | JSON verdict, exit 0 |
| Routing | `select_worker.py` per phase | `(type[, stack]) → worker` |
| Declared criteria | `exit-criteria.json` | per phase-rules skill |
| Transition guard | `_precond_phase_transitioned` | append-time (orch-log BR-06) |

## 2. Data Model

### PhaseState (`PhaseStatus`: pending/active/exit_approved/completed/paused)

`{ name, order, status, entered_at, completed_at }`.

### Exit-criteria checker protocol (stdout JSON)

```json
{ "criterion": "all_impl_tasks_terminal", "met": true,
  "evidence": [101,102,103], "details": { "total": 12, "completed": 11, "dlq": 1 } }
```
Exit code 0 always (errors reported inside the JSON). (`extras/phases.md`)

## 3. Exit criteria by phase (`skills/phase-*-rules/scripts/`)

| Phase | Checkers |
|-------|----------|
| sdd | `check_handoff_manifest_approved`, `check_all_domains_validated`, `check_error_codes_synced` |
| dev | `check_all_impl_tasks_terminal`, `check_all_deliveries_qa_ready`, `check_no_open_prohibitions`, `check_acceptance_criteria_covered`, `check_spec_requirements_covered`, `check_backlog_scope`, `check_all_branches_integrated` |
| review | `check_all_qa_verdicts_approved`, `check_no_open_critical_findings`, `check_documentation_verified` |
| test | `check_all_test_tasks_terminal`, `check_all_tests_passed`, `check_no_critical_failures` (checkers implemented; `orchestrator-test.md` still deferred — see `extras/phases.md`) |

## 4. Library Contract

| Function | Signature | Notes |
|----------|-----------|-------|
| `_precond_phase_transitioned` | `(data, events) -> str\|None` | non-None reason rejects the transition append |
| phase handlers | reducer entries | `phase_declared/entered/exit_criterion_met/exit_approved/transitioned/paused/resumed` |

## 5. Phase transition data schema

`phase_transitioned`: `{ from_phase, to_phase, evidence_seq(int, references a prior event), workflow_id }`. `to_phase == "done"` for terminal transitions.

## 6. Out of Scope

- Worker agent internals; meta control loop (orch-control).

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Checker protocol, per-phase criteria, transition guard | — |
