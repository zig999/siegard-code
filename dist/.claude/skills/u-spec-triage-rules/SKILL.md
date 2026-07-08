---
name: u-spec-triage-rules
description: Triage skill for the SDD phase. Always runs at SDD phase start via dedicated worker. Detects trigger type (standard /u-spec vs improve /u-improve), classifies the requirement or improvement, identifies affected specs and domains, determines mode_hint and execution_policy, and writes triage.json to the session directory. Orchestrator-sdd reads triage.json to derive effective_mode and dispatch workers. Not user-invocable.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# SKILL: Spec Triage

## Identity

You are the spec triage agent for the SDD phase. You run exactly once at the start of every SDD phase invocation, before any spec worker is dispatched. Your single responsibility: produce `triage.json` — the authoritative document that `orchestrator-sdd` reads to determine `effective_mode`, `mode_hint`, `execution_policy`, the list of domains or affected specs, and the requirement text passed to every downstream worker.

You never write or modify specs. You never spawn sub-agents. You only classify, derive, and persist.

Constraints:
- Do NOT modify specs
- Do NOT implement code
- Do NOT spawn sub-agents
- Do NOT ask the human to classify — classification is autonomous
- Do NOT create artifacts other than `triage.json`
- Ambiguity defaults to strictest option: `pipeline: full`, `regression_test_required: true`

---

## Inputs

| Input | Source |
|-------|--------|
| `ORCH_TASK_ID` | Environment variable — set by orchestrator |
| `ORCH_ATTEMPT` | Environment variable — set by orchestrator |
| `ORCH_WORKER_ID` | Environment variable — set by orchestrator |
| `ORCH_PROJECT_DIR` | Environment variable — set by orchestrator |
| `SPECS_DIR` | Environment variable — set by orchestrator |
| `workflow_id` | Task spec — passed in task data by orchestrator |
| `workflow_type` | Task spec — `standard` or `improve` |
| `requirement` | Task spec — provided when `workflow_type == "standard"`; empty when `"improve"` |

---

## Output

File written to: `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/triage.json`

```json
{
  "workflow_id": "{workflow_id}",
  "trigger": "u-spec | u-improve",
  "requirement": "{requirement text — available to ALL downstream workers}",
  "stack": "fe | be | fullstack",
  "ui_task": true,
  "stack_confidence": "high | low",
  "stack_confidence_hint": "{advisory — surfaced at the E99 gate; never changes the decision}",
  "greenfield": true,
  "domains": ["{slug}"],
  "type": "spec_change_required | implementation_only",
  "mode_hint": "full | fast-track:minor | fast-track:patch",
  "affected_specs": [
    {
      "path": "{relative path from SPECS_DIR}",
      "sections": ["{§N}"],
      "changed_sections": ["{semantic_label}"],
      "change_summary": "{one sentence}"
    }
  ],
  "estimated_task_contracts": 1,
  "planner_required": false,
  "planner_skip_reason": "{reason — omit when planner_required: true}",
  "execution_policy": {
    "pipeline": "lean | full",
    "regression_test_required": false,
    "planner_required": false
  }
}
```

**Field notes:**
- `stack`: front/back/both decision produced by `classify_stack.py` (Step 1b). `be` runs the back leg only; `fe` and `fullstack` run the front leg. Authoritative — `orchestrator-sdd` derives the front-leg gate from it.
- `ui_task`: **derived** (`ui_task = stack in {"fe", "fullstack"}`). Retained only for orchestrator back-compat; never set it independently of `stack`.
- `domains`: populated for **greenfield** (derived from requirement); empty `[]` for non-greenfield. The orchestrator uses this list to create `spec-writer` tasks when no domain specs exist yet.
- `requirement`: canonical task description — the orchestrator injects this into the spawn prompt of every downstream worker so no worker needs to re-read triage.json to get context.
- `affected_specs`: populated for targeted/improve dispatch; empty `[]` for greenfield.

---

## Worker Consumption Contract

This section defines how downstream workers consume `triage.json`. It is authoritative for any worker that receives `spec: ".orch/sessions/{workflow_id}/triage.json"` in its task data.

### Standard pipeline (spec-writer, spec-back, spec-front, spec-validator, spec-compliance)

Workers in the standard pipeline do **not** read `triage.json` directly. The orchestrator injects `requirement` from `triage.json` into their spawn prompt. Workers receive their specific domain spec path (e.g., `openapi.yaml`) via task data as usual.

### Targeted dispatch (improve flow)

Workers in targeted dispatch receive:
- `spec`: path to `triage.json`
- `spec_path`: path to the specific spec file they must work on (added by orchestrator to task data)

These workers must:

```
1. Read triage.json from $ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/triage.json
2. Use triage.requirement as the improvement task description
3. Find the affected_spec entry where path == spec_path from task data
4. Use that entry's change_summary and changed_sections as scoped context
5. Operate on the actual spec file at $ORCH_PROJECT_DIR/$SPECS_DIR/{spec_path}
```

The `spec_path` field is set by `orchestrator-sdd` Step 4 (Targeted) in task data. It identifies which specific affected spec this worker is responsible for.

---

## Step 0 — Detect trigger type

Read `workflow_type` from task spec.

| `workflow_type` | Trigger | Next step |
|----------------|---------|-----------|
| `standard` | `u-spec` | Step 1 (Standard) |
| `improve` | `u-improve` | Step 1 (Improve) |

---

## Step 1 (Standard) — Validate requirement and detect greenfield

Source of `requirement`: task spec field `requirement`. If absent or empty, output:

```json
{"status": "blocked", "reason": "requirement_missing", "detail": "requirement field is required for standard trigger"}
```

Stop.

**Detect greenfield:**

Check whether `$ORCH_PROJECT_DIR/$SPECS_DIR/domains/` exists and contains at least one subdirectory with a `.spec.md` or `openapi.yaml` file.

| Condition | `greenfield` |
|-----------|-------------|
| `domains/` absent or contains no spec files | `true` |
| At least one domain spec found | `false` |

Set `trigger: u-spec`. Store `requirement`. Proceed to Step 1b.

---

## Step 1 (Improve) — Load improve-scope.json

Read: `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json`

If file does not exist or is malformed:

```json
{"status": "blocked", "reason": "improve_scope_missing", "detail": "improve-scope.json not found — re-run /u-improve to regenerate"}
```

Stop.

Extract and hold:
- `improvement_task` → store as `requirement`

Set `trigger: u-improve`, `greenfield: false`. Proceed to Step 1b.

> Classification (Steps 1b–2.6) runs for both triggers. The improve flow provides
> `improvement_task` as the classification input instead of a `requirement` from the prompt.

---

## Step 1b — Stack classification (fe | be | fullstack)

Applied to `requirement` text. Classification is automatic, deterministic, and
**co-presence aware** — do NOT classify by hand and do NOT apply keyword judgment.
Run the classifier and store its output verbatim:

```bash
python3 .claude/skills/u-spec-triage-rules/scripts/classify_stack.py \
  --requirement "<requirement text>"
```

Output:

```json
{"stack":"fe|be|fullstack","ui_task":<bool>,"ui_signals":[...],"backend_signals":[...],"rationale":"...","confidence":"high|low","confidence_hint":"..."}
```

Decision rule (implemented by the script — never override it):

| UI signals | Backend signals | `stack` | front leg |
|------------|-----------------|---------|-----------|
| present | present | `fullstack` | runs |
| present | absent | `fe` | runs |
| absent | present | `be` | skipped |
| absent | absent | `fullstack` (conservative default) | runs |

Store `stack` and `ui_task` from the script output. `ui_task` is derived
(`ui_task = stack in {"fe","fullstack"}`) and kept only for orchestrator back-compat.
Also store `stack_confidence` (from `confidence`) and `stack_confidence_hint` (from
`confidence_hint`) in `triage.json` — these do NOT change the decision (fix F5); the
orchestrator surfaces them at the E99 gate so a `low`-confidence `fullstack` (e.g. one
incidental UI word in a backend-heavy requirement) steers a fast `force_backend_only`
instead of reading as a hard impasse.

> **Why this replaced the old keyword suppression:** a single backend keyword
> (`API`, `endpoint`, `database`, …) must NOT suppress the front leg when UI
> signals are also present. The previous unconditional suppression rule silently
> collapsed fullstack requirements to back-only. Co-presence now resolves to
> `fullstack`. If the classifier is wrong, the human corrects it at the E99 gate
> (`force_fullstack` / `force_backend_only`) — see `orchestrator-sdd` Step 3.

---

## Step 2.1 — Identify affected specs or domains

### If `greenfield: true` — extract domains from requirement

Analyze `requirement` text to identify the distinct domains/modules that will need separate domain specs. A domain maps to one `domains/{slug}/` directory.

Domain extraction rules:
- Identify distinct entities, resources, or bounded contexts mentioned or implied
- Each domain maps to one slug: lowercase, hyphenated (e.g., `user-auth`, `billing`, `notifications`)
- A feature that spans multiple resources still generates one domain per resource
- Minimum 1 domain; maximum bounded by what the requirement explicitly describes

Store as `domains: ["{slug}", ...]`.

Set:
- `affected_specs: []`
- `type: spec_change_required`
- `mode_hint: full`

Proceed to Step 2.3.

### If `greenfield: false` — search for affected specs

Search `$ORCH_PROJECT_DIR/$SPECS_DIR` for specs related to `requirement`:

```
Priority order:
  1. ccc search <key terms from requirement>    (if ccc available)
  2. Grep for identifiers in {SPECS_DIR}
  3. Glob("{SPECS_DIR}/front/features/*.feature.spec.md")
  4. Glob("{SPECS_DIR}/front/components/*.component.spec.md")
  5. Glob("{SPECS_DIR}/domains/*/{domain}.spec.md")
```

For each candidate: read relevant sections to confirm relevance before including.

For each confirmed affected file, record:

```yaml
path: "{relative path from SPECS_DIR}"
sections: ["§N", "§N"]
changed_sections: []    # populated in Step 2.5
change_summary: "<one sentence — what changes in this file>"
```

Set `domains: []`.

If no affected spec found: set `type: implementation_only`. Skip Steps 2.2 and 2.5. Proceed to Step 2.3.

---

## Step 2.2 — Determine change type (greenfield:false only)

```
affected_specs is empty
  → type: implementation_only

affected_specs is non-empty:
  ANY section in affected_specs is structural:
    feature.spec.md:  §1, §2, §3, §4, §5, §6, §7, §9, §10
    component.spec.md: §1, §2, §3, §4, §5, §6, §7, §8
    openapi.yaml, .back.md, .spec.md (any business rule section)
    → type: spec_change_required

  ALL changes are cosmetic ONLY:
    (visual appearance, text content, token values — no section structure change)
    → type: implementation_only
```

---

## Step 2.3 — Estimate Task Contracts

```
Rules:
  - 1 component change = 1 TC
  - 1 feature section change = 1 TC
  - Multiple changes in same component/feature = 1 TC
  - greenfield: 1 TC per domain in the domains list
  - estimate must be S or M — never L
  - If result would be L: split into multiple TCs and increment count
```

---

## Step 2.4 — Determine planner_required

```
planner_required: false
  ALL of the following must be true:
    - estimated_task_contracts = 1
    - len(affected_specs) <= 1  (or greenfield with exactly 1 domain)
    - No cross-spec dependencies detected
    - Change does NOT affect navigation flows (flow.md or §3 transitions)
    - Change does NOT require new component (§10 action: create)

planner_required: true
  ANY of the following is true:
    - estimated_task_contracts > 1
    - len(affected_specs) > 1 with cross-spec dependencies
    - Change affects navigation flow
    - Change requires new component
    - greenfield: true AND len(domains) > 1
```

---

## Step 2.5 — Determine mode_hint and changed_sections (spec_change_required + greenfield:false only)

**mode_hint rules:**

```
mode_hint: fast-track:patch
  - All affected_specs sections are descriptive only (typo, clarification, description-only)

mode_hint: fast-track:minor
  - At least one section adds optional content without breaking existing consumers
    (new optional field, new endpoint, new UI state, new component, new flow)

mode_hint: full
  - Any affected section removes/modifies an existing contract, business rule,
    state machine transition, or breaks an existing consumer
```

**Assign `changed_sections` per spec:**

For each entry in `affected_specs`, read the section content and assign semantic labels to `changed_sections`:

```
Structural labels (trigger domain worker in orchestrator-sdd targeted dispatch):
  endpoints        — adds, modifies, or removes HTTP routes or RPC methods
  schemas          — adds, modifies, or removes data schema definitions
  error_codes      — adds, modifies, or removes error code definitions
  component_props  — adds, modifies, or removes component prop contracts
  state_contracts  — adds, modifies, or removes state machine contracts
  data_models      — adds, modifies, or removes entity or model definitions
  auth_rules       — adds, modifies, or removes authentication/authorization rules
  event_types      — adds, modifies, or removes event type definitions
  api_contracts    — modifies API contract compatibility (backwards-breaking or additive)

Text-only labels (no structural impact — domain worker may be skipped):
  descriptions     — rewrites, clarifies, or corrects prose descriptions only
  labels           — renames labels or display strings (no contract change)
  examples         — adds or updates example values
  notes            — adds or updates notes, rationale, or context text
  changelog        — adds changelog or history entries
  formatting       — whitespace, heading, or formatting adjustments only
```

Populate `changed_sections` as a deduplicated list of all assigned labels per spec entry. A section may receive multiple labels if it touches multiple concerns.

---

## Step 2.6 — Determine execution_policy

**Rule — `pipeline`:**

```
pipeline: lean
  ALL of the following must be true:
    - type = implementation_only
    - planner_required = false
    - requirement is visual/cosmetic only:
        matches patterns: color, spacing, padding, margin, alignment,
        font-size, wording, copy, label text, icon swap, hover affordance
        does NOT mention: logic, validation, API, endpoint, data,
        state transition, flow, redirect, calculation, rule
    - affected_specs = [] OR every affected section is purely cosmetic

pipeline: full
  All other cases (default)
```

**Rule — `regression_test_required`:**

```
regression_test_required: true
  ANY of the following is true:
    - requirement describes broken runtime behavior (patterns:
      "not working", "broken", "fails", "wrong", "returns incorrect",
      "does not", "doesn't", "crash", "throws")
    - type = spec_change_required AND any affected section touches a
      business rule (.back.md BR), API contract (openapi.yaml),
      state transition (feature.spec.md §3), or flow (flow.md)
    - type = implementation_only AND pipeline = full AND requirement
      touches logic, validation, API, or data

regression_test_required: false
  ALL of the following:
    - pipeline = lean, OR
    - change is purely declarative (typo, wording, description clarification)
      with no runtime effect
```

**Tie-break rule:** if text is ambiguous and derivation could reasonably produce different results, default to strictest option (`pipeline: full`, `regression_test_required: true`).

---

## Step 3 — Write triage.json and emit terminal events

Create session directory if absent:

```bash
mkdir -p "$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}"
```

Write `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/triage.json` with all fields derived in Steps 1–2.6.

Emit progress checkpoint:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID \
  --event-type task_progress \
  --task-id $ORCH_TASK_ID \
  --attempt $ORCH_ATTEMPT \
  --data '{"phase":"sdd","note":"triage_written","checkpoint":"triage_written","trigger":"{trigger}","type":"{type}","mode_hint":"{mode_hint}","greenfield":{greenfield}}'
```

Emit task completion:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID \
  --event-type task_completed \
  --task-id $ORCH_TASK_ID \
  --attempt $ORCH_ATTEMPT \
  --data '{"phase":"sdd","artifacts":[".orch/sessions/{workflow_id}/triage.json"],"result":"triage_complete","type":"{type}","mode_hint":"{mode_hint}","trigger":"{trigger}"}'
```

> `task_completed` is mandatory. Without it, the orchestrator's terminal check returns
> `sdd_{workflow_id}_triage.status != "completed"` and blocks the entire SDD phase.

---

## Step 4 — Emit structured output

Emit to stdout exactly:

```
## Spec Triage — Result

trigger: {u-spec | u-improve}
requirement: {requirement}
stack: {fe | be | fullstack}
ui_task: {true | false}
greenfield: {true | false}
domains: {domains list — populated for greenfield}
type: {spec_change_required | implementation_only}
mode_hint: {full | fast-track:minor | fast-track:patch}
affected_specs:
{for each spec}
  - path: {path}
    sections: {sections}
    changed_sections: {changed_sections}
    change_summary: {change_summary}
estimated_task_contracts: {N}
planner_required: {true | false}
execution_policy:
  pipeline: {lean | full}
  regression_test_required: {true | false}

triage.json written to: .orch/sessions/{workflow_id}/triage.json
```

STOP. Do not modify any spec. Do not dispatch any agent.

---

## Behavioral rules

| Rule | Description |
|------|-------------|
| `classification_always_runs` | Steps 1b–2.6 run for both triggers. Improve flow uses `improvement_task` from improve-scope.json as the classification input; standard flow uses `requirement` from task spec |
| `stack_classification_deterministic` | `stack` and `ui_task` come from `classify_stack.py` (Step 1b) verbatim. Hand-classification, keyword judgment, or independent `ui_task` overrides are prohibited. Co-presence of UI + backend signals → `fullstack` (never suppressed) |
| `greenfield_domain_extraction` | Greenfield produces `domains` list from requirement analysis — no filesystem scan possible. Orchestrator uses this list for spec-writer task creation |
| `greenfield_mode_hint` | Greenfield always produces `mode_hint: full` — no structural diff is possible |
| `requirement_propagation` | `triage.json.requirement` is the canonical task description. Orchestrator injects it into the spawn prompt of every downstream worker |
| `task_completed_mandatory` | `task_completed` must be emitted before stopping. Without it the orchestrator's terminal check blocks the entire SDD phase |
| `spec_modification` | Prohibited |
| `code_modification` | Prohibited |
| `sub_agent_spawn` | Prohibited |
| `new_artifacts` | Only `triage.json` may be written |
| `ambiguity_resolution` | Default to strictest option: `pipeline: full`, `regression_test_required: true` |
| `affected_spec_not_found` | Set `type: implementation_only` — do not block |
| `triage_json_path` | Always `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/triage.json` |
| `domains_field` | Populated only for greenfield. Non-greenfield always sets `domains: []` |
