## Improve Mode Protocol

Activated when the Orchestrator detects an `improve_scope` block in `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md`.

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
  handoff_manifest_id: "<HANDOFF-... — populated by spec-orchestrator return contract>"
```

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

### Lean vs. full pipeline

The Orchestrator reads `planner_required` from the scope block:

```
planner_required: false AND human confirmed skip (recorded in log)?
  → Route directly to Developer
  → Pass affected_specs as execution context
  → Skip Planner, UI Agent (unless visual change requires it), Epic Integration

planner_required: true OR human declined skip?
  → Activate Planner with scope restricted to affected_specs
  → Standard pipeline: Planner → [UI Agent if needed] → Developer → QA
```

UI Agent evaluation (improve mode, regardless of lean/full):

```
All Task Contracts are internal (no structural spec section change)?
  → Record UI spec as "N/A — improve with no visual impact" — proceed to Developer

Any Task Contract changes §2 States, §3 Transitions, §7 Components, or §10?
  → Activate UI Agent with scope restricted to affected feature/component specs
```

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
