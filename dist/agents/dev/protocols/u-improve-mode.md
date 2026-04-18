## Improve Mode Protocol

Activated when the Orchestrator detects an `improve_scope` block in `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md`.

> **Scope:** this protocol governs every intentional change routed through `/u-improve` — bug fixes, tweaks, and enhancements. The former `u-bug-mode.md` protocol was merged into this file. Branching between lean and full pipelines is driven by `improve_scope.execution_policy.pipeline`, which `/u-improve` derives at Step 2.6.

---

### improve_scope block format

Written by `/u-improve` to the session log. Schema:

```yaml
improve_scope:
  description: "<single objective sentence>"
  type: spec_change_required | implementation_only
  spec_change_status: pending_spec | completed | divergence_accepted | not_required | failed
  affected_specs:
    - path: "<relative path from SPECS_DIR>"
      sections: ["§N", "§N"]
      change_summary: "<one sentence>"
  estimated_task_contracts: <integer>
  planner_required: true | false
  planner_skip_reason: "<reason — present only when planner_required: false>"
  execution_policy:
    pipeline: lean | full
    regression_test_required: true | false
    planner_required: true | false
  handoff_manifest_id: "<HANDOFF-... — populated by spec-orchestrator return contract>"
```

`execution_policy` semantics (derived by `/u-improve` Step 2.6):
- `pipeline: lean` — visual/cosmetic fix with no spec impact; Developer patches directly, no Planner, no regression test, QA smoke validates.
- `pipeline: full` — every other case; Planner → Developer → QA runs the standard cycle.
- `regression_test_required: true` — Developer MUST write a failing test that reproduces the defect or asserts the new behavior BEFORE changing production code (TDD).
- `regression_test_required: false` — change is declarative (typo, wording, pure spec rewrite) or strictly visual; skip the regression test step.

`spec_change_status` semantics:
- `pending_spec` — **non-terminal** transient state written by `/u-improve` Step 3a (write-before-confirm). Indicates the spec pipeline is in flight or awaiting confirmation. `/u-dev` MUST refuse to start.
- `completed` — specs updated via /u-spec fast-track; `/u-dev` may proceed
- `divergence_accepted` — human declined spec update; divergence is recorded; `/u-dev` may proceed
- `not_required` — type was implementation_only; no spec change was needed
- `failed` — spec pipeline reached a terminal failure state (envelope return contract); `/u-dev` MUST refuse to start until human resolves

---

### Orchestrator pre-activation checks

Before activating any agent, the Orchestrator validates the scope block:

```
improve_scope block present?
  → No  → mode detection error — halt and notify human
  → Yes → continue

spec_change_status = pending_spec?
  → NON-TERMINAL state — DO NOT activate any agent.
  → Enter Halt-await-spec mode (see below). Emit structured status to human; do NOT
    ask A/B/C-style questions about how to proceed. The /u-spec pipeline (or its
    abort/failure path) is responsible for transitioning this status.

spec_change_status = failed?
  → Terminal failure state — DO NOT activate any agent.
  → Halt and emit structured status `spec_pipeline_failed` to human, including
    failure_reason from the latest spec_pipeline_return block. Human must resolve
    (re-run /u-spec, accept divergence, or abort improve) before /u-dev can proceed.

spec_change_status = completed?
  → Specs are authoritative — Planner reads affected_specs directly
  → If handoff_manifest_id is present in the scope block, validate the version of
    each affected_specs entry against the manifest; halt on mismatch.

spec_change_status = divergence_accepted?
  → Record in {SPECS_DIR}/spec-divergences.md:
      SPEC-DIVERGENCE-ACCEPTED: improve — {description} — {affected_specs paths}
  → Continue — Planner uses codebase as reference (no approved spec for affected area)

spec_change_status = not_required?
  → Continue normally
```

### Halt-await-spec mode

Activated when `spec_change_status = pending_spec`. In this mode:
- Emit one structured status block to the human and STOP. Do not prompt A/B/C.
- The status block names: the envelope id (if present), the expected next event
  (spec pipeline return), and the suggested human actions (re-run /u-spec, mark
  divergence_accepted manually, or abort).
- Resume happens only when the spec_change_status field transitions to a terminal
  state (`completed`, `divergence_accepted`, `failed`).

```yaml
halt_state: spec-pipeline-running
envelope_id: "{IMPROVE-...}"   # if present in handoff_envelope block
awaiting: spec_pipeline_return
suggested_actions:
  - wait_for_spec_pipeline
  - mark_divergence_accepted_manually
  - abort_improve
```

---

### Planner activation

The Planner receives:

```yaml
mode: improve
scope:
  affected_specs: <list from improve_scope.affected_specs>
  estimated_task_contracts: <from improve_scope>
```

**Planner reads ONLY the files listed in `affected_specs`.** It does NOT scan `{SPECS_DIR}` globally.

For each affected spec, the Planner reads only the sections listed in `improve_scope.affected_specs[*].sections`.

Task Contract `origin` field: `improve` (no sequential number).

References in improve mode:

```yaml
# spec_change_status = completed: use spec files
references:
  - path: "{SPECS_DIR}/{affected_spec.path}"
    section: "{affected_spec.sections joined}"
    version: "<from spec frontmatter or git hash>"

# spec_change_status = divergence_accepted or not_required: use codebase
references:
  - path: "codebase"
    section: "Developer discovers via inspection — scope: {affected_specs paths}"
```

---

### Pipeline branching — lean vs full

The Orchestrator reads `execution_policy.pipeline` from the scope block:

```
execution_policy.pipeline = lean?
  → Route directly to Developer — no Planner, no UI Agent, no TDD
  → Pass affected_specs (if any) and description as execution context
  → Developer creates branch `fix/visual-<short-description>` (e.g., fix/visual-misaligned-button)
  → Commit: `fix(visual): <description>`
  → Developer makes the smallest possible change (CSS, token, text) — no logic
  → QA validates smoke: matches expected behavior, no regression in adjacent states
     (hover, disabled, mobile); writing an automated test is NOT required

execution_policy.pipeline = full?
  → Standard pipeline: Planner → [UI Agent if needed] → Developer → QA
  → Planner activation and UI Agent evaluation follow the rules below
```

**Lean pipeline boundary.** If during a lean fix the Developer identifies that the change involves logic, state management, or a shared component, the Developer MUST stop the fix immediately, record `PIPELINE-PROMOTION: TC-XX — <reason>` in the session log, and wait for human confirmation before proceeding under the full pipeline.

#### Planner activation (full pipeline only)

The Orchestrator reads `planner_required` from the scope block:

```
planner_required: false AND human confirmed skip (recorded in log)?
  → Route directly to Developer
  → Pass affected_specs as execution context
  → Skip Planner, UI Agent (unless visual change requires it), Epic Integration

planner_required: true OR human declined skip?
  → Activate Planner with scope restricted to affected_specs
  → Task Contract priority default derives from the change nature encoded in the
    scope block: descriptions matching broken-behavior patterns receive P0 or P1;
    enhancements receive P1 or P2 (the Planner consults the description and
    affected_specs change_summary fields).
```

UI Agent evaluation (improve mode, full pipeline):

```
All Task Contracts are internal (no structural spec section change)?
  → Record UI spec as "N/A — improve with no visual impact" — proceed to Developer

Any Task Contract changes §2 States, §3 Transitions, §7 Components, or §10?
  → Activate UI Agent with scope restricted to affected feature/component specs
```

#### Regression-test discipline (full pipeline only)

The Developer reads `execution_policy.regression_test_required`:

```
regression_test_required: true?
  → Write a failing test that reproduces the defect (bug) or asserts the new
    contract (enhancement) BEFORE touching production code.
  → The test MUST fail on the pre-change codebase and pass after the fix.
  → QA verifies the regression test exists, its pre-change failure, and its
    post-change passing status.

regression_test_required: false?
  → No regression test is required. QA verifies the change matches the stated
    outcome and does not introduce regressions in adjacent code paths.
```

#### Spec-impact gate — breaking-change affordance

During the full pipeline, if the Planner identifies that a change affects an existing contract/API while approved specs exist for the domain, the Orchestrator MUST:

1. Notify the human with options:
   - Update specs first (re-run `/u-spec` via fast-track) — recommended
   - Fix in code now — requires a spec-divergence record

2. If the human chooses to fix without updating:
   - Record in the session log: `SPEC-DIVERGENCE-ACCEPTED: TC-XX — <domain> — <description>`
   - The Task Contract notes: "accepted spec divergence — CR pending"
   - After QA approves, the Orchestrator creates or updates `{SPECS_DIR}/spec-divergences.md` with the divergence for future review

If no approved specs exist for the affected area, treat as a normal change and skip the gate.

---

### Post-Task Contract checks

After QA approves a Task Contract with `origin: improve`:

```
spec_change_status = completed?
  → No post-TC spec update needed — specs were updated before implementation
  → Record in log: "TC-XX: spec pre-updated — no post-TC action required"

spec_change_status = divergence_accepted?
  → Record in log: "TC-XX: divergence_accepted — CR pending"
  → Open CR: save {SESSIONS_DIR}/{SESSION}/cr-{id}.yaml
      type: spec_gap
      affected_files: {affected_specs paths}
  → Append entry to {SPECS_DIR}/spec-changelog-notify.yaml (schema: .claude/skills/u-shared-templates/spec-changelog-notify.schema.yaml):
      origin: triage
      summary: "DIVERGENCE: TC-XX improve — spec outdated — CR-{id} pending"
      changed_files: {affected_specs paths}
      dev_impact: reevaluate_task_contracts

spec_change_status = not_required?
  → Record in log: "TC-XX: cosmetic change — spec does not require update"
```

> **Rule:** post-TC log entry is mandatory for every Task Contract with `origin: improve`. The entry is evidence that the evaluation was performed.

---

### Scope block consumption

After the Planner generates `backlog.md`, the Orchestrator records:

```markdown
## [YYYY-MM-DD HH:MM] — Improve scope consumed
improve_scope_status: consumed
backlog_generated: true
```

On session resumption: if `improve_scope_status: consumed` is present in the log, the Orchestrator enters Resume mode (not Improve mode) and skips scope re-processing.
