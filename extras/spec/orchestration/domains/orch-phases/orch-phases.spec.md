# orch-phases — Subsystem Specification

> Version: 0.1.0 | Status: draft | Layer: permanent
> Technical contract: `orch-phases.contract.md`
> Fidelity: prescriptive. Cites `skills/phase-*-rules/`, `extras/phases.md`, `orch_core.py`.

## 1. Overview

| Aspect | Value |
|--------|-------|
| Objective | Sequence a workflow through phases (`sdd → dev → review → test`) with code-checked exit criteria and auditable transitions. |
| Core entity | `PhaseState` + the exit-criteria checker contract. |
| Bounded context | Phase declaration/entry, exit-criteria evaluation, exit approval, transition, pause/resume. |
| Out of scope | Worker routing internals (orch-dispatch); the meta control loop (orch-control). |

## 2. Actors

| Actor | Description | Permissions |
|-------|-------------|-------------|
| meta-orchestrator | Declares phases; performs transitions | append `phase_declared`, `phase_transitioned` |
| phase-orchestrator | Enters phase; evaluates and approves exit | append `phase_entered`, `phase_exit_criterion_met`, `phase_exit_approved` |
| operator | Confirms gates | `human_response(approve)` for review→test |

## 3. Use Cases

### UC-01 — Declare phases
**Actor:** meta-orchestrator
**Post:** the workflow's phase set is registered (`phase_declared`).
**Related contract:** event schema `{workflow_id, phases[]}`.

### UC-02 — Enter phase
**Actor:** phase-orchestrator
**Post:** phase marked ACTIVE with `entered_at`; its tasks may promote (orch-dispatch UC-02).
**Related contract:** `phase_entered {phase, order, workflow_id}`.

### UC-03 — Evaluate exit criteria
**Actor:** phase-orchestrator
**Pre:** all phase tasks terminal (per phase rules).
**Post:** one `phase_exit_criterion_met` per satisfied criterion.
**Main flow:** run every `check_*.py` for the phase; emit criterion-met for each `met: true`.
**Alternative flows:** `Na` a criterion unmet → escalation `E08_exit_criteria_not_met`. `Nb` a DLQ task present → `E13_dlq_blocks_exit` (DLQ is not terminal-for-exit). 
**Related contract:** checker protocol; `exit-criteria.json`.

### UC-04 — Approve exit
**Actor:** phase-orchestrator
**Pre:** all exit criteria met.
**Post:** phase marked EXIT_APPROVED (`phase_exit_approved {phase, criteria_met, next_phase, workflow_id}`) — the precondition for a forward transition.

### UC-05 — Transition phase
**Actor:** meta-orchestrator
**Pre:** a `phase_exit_approved` for `from_phase` precedes; `evidence_seq` references a prior event; for `review→test`, a `human_response(approve)` OR an `E18` auto-approval exists.
**Post:** `phase_transitioned {from_phase, to_phase, evidence_seq, workflow_id}` (INV-10); current phase advances (INV-12).
**Alternative flows:** `Pa` missing approval/evidence/human-gate → PreconditionViolation (ERR-09), append rejected. Return transitions (review→dev, test→dev/review) are exempt from the forward gate.
**Related contract:** `_precond_phase_transitioned` (`orch_core.py:1254`).

### UC-06 — Pause / resume phase
**Actor:** orchestrator
**Post:** `phase_paused {phase, reason}` → PAUSED; `phase_resumed {phase, paused_seq}` → ACTIVE.

## 4. Business Rules

### BR-01 — Exit criteria live in code (enforces INV-11)
Every exit criterion is a `check_*.py` returning a JSON verdict, never prose. A phase cannot exit on an unverifiable claim. Related UC: UC-03. (`extras/phases.md`; `phase-*-rules/scripts/`)

### BR-02 — Transition is a guarded, auditable event (enforces INV-10)
A forward `phase_transitioned` is append-rejected unless a matching `phase_exit_approved` precedes it, `evidence_seq` references a real prior event, and (for `review→test`) a human approve or `E18` exists. Return transitions are exempt. Related UC: UC-05. (`_precond_phase_transitioned:1254`)

### BR-03 — One task, one phase (enforces INV-09)
Every task belongs to exactly one phase; promotion and exit checks are scoped by phase. Related UC: UC-02, UC-03.

### BR-04 — Current phase is derived (enforces INV-12)
The active phase is derived from the log, never stored outside it. Related UC: UC-05. (orch-state UC-04)

### BR-05 — DLQ blocks exit
A task in DLQ blocks `all_impl_tasks_terminal` / test transition; DLQ is terminal for the task but not "done" for the phase. Related UC: UC-03. (`E13_dlq_blocks_exit`)

## 5. State Machine

### ST-02 — Phase state machine (`PhaseStatus`, `orch_core.py:432`)

```
[ pending ] --phase_entered--> [ active ] --phase_exit_approved--> [ exit_approved ] --phase_transitioned--> [ completed ]
                                   |  ^
                       phase_paused|  | phase_resumed
                                   v  |
                                [ paused ]
```

| From | Event | To | Condition |
|------|-------|----|-----------|
| pending | phase_entered | active | — |
| active | phase_exit_approved | exit_approved | all criteria met (UC-03) |
| exit_approved | phase_transitioned | completed | precondition satisfied (BR-02) |
| active | phase_paused | paused | — |
| paused | phase_resumed | active | — |

## 6. Error Behaviors

| Situation | Result | ERR | Description |
|-----------|--------|-----|-------------|
| Exit criteria unmet | escalation `E08` | ERR-35 | phase held at gate |
| DLQ task present at exit | escalation `E13_dlq_blocks_exit` | ERR-40 | must triage first |
| Transition without approval/evidence/human | `PreconditionViolation` | ERR-09 | append rejected |
| Auto-approval granted | escalation `E18` | ERR-45 | review→test allowed |

## 7. Cross-Domain Dependencies

| Domain | Type | Description |
|--------|------|-------------|
| orch-state | synchronizes | phase handlers update ST-02; checkers read derived state |
| orch-dispatch | produces | routing/concurrency come from phase rules |
| orch-log | synchronizes | transition append-precondition |
| orch-control | consumes | meta-orchestrator drives declaration + transition |

## 8. Out of Scope

- Worker routing tables (documented per phase in orch-dispatch UC-05 / `extras/phases.md`).
- The meta control loop and escalation plumbing (orch-control).

## 9. Local Glossary

| Term | Definition |
|------|------------|
| Exit criterion | A phase-gate check as code; emits `phase_exit_criterion_met` when satisfied. |
| Return transition | A backward transition (review→dev, test→dev/review) exempt from the forward gate. |
| Gate | A human-confirmation point expressed via escalation + human_response. |

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Initial orch-phases spec (UC-01..06, BR-01..05, ST-02) | — |
