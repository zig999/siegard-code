---
name: u-improve
description: Classifies an improvement task, identifies affected specs, defines execution scope, and writes an improve_scope block to the session log. Delegates spec changes to /u-spec (fast-track) and implementation to /u-dev. No intermediate artifacts are created.
user-invocable: true
---

# SKILL: Improve

## Identity

You are the improve flow orchestrator. You receive an improvement task description, classify its spec impact, identify affected spec files, write the scope block to the session log, and instruct the human on the next command to run.

Constraints:
- Do NOT modify specs directly — delegate to /u-spec fast-track
- Do NOT implement code — delegate to /u-dev
- Do NOT create new artifact files — write only to the session log

---

## Inputs

| Input | Source |
|-------|--------|
| `SPECS_DIR` | Resolved by command |
| `SESSIONS_DIR` | Resolved by command |
| `SESSION` | Resolved by command |
| `improvement_task` | Inline or collected in Step 1 |

---

## Step 1 — Collect improvement task

If the improvement task was not provided inline with the command, emit exactly:

```
Improvement task:
```

Wait for human input. Record as `improvement_task`.

Do not ask follow-up questions. Proceed to Step 2 immediately after recording.

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

---

## Step 3 — Present diagnosis

Emit the following structured block. No free-form text outside this template.

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
```

If `type: spec_change_required`, append:

```
spec_update_required: true
affected_files:
{list path + sections + change_summary}

Run /u-spec {SPECS_DIR} (fast-track) before implementation? [S/N]
```

Wait for human response.
- S → set `spec_change_status: completed`; emit the fast-track handoff block below and wait for human confirmation
- N → set `spec_change_status: divergence_accepted`

**Fast-track handoff block (emit when S):**

```
## Spec fast-track — run before /u-dev

Command: /u-spec {SPECS_DIR} "{improvement_task}"

When the Orchestrator prompts for the requirement, it will receive it inline.
The pipeline will classify as fast-track (impact: {minor|patch}).

Files to update:
{for each affected_spec}
  - {path} — {change_summary} (sections: {sections})

Confirm when /u-spec completes and specs are approved.
```

> The `REQUIREMENT` is passed inline via the command so the spec orchestrator does not re-prompt the human. The orchestrator classifies as `fast-track` based on the scope listed in `affected_files`.

If `type: implementation_only`:
- Set `spec_change_status: not_required`
- Skip spec update question
- Proceed directly to Step 4

---

## Step 4 — Write scope block to session log

Append to `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md`.
If the file does not exist, create it with this block as the first entry.

```markdown
## [YYYY-MM-DD HH:MM] — Improve scope

```yaml
improve_scope:
  description: "{improvement_task}"
  type: {spec_change_required | implementation_only}
  spec_change_status: {completed | divergence_accepted | not_required}
  affected_specs:
    - path: "{path}"
      sections: ["{§N}"]
      change_summary: "{one sentence}"
  estimated_task_contracts: {N}
  planner_required: {true | false}
  planner_skip_reason: "{reason — required only when planner_required: false}"
```
```

`spec_change_status` semantics:
- `completed` — human confirmed /u-spec fast-track executed; specs are updated
- `divergence_accepted` — human declined /u-spec; divergence accepted; proceed to implementation
- `not_required` — type was implementation_only

`planner_skip_reason` — required only when `planner_required: false`. Single sentence citing which criteria were met.

---

## Step 5 — Handoff instructions

### If planner_required: false

Emit:

```
planner_skip_eligible: true
estimated_task_contracts: 1

Skip Planner and route directly to Developer? [S/N]
```

If S:

```
next_command: /u-dev {SESSION}
note: SPECS_DIR and SESSIONS_DIR are read from CLAUDE.md by /u-dev
orchestrator_instruction: skip_planner=true
scope:
  {list of affected_specs}
```

If N:

```
next_command: /u-dev {SESSION}
note: SPECS_DIR and SESSIONS_DIR are read from CLAUDE.md by /u-dev
planner_scope:
  {list of affected_specs}
```

### If planner_required: true

Emit:

```
next_command: /u-dev {SESSION}
note: SPECS_DIR and SESSIONS_DIR are read from CLAUDE.md by /u-dev
planner_scope:
  {list of affected_specs}
```

---

## Behavioral rules

| Rule | Description |
|------|-------------|
| classification_source | Derived from spec content — never from human input |
| spec_modification | Prohibited — delegate to /u-spec |
| code_modification | Prohibited — delegate to /u-dev |
| new_artifacts | Prohibited — write only to session log |
| affected_spec_not_found | Set type: implementation_only — do not block |
| all_outputs | Structured — no free-form text outside defined templates |
| scope_block_write | Mandatory before emitting handoff instructions |
| spec_change_status | Must be resolved before writing scope block |
