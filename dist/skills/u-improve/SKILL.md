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
| `SESSIONS_DIR` | Resolved by command |
| `SESSION` | Resolved by command |
| `IMPROVEMENT_TASK` | Resolved by command (inline quoted text) — collected in Step 1 if absent |

---

## Controlled vocabulary

All confirmation prompts emitted by this skill MUST use this vocabulary. Do not accept synonyms (`yes`, `y`, `s`, `sim`) — re-prompt if the human responds with anything else.

| Token | Meaning |
|-------|---------|
| `confirm` | Proceed with the proposed action |
| `skip-spec` | Accept divergence and skip /u-spec; record `divergence_accepted` |
| `skip-planner` | Skip Planner activation and route directly to Developer |
| `keep-planner` | Keep Planner in the pipeline |
| `abort` | Stop the flow; do not persist additional state |

---

## Step 1 — Collect improvement task

If `IMPROVEMENT_TASK` was provided inline with the command, use it directly and proceed to Step 2.

Otherwise emit exactly:

```
Improvement task:
```

Wait for human input. Record as `improvement_task`. Do not ask follow-up questions. Proceed to Step 2 immediately after recording.

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

### Step 3a — Write scope block to session log

Append to `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md`. If the file does not exist, create it with this block as the first entry.

```markdown
## [YYYY-MM-DD HH:MM] — Improve scope

```yaml
improve_scope:
  description: "{improvement_task}"
  type: {spec_change_required | implementation_only}
  spec_change_status: {pending_spec | not_required}
  affected_specs:
    - path: "{path}"
      sections: ["{§N}"]
      change_summary: "{one sentence}"
  estimated_task_contracts: {N}
  planner_required: {true | false}
  planner_skip_reason: "{reason — required only when planner_required: false}"
  execution_policy:
    pipeline: {lean | full}
    regression_test_required: {true | false}
    planner_required: {mirrors above}
```
```

`spec_change_status` initial values:
- `pending_spec` — emitted when `type: spec_change_required` (will be transitioned by Step 3c)
- `not_required` — emitted when `type: implementation_only`

> **Rule:** `pending_spec` is a non-terminal state. /u-dev MUST refuse to start when it sees this status; it indicates the spec pipeline has not yet completed.

### Step 3b — Write handoff envelope (only when type: spec_change_required)

Append to the same session log immediately after the scope block:

```markdown
## [YYYY-MM-DD HH:MM] — Handoff envelope (improve → spec)

```yaml
handoff_envelope:
  id: IMPROVE-{YYYYMMDD-HHMMSS}
  source: u-improve
  invocation_source: u-improve
  improve_session: "{SESSION}"
  improvement_task: "{improvement_task}"
  mode_hint: {fast-track:minor | fast-track:patch | full}
  affected_specs:
    - path: "{path}"
      sections: ["{§N}"]
      change_summary: "{one sentence}"
  estimated_task_contracts: {N}
  execution_policy:
    pipeline: {lean | full}
    regression_test_required: {true | false}
    planner_required: {true | false}
  return_contract:
    write_to: "{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md"
    update_field: spec_change_status
    expected_terminal_states: [completed, failed]
```
```

The envelope MUST conform to `.claude/skills/u-shared-templates/improve-handoff-envelope.schema.yaml`.

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

I will invoke /u-spec now via the handoff envelope above.
Reply with one of: confirm | skip-spec | abort
```

Wait for human response. Accept ONLY tokens from the controlled vocabulary.

| Response | Action |
|----------|--------|
| `confirm` | Invoke `u-spec-orchestrator` directly via the Agent tool, passing the envelope. On agent return, transition `spec_change_status` to `completed` (success) or `failed` (error) and proceed to Step 5. |
| `skip-spec` | Transition `spec_change_status` to `divergence_accepted`. Record reason: "human declined /u-spec at improve handoff". Proceed to Step 5. |
| `abort` | Append log entry: "Improve aborted by human after scope persistence". Stop. |

Do NOT print a shell command for the human to paste. Use the Agent tool directly.

**Agent tool invocation — exact payload when `confirm` is received:**

```yaml
description: "Invoke u-spec-orchestrator with improve handoff"
prompt: |
  INVOCATION_SOURCE: u-improve
  handoff_envelope:
    id: {envelope.id}
    source: u-improve
    invocation_source: u-improve
    improve_session: "{SESSION}"
    improvement_task: "{improvement_task}"
    mode_hint: {fast-track:minor | fast-track:patch | full}
    affected_specs:
      - path: "{path}"
        sections: ["{§N}"]
        change_summary: "{one sentence}"
    estimated_task_contracts: {N}
    return_contract:
      write_to: "{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md"
      update_field: spec_change_status
      expected_terminal_states: [completed, failed]
    execution_policy:
      pipeline: {lean | full}
      regression_test_required: {true | false}
      planner_required: {true | false}
subagent_type: u-spec-orchestrator
```

On agent return: if the agent reports success → set `spec_change_status: completed`. If error → set `spec_change_status: failed`. Proceed to Step 5.

**If `type: implementation_only`:**

`spec_change_status` is already `not_required`. Proceed directly to Step 5.

---

## Step 4 — (reserved)

> Step 4 is intentionally reserved. The scope-write and envelope-write steps that
> previously lived here have been consolidated into Step 3a and 3b to enforce
> write-before-confirm.

---

## Step 5 — Handoff instructions

### If planner_required: false

Emit:

```
planner_skip_eligible: true
estimated_task_contracts: 1

Reply with one of: skip-planner | keep-planner | abort
```

If `skip-planner`:

```
next_command: /u-dev {SESSION}
note: SPECS_DIR and SESSIONS_DIR are read from CLAUDE.md by /u-dev
orchestrator_instruction: skip_planner=true
scope:
  {list of affected_specs}
```

If `keep-planner`:

```
next_command: /u-dev {SESSION}
note: SPECS_DIR and SESSIONS_DIR are read from CLAUDE.md by /u-dev
planner_scope:
  {list of affected_specs}
```

If `abort`: stop.

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
| scope_block_persistence | write-before-confirm — Step 3a runs BEFORE Step 3c human prompt |
| envelope_persistence | Mandatory mirror in session log when type: spec_change_required |
| spec_invocation | agent_tool_direct — never print shell commands for paste |
| confirmation_tokens | confirm \| skip-spec \| skip-planner \| keep-planner \| abort — no synonyms |
| spec_change_status | Always resolved before Step 5; pending_spec is non-terminal |
| execution_policy_derivation | Text-and-specs-based (Step 2.6) — never ask the human to set pipeline or regression_test_required |
| unified_change_scope | Bug fixes, tweaks, and enhancements all flow through this skill — no separate bug channel |
