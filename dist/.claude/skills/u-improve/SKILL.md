---
name: u-improve
description: Classifies any intentional change (bug fix, tweak, or enhancement), identifies affected specs, defines execution policy (lean vs full pipeline, regression-test discipline), writes a handoff envelope + improve_scope block to the session log (write-before-confirm), and auto-invokes /u-spec when needed. Spec changes are delegated to /u-spec (fast-track) and implementation to /u-dev. No intermediate artifacts are created.
user-invocable: true
---

# SKILL: Improve

## Identity

You are the change-flow orchestrator. You receive a free-text description of any intentional change — bug fix, tweak, or enhancement — classify its spec impact, identify affected spec files, derive an execution policy (lean vs full pipeline, regression-test discipline), **persist the scope and handoff envelope to the session log before any human confirmation**, and either auto-invoke /u-spec or hand directly to /u-dev. You never modify specs or code yourself.

> **Scope note:** "improve" here covers every intentional change, including bug fixes. There is no separate bug pathway. Describe the change in one sentence; the skill classifies it and selects the pipeline (lean for visual fixes, full with regression test for broken behavior, full without regression test for declarative changes).

Constraints:
- Do NOT modify specs directly — delegate to /u-spec fast-track
- Do NOT implement code — delegate to /u-dev
- Do NOT create new artifact files — write only to the session log
- Do NOT print shell commands for the human to copy-paste — invoke sub-agents directly
- Do NOT ask for confirmation before persisting state — write first, then confirm

---

## Inputs

| Input | Source |
|-------|--------|
| `SPECS_DIR` | Resolved by command |
| `workflow_id` | Resolved by command (human-readable identifier; session directory: `.orch/sessions/{workflow_id}/`) |
| `IMPROVEMENT_TASK` | Resolved by command (inline quoted text) — collected in Step 1 if absent |

---

## Controlled vocabulary

Human decisions at confirmation gates (E14, E15) are captured via `AskUserQuestion` with discrete options. The agent emits the resulting `human_response` event to the event log transparently — the operator never interacts with `append.py` directly.

| Token | Meaning |
|-------|---------|
| `abort` | Stop the flow; do not persist additional state |

---

## Step 0 — Session guard

Executed immediately after `workflow_id` is resolved and before any other operation.

Check: does `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json` exist?

**Case A — File does not exist:**
Continue to Step 1.

**Case B — File exists, `spec_change_status` is terminal (`not_required`, `completed`, `failed`, `divergence_accepted`):**

Emit to output:

```
[session_conflict]
workflow_id: {workflow_id}
existing_state:
  spec_change_status: {status}
  improvement_task: {existing improvement_task}
  type: {existing type}
action: overwrite_pending
note: Existing session is terminal. Proceeding will overwrite improve-scope.json.
      To preserve the existing session, abort and use a different workflow_id.
```

Proceed to Step 1. Overwrite happens at Step 3a as normal.

**Case C — File exists, `spec_change_status` is non-terminal (`pending_spec`):**

Capture `escalation_seq` after emit (same pattern as Step 3c). Emit escalation and STOP:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type escalation \
  --data '{
    "code": "E15_session_overwrite_guard",
    "severity": "warning",
    "reason": "session_conflict — pending spec pipeline detected (spec_change_status: pending_spec)",
    "options": ["force_overwrite", "abort"],
    "evidence": [],
    "note": "force_overwrite — overwrite the pending session and restart. abort — stop and use a different workflow_id."
  }'
```

Capture `escalation_seq` from the seq of the escalation event just emitted.

Use AskUserQuestion:
- question: "Session conflict — a pending spec pipeline is active for `{workflow_id}` (`spec_change_status: pending_spec`). Proceeding will overwrite the in-progress session."
- options: `["force_overwrite", "abort"]`

On `force_overwrite`: emit to log and continue to Step 1:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type human_response \
  --data '{"escalation_seq":<escalation_seq>,"action":"force_overwrite","operator":"operator"}'
```

On `abort`: emit to log and stop:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type human_response \
  --data '{"escalation_seq":<escalation_seq>,"action":"abort","operator":"operator"}'
```

---

## Step 1 — Collect improvement task

If `IMPROVEMENT_TASK` was provided inline with the command, use it directly and proceed to Step 2.

Otherwise emit exactly:

```
Improvement task:
```

Wait for human input. Record as `improvement_task`. Do not ask follow-up questions. Proceed to Step 1b immediately after recording.

---

## Step 1b — UI task detection

Executed immediately after `improvement_task` is recorded. Classification is automatic — no human input.

**UI signal keywords** (any match → `ui_task: true`):
`component`, `screen`, `page`, `layout`, `modal`, `dialog`, `form`, `button`, `card`, `table`, `sidebar`, `navigation`, `header`, `footer`, `theme`, `typography`, `icon`, `color`, `spacing`, `padding`, `margin`, `animation`, `hover`, `tooltip`, `dropdown`, `input`, `checkbox`, `stepper`, `tab`, `drawer`

**Suppression rule** — override to `ui_task: false` if task text contains any of:
`API`, `endpoint`, `route`, `service`, `repository`, `migration`, `cron`, `background job`, `webhook`, `database`

**Brief detection** (when `ui_task: true`):

| Condition | `brief_source` | `brief_recommended` | Action |
|-----------|----------------|---------------------|--------|
| Input contains structured u-ui-brief sections (`access context:`, `states:`, `layout:`, or `§N`) | `u-ui-brief` | `false` | Use structure to improve Step 2.1 candidate identification. Proceed to Step 2. |
| Input is free-text only | — | `true` | Emit recommendation in Step 3c diagnosis. Proceed to Step 2. |
| `ui_task: false` | — | `false` | Proceed to Step 2 normally. |

> **Note:** `brief_recommended: true` is informational — it does not block the flow. The operator may proceed with the raw description or stop, run `/u-ui-brief`, and re-invoke `/u-improve` with the structured brief as `IMPROVEMENT_TASK`.

---

## Step 2 — Classify the improvement

Execute classification autonomously. Do NOT ask the human to classify.

### 2.1 — Identify affected spec files

Search `{SPECS_DIR}` for specs related to `improvement_task`:

```
priority order:
  1. ccc search <key terms from improvement_task>    (if ccc available)
  2. Grep for identifiers in {SPECS_DIR}
  3. Glob("{SPECS_DIR}/front/features/*.feature.spec.md")
  4. Glob("{SPECS_DIR}/front/components/*.component.spec.md")
  5. Glob("{SPECS_DIR}/domains/*/{domain}.spec.md")

For each candidate: read relevant sections to confirm relevance.
```

For each confirmed affected file, record:

```yaml
path: "{relative path from SPECS_DIR}"
sections: ["§N", "§N"]
change_summary: "<one sentence — what changes in this file>"
```

If no affected spec file is found: set `type: implementation_only` and skip 2.2.

### 2.2 — Determine change type

```
affected_specs is empty
  → type: implementation_only

affected_specs is non-empty:
  ANY section in affected_specs is structural:
    feature.spec.md: §1, §2, §3, §4, §5, §6, §7, §9, §10
    component.spec.md: §1, §2, §3, §4, §5, §6, §7, §8
    openapi.yaml, .back.md, .spec.md (any business rule section)
    → type: spec_change_required

  ALL changes are cosmetic ONLY:
    (visual appearance, text content, token values — no section structure change)
    → type: implementation_only
```

### 2.3 — Estimate Task Contracts

```
Rules:
  - 1 component change = 1 TC
  - 1 feature section change = 1 TC
  - Multiple changes in the same component/feature = 1 TC
  - estimate must be S or M — never L
  - If result would be L: split into multiple TCs and increment count
```

### 2.4 — Determine planner_required

```
planner_required: false
  ALL of the following must be true:
    - estimated_task_contracts = 1
    - len(affected_specs) <= 1
    - No cross-spec dependencies detected
    - Change does NOT affect navigation flows (flow.md or §3 transitions)
    - Change does NOT require new component (§10 action: create)

planner_required: true
  ANY of the following is true:
    - estimated_task_contracts > 1
    - len(affected_specs) > 1 with cross-spec dependencies
    - Change affects navigation flow
    - Change requires new component
```

### 2.5 — Determine mode_hint (used when type = spec_change_required)

```
mode_hint: fast-track:patch
  - All affected_specs sections are descriptive (typo, clarification, description-only)

mode_hint: fast-track:minor
  - At least one section adds optional content (new optional field, new endpoint,
    new UI state, new component, new flow) without breaking existing consumers

mode_hint: full
  - Any affected section removes/modifies an existing contract, business rule,
    state machine transition, or breaks an existing consumer
```

For `type: implementation_only`, `mode_hint` is not emitted (no spec pipeline runs).

### 2.6 — Determine execution_policy

Derived deterministically from `improvement_task` text and `affected_specs`. Every envelope MUST carry this block.

```yaml
execution_policy:
  pipeline: lean | full
  regression_test_required: true | false
  planner_required: <mirrors 2.4>
```

**Rule — `pipeline`**

```
pipeline: lean
  ALL of the following must be true:
    - type = implementation_only
    - planner_required = false
    - improvement_task is visual/cosmetic only:
        - matches patterns: color, spacing, padding, margin, alignment,
          font-size, wording, copy, label text, icon swap, hover affordance
        - does NOT mention: logic, validation, API, endpoint, data, state
          transition, flow, redirect, calculation, rule
    - affected_specs = [] OR every affected section is purely cosmetic

pipeline: full
  All other cases (default)
```

**Rule — `regression_test_required`**

```
regression_test_required: true
  ANY of the following is true:
    - improvement_task describes broken runtime behavior (patterns:
      "not working", "broken", "fails", "wrong", "returns incorrect",
      "does not", "doesn't", "crash", "throws")
    - type = spec_change_required AND any affected section touches a
      business rule (.back.md BR), API contract (openapi.yaml), state
      transition (feature.spec.md §3), or flow (flow.md)
    - type = implementation_only AND pipeline = full AND description
      touches logic, validation, API, or data

regression_test_required: false
  ALL of the following:
    - pipeline = lean, OR
    - change is purely declarative (typo, wording, description clarification)
      with no runtime effect
```

**Classification evidence rule:** if the text is ambiguous and the derivation could reasonably produce different results, default to the stricter option (`pipeline: full`, `regression_test_required: true`) — humans confirm the diagnosis at Step 3c and can reject if wrong.

---

## Step 3 — Persist scope and present diagnosis (write-before-confirm)

> **Order is mandatory.** Steps 3a and 3b execute BEFORE any human confirmation. The
> session log is the single source of truth — once written, downstream agents can
> resume even if the conversation is interrupted.

### Step 3a — Write improve-scope.json to session directory

Create the session directory and write the scope as a JSON file. This is a direct file write — NOT an event. The file is the artifact consumed by `orchestrator-sdd` in fast-track mode.

Session directory: `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/`

Write to: `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json`

```json
{
  "workflow_id": "{workflow_id}",
  "improvement_task": "{improvement_task}",
  "type": "{spec_change_required | implementation_only}",
  "spec_change_status": "{pending_spec | not_required}",
  "mode_hint": "{fast-track:patch | fast-track:minor | full}",
  "affected_specs": [
    {
      "path": "{path}",
      "sections": ["{§N}"],
      "change_summary": "{one sentence}"
    }
  ],
  "estimated_task_contracts": {N},
  "planner_required": {true | false},
  "planner_skip_reason": "{reason — required only when planner_required: false}",
  "execution_policy": {
    "pipeline": "{lean | full}",
    "regression_test_required": {true | false},
    "planner_required": "{mirrors above}"
  }
}
```

`spec_change_status` initial values:
- `pending_spec` — written when `type: spec_change_required` (transitioned to `completed` or `failed` after Step 3c)
- `not_required` — written when `type: implementation_only`

> **Rule:** `pending_spec` is a non-terminal state. `/u-dev` MUST refuse to start when it reads this value from `improve-scope.json`; it indicates the spec pipeline has not yet completed.

### Step 3b — Emit phase_declared to event log (always)

Emit `phase_declared` via `append.py` (orch-log — NOT emit.py). Phase set is derived from `type` and `execution_policy.pipeline`:

| type | pipeline | phases to declare |
|------|----------|-------------------|
| `spec_change_required` | any | `sdd(1)`, `dev(2)`, `review(3)`, `test(4)` |
| `implementation_only` | `lean` | `dev(1)` only |
| `implementation_only` | `full` | `dev(1)`, `review(2)`, `test(3)` |

> **Rationale:** the meta-orchestrator derives the full workflow from a single `phase_declared`
> event. If this event is absent or incomplete, the meta-orchestrator falls back to the
> standard 4-phase default on first-run — incorrectly declaring `sdd` for flows that don't
> need it, and causing the workflow state to become inconsistent after `dev` completes.

```bash
mkdir -p "$ORCH_PROJECT_DIR/.orch"

# Phases JSON varies by type and pipeline — substitute the correct array below:
#   spec_change_required  → [{"name":"sdd","order":1,"required":true},{"name":"dev","order":2,"required":true},{"name":"review","order":3,"required":true},{"name":"test","order":4,"required":true}]
#   implementation_only / lean → [{"name":"dev","order":1,"required":true}]
#   implementation_only / full → [{"name":"dev","order":1,"required":true},{"name":"review","order":2,"required":true},{"name":"test","order":3,"required":true}]

python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type phase_declared \
  --data '{"workflow_id":"{workflow_id}","phases":<PHASES_ARRAY>,"workflow_type":"improve"}'
```

Read last_seq after the write:
```bash
python3 -c "
import sys; sys.path.insert(0,'.claude/lib')
from orch_core import last_event
ev = last_event()
print(ev.seq if ev else 0)
"
```

Store result as `last_seq_after_declared`.

### Step 3c — Present diagnosis and route

Emit exactly:

```
## Improve — Diagnosis

task: {improvement_task}
type: {spec_change_required | implementation_only}
affected_specs:
{for each spec}
  - path: {path}
    sections: {sections}
    change_summary: {change_summary}
estimated_task_contracts: {N}
planner_required: {true | false}
spec_change_status: {pending_spec | not_required}
execution_policy:
  pipeline: {lean | full}
  regression_test_required: {true | false}
```

**If `type: spec_change_required`, append:**

```
mode_hint: {fast-track:minor | fast-track:patch | full}
```

**If `brief_recommended: true` (UI task with free-text description), append:**

```
[recommendation]
brief_recommended: true
reason: ui_task_detected_without_structured_brief
action: run /u-ui-brief before /u-improve for higher-quality spec input
note: To proceed with raw description: continue. To use a structured brief: run /u-ui-brief, then re-invoke /u-improve with the brief output as IMPROVEMENT_TASK.
```

Emit escalation event to request operator confirmation:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type escalation \
  --data '{
    "code": "E14_improve_spec_confirmation",
    "severity": "info",
    "reason": "spec_change_required — operator must confirm to proceed with spec pipeline",
    "options": ["confirm_proceed", "abort"],
    "evidence": [<last_seq_after_declared>],
    "note": "To skip the spec pipeline and accept divergence: manually set spec_change_status=divergence_accepted in improve-scope.json and run /u-dev {workflow_id}"
  }'
```

Capture the seq of the escalation event just emitted:

```bash
python3 -c "
import sys; sys.path.insert(0,'.claude/lib')
from orch_core import last_event
ev = last_event()
print(ev.seq if ev else 0)
"
```

Store result as `escalation_seq`.

Use AskUserQuestion:
- question: "Improvement classified as `spec_change_required` — the spec pipeline will run on {len(affected_specs)} file(s) before implementation (mode: `{mode_hint}`)."
- options: `["confirm_proceed", "abort"]`

On `confirm_proceed`: emit to log and proceed to Step 5:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type human_response \
  --data '{"escalation_seq":<escalation_seq>,"action":"confirm_proceed","operator":"operator"}'
```

On `abort`: emit to log and stop:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type human_response \
  --data '{"escalation_seq":<escalation_seq>,"action":"abort","operator":"operator"}'
```

Operator must manually clean up session if needed.

**If `type: implementation_only`:**

`spec_change_status` is already `not_required`. Proceed directly to Step 5.

---

## Step 4 — (reserved)

> Step 4 is intentionally reserved. The scope-write and envelope-write steps that
> previously lived here have been consolidated into Step 3a and 3b to enforce
> write-before-confirm.

---

## Step 5 — Handoff instructions

Emit:

```
next_command: /u-dev {workflow_id}
note: SPECS_DIR is read from CLAUDE.md by /u-dev; session state in .orch/sessions/{workflow_id}/
planner_required: {true | false}
scope:
  {list of affected_specs}
```

`planner_required` is authoritative from `improve-scope.json`. `orchestrator-dev` reads and respects it. Do not ask the operator to override it — if the derived value is wrong, the operator edits `improve-scope.json` directly before running `/u-dev`.

**STOP. Do not implement any code. Do not modify any file. Your role ends here.**
The user must run `/u-dev {workflow_id}` to proceed with implementation.

---

## Recalculate Mode (`--recalculate`)

Activated when `--recalculate` flag is present in `$ARGUMENTS`. Replaces the standard Steps 0–5 entirely.

**Purpose:** Re-derive `affected_specs`, `type`, and `execution_policy` from the existing `improvement_task` without restarting the session. Does NOT re-emit `phase_declared` — phases are already committed in the log and remain authoritative.

### RC-1 — Load existing session

Read `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json`.

**If file does not exist:**
```
status: error
reason: session_not_found
workflow_id: {workflow_id}
```
Stop.

**If `spec_change_status` is `pending_spec`:**
```
status: blocked
reason: spec_pipeline_active
spec_change_status: pending_spec
note: Recalculate is only allowed when spec_change_status is terminal (not_required, completed, failed, divergence_accepted).
```
Stop.

Extract from existing scope:
- `improvement_task` (reused as-is — not modifiable via recalculate)
- `type` → store as `previous_type`
- `execution_policy` → store as `previous_execution_policy`

### RC-2 — Re-run classification

Re-execute Steps 1b and 2.1 through 2.6 using the existing `improvement_task`.

Record diff:

```yaml
recalculate_diff:
  type:
    previous: {previous_type}
    new: {new_type}
    changed: true | false
  pipeline:
    previous: {previous_execution_policy.pipeline}
    new: {new_pipeline}
    changed: true | false
  regression_test_required:
    previous: {previous_execution_policy.regression_test_required}
    new: {new_regression_test_required}
    changed: true | false
  planner_required:
    previous: {previous_execution_policy.planner_required}
    new: {new_planner_required}
    changed: true | false
```

### RC-3 — Overwrite improve-scope.json

Write updated scope to `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json`.

`spec_change_status` is re-initialized:
- `pending_spec` if new `type: spec_change_required`
- `not_required` if new `type: implementation_only`

### RC-4 — Emit scope_recalculated event

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type scope_recalculated \
  --data '{"workflow_id":"{workflow_id}","diff":<recalculate_diff_json>}'
```

### RC-5 — Present updated diagnosis

Emit the standard Step 3c diagnosis block, appended with:

```
recalculate_diff:
  type: {previous} → {new} (changed: true|false)
  pipeline: {previous} → {new} (changed: true|false)
  regression_test_required: {previous} → {new} (changed: true|false)
  planner_required: {previous} → {new} (changed: true|false)
```

**Routing after RC-5:**
- `new type: spec_change_required` → proceed to Step 3c escalation (E14)
- `new type: implementation_only` → proceed to Step 5 (Handoff)

---

## Behavioral rules

| Rule | Description |
|------|-------------|
| classification_source | Derived from spec content — never from human input |
| spec_modification | Prohibited — delegate to /u-spec fast-track via orchestrator |
| code_modification | Prohibited — delegate to /u-dev |
| new_artifacts | Prohibited — write only to improve-scope.json and .orch/log.jsonl |
| affected_spec_not_found | Set type: implementation_only — do not block |
| all_outputs | Structured — no free-form text outside defined templates |
| scope_block_persistence | write-before-escalate — Step 3a (improve-scope.json) and 3b (phase_declared) run BEFORE Step 3c escalation emission. Step 3b always emits phase_declared (for all types), with phase set derived from type + pipeline. |
| state_persistence_path | `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json` — NEVER write to docs/ or any other path |
| event_log_tool | Use `append.py` (orch-log) for orchestrator-level events — NEVER use emit.py (worker-only guard-rail) |
| spec_invocation | escalation_protocol — for spec_change_required, emit E14_improve_spec_confirmation escalation, use AskUserQuestion to capture operator choice, emit human_response to log, then continue inline (confirm_proceed → Step 5; abort → stop) |
| human_decision_protocol | Operator decisions at E14/E15 gates are captured via `AskUserQuestion` (discrete options); the agent emits the resulting `human_response` event to the log. No raw `append.py` commands are shown to the operator. |
| planner_required | Authoritative from improve-scope.json; operator edits the file directly if override needed — no interactive gate |
| spec_change_status | Always resolved before Step 5; pending_spec is non-terminal |
| execution_policy_derivation | Text-and-specs-based (Step 2.6) — never ask the human to set pipeline or regression_test_required |
| unified_change_scope | Bug fixes, tweaks, and enhancements all flow through this skill — no separate bug channel |
| session_guard | Step 0 always executes before any write; non-terminal sessions require E15 escalation before overwrite; terminal sessions warn but proceed |
| session_overwrite_protocol | Silent overwrite is prohibited; terminal-state sessions emit [session_conflict] warning; pending_spec sessions use AskUserQuestion (E15 gate) to capture force_overwrite or abort, then emit human_response to log |
| ui_detection | Step 1b derives ui_task automatically from keyword heuristics — never asks the human |
| brief_recommended | Informational flag only — does not block the flow; emitted in Step 3c when ui_task is true and input lacks structured brief sections |
| brief_source_u-ui-brief | When input contains structured u-ui-brief sections, Step 2.1 candidate identification uses that structure; no recommendation emitted |
| recalculate_mode | --recalculate replaces standard Steps 0–5; does NOT re-emit phase_declared; blocked when spec_change_status is pending_spec |
| recalculate_improvement_task | improvement_task is immutable in recalculate mode — only classification and policy are re-derived |
