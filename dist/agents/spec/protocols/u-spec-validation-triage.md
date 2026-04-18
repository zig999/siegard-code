# Protocol: Validation Triage

## Purpose

Defines how validation errors are persisted, selected by the human, and processed incrementally. Allows the human to choose which inconsistencies to resolve now and which to defer, without blocking the entire pipeline.

## When to use

- Spec Validator returned INVALID for a domain
- Human wants to resolve only some of the errors before proceeding
- Multiple domains have errors and human wants to prioritize
- Command `/u-spec-triage [SPECS_DIR]` is executed

---

## Step 1: Persistence of the validation report

When the Spec Validator produces a report with INVALID status, the Orchestrator MUST persist the report at:

```
{SPECS_DIR}/_validation/{domain}-validation.md
```

Create folder `{SPECS_DIR}/_validation/` if it does not exist.

### Persisted file format

Uses the base format from the validation SKILL with additional fields:

```markdown
# Validation: {domain} v{version}
> Validator: Spec Validator | Date: {date}
> Status: INVALID
> Triage: PENDING

## Coverage Map
| UC | Endpoint | BR | UI (screen) | FL (flow) | Status |
|----|----------|----|-------------|-----------|--------|

## Inconsistencies
| # | Type | Source File | Target File | Description | Agent | Severity | Selected |
|---|------|------------|-------------|-------------|-------|----------|----------|
| 1 | cross-ref | auth.back.md | auth.spec.md | BR-03 ref nonexistent UC | Back Spec Agent | blocking | [ ] |
| 2 | error-code | -- | error-codes.md | BUSINESS_X missing from catalog | Spec Writer | blocking | [ ] |

## Error Codes
| error.code | openapi | spec | back | front/screen | Status |
|------------|---------|------|------|-------------|--------|

## Dependencies
| Domain | Exists | Status | Bidirectional |
|--------|--------|--------|---------------|

## Result
- [ ] UC coverage complete
- [ ] Error codes consistent
- [ ] No orphan specs
- [ ] Dependencies valid

## Triage History
| Date | Selected items | Activated agents | Result |
|------|----------------|-----------------|--------|
```

### Additional fields vs base format

| Field | Description |
|-------|-------------|
| `> Triage: PENDING \| IN_PROGRESS \| COMPLETED` | Triage state — controls flow |
| `Agent` column | Back Spec Agent, Front Spec Agent, Spec Writer, or `-- (external)` |
| `Severity` column | `blocking` (prevents handoff) or `warning` (informational) |
| `Selected` column | `[ ]` not selected, `[x]` selected for correction |
| `## Triage History` | Cumulative record of each triage session |

### Updating an existing report

When the Validator is run again on a domain that already has a report:
1. Replace data sections (Coverage Map, Inconsistencies, Error Codes, Dependencies, Result)
2. PRESERVE the existing Triage History
3. Reset Triage to `PENDING` if new errors were found
4. Keep `COMPLETED` if result is VALID

---

## Step 2: Presentation to the human (triage interface)

### 2.1 List pending reports

When starting the triage, display a consolidated table:

```markdown
## Pending validation reports

| # | Domain | Version | Date | Blocking | Warnings | Triage |
|---|--------|---------|------|----------|----------|--------|
| 1 | auth | 1.0.0 | 2026-03-22 | 3 | 2 | PENDING |
| 2 | tasks | 1.1.0 | 2026-03-22 | 2 | 0 | PENDING |

Which domain do you want to triage? (number, "all", or "exit")
```

### 2.2 Display inconsistencies for the selected domain

For each chosen domain:

```markdown
## Inconsistencies — auth v1.0.0

| # | Type | Summary description | Agent | Severity |
|---|------|---------------------|-------|----------|
| 1 | cross-ref | BR-03 ref nonexistent UC | Back Spec Agent | blocking |
| 2 | error-code | BUSINESS_X missing from catalog | Spec Writer | blocking |
| 3 | orphan-spec | UI-05 ref nonexistent operationId | Front Spec Agent | blocking |
| 4 | dependency | domain "billing" in draft | -- (external) | warning |
| 5 | error-code | TASK_LIMIT divergent behavior | Spec Writer | warning |

Which items do you want to fix now? (e.g.: "1,2,3" or "all" or "blocking")
```

### 2.3 Accepted selection options

| Input | Meaning |
|-------|---------|
| `1,2,3` | Specific items by number |
| `all` | Select all items |
| `blocking` | Select only blocking severity |
| `warnings` | Select only warnings |
| `none` | Defer everything — record in history and close |

### 2.4 Update file

After selection:
1. Mark `[x]` on selected items in the validation file
2. Change `> Triage: IN_PROGRESS`

---

## Step 3: Selective routing

### 3.1 Group by responsible agent

Build routing table:

```markdown
| Agent | Items | Description |
|-------|-------|-------------|
| Back Spec Agent | #1 | BR-03 ref nonexistent UC |
| Spec Writer | #2, #5 | error codes (BUSINESS_X, TASK_LIMIT) |
| Front Spec Agent | #3 | UI-05 ref nonexistent operationId |
```

Items with agent `-- (external)` are not routed — flagged to the human as manual action.

### 3.2 Map agent -> file

| Responsible agent | Agent file | Skill file | Required context |
|-------------------|-----------|------------|------------------|
| Spec Writer | `.claude/agents/spec/u-spec-writer.md` | `.claude/skills/u-spec-writing/SKILL.md` | globals + templates + openapi.yaml + .spec.md |
| Back Spec Agent | `.claude/agents/spec/u-spec-back.md` | (inline) | APPROVED openapi.yaml + APPROVED .spec.md + TEMPLATE.back.md |
| Front Spec Agent | `.claude/agents/spec/u-spec-front.md` | (inline) | APPROVED openapi.yaml + APPROVED .spec.md + front/screen/flow templates |

> For full context of each agent, see `protocols/u-spec-context-mounting.md`.

### 3.3 Activate agents

For each agent with pending items:

1. **Invoke via Agent tool** with `subagent_type: "general-purpose"`
2. **Short mode** if the agent has already acted in this session (check in the log)
3. Pass ONLY the selected inconsistencies + affected files
4. **Correction prompt:**

```markdown
## Requested corrections (Triage)

You are being reactivated to fix inconsistencies selected by the human.
Fix ONLY the listed items — do not change other areas of the spec.

## Agent
Read and follow: {agent_file}
Load skill: {skill_file}

## Items to fix
| # | Type | Description | What to fix |
|---|------|-------------|-------------|
| 1 | cross-ref | BR-03 ref nonexistent UC | Fix reference or remove BR |

## Files to modify
- `{SPECS_DIR}/domains/{domain}/back/{domain}.back.md`

## Reference files (read-only)
- `{SPECS_DIR}/domains/{domain}/{domain}.spec.md`
- `{SPECS_DIR}/domains/{domain}/openapi.yaml`
```

5. **Wait for completion** of the agent before invoking the next one (sequential per agent, parallel between independent agents via `run_in_background: true`)
6. **Record result** of each agent: which items were fixed, which failed

### 3.4 Cycle limits

Same rule as the Orchestrator: **maximum 2 cycles per agent**.

If the agent does not resolve the item after 2 attempts:
1. Mark item as `ESCALATED` in the validation report and in the history
2. Notify the human with context from the 2 attempts (produced diffs, errors found)
3. Continue with other agents/items — do not block the pipeline

---

## Step 4: Scoped revalidation

After ALL agents complete their corrections, the Orchestrator activates the Spec Validator to revalidate.

### 4.1 Build revalidation scope

Build the scope list from the corrected items:
- Which UCs, BRs, UIs, FLs were modified by the agents
- Which error codes were changed or added
- Which inter-domain dependencies were affected

### 4.2 Invoke Validator

Invoke via Agent tool:

```markdown
## Triage Revalidation

Agent: .claude/agents/spec/u-spec-validator.md
Skill: .claude/skills/u-spec-validation/SKILL.md

Mode: INCREMENTAL — revalidate only the scope below.
DO NOT re-run full validation.

## Scope
- Affected UCs: {list}
- Corrected BRs: {list}
- Changed error codes: {list}
- Modified files: {list of paths}

## Files
{list of domain files per u-spec-context-mounting.md, Spec Validator section}
```

### 4.3 Update validation report

After the Validator returns, the **Orchestrator** (not the Validator) updates the file `{SPECS_DIR}/_validation/{domain}-validation.md`:

1. **Resolved items:** remove from the Inconsistencies table (or mark as resolved)
2. **New errors found:** add with new sequential numbers and `Selected: [ ]`
3. **Update checklist** of Result (UC Coverage, Error codes, etc.)
4. **Update overall status:** recalculate whether VALID or INVALID

### 4.3 Handle result

**If new errors found in the corrected areas:**
- Add to the validation report with new sequential numbers
- If within cycle limit: automatically route to the agent
- If exceeded limit: present to the human for a new triage cycle

**If all selected items resolved:**
- Update report: resolved items removed from the active table
- Evaluate overall status:

| Situation | Action |
|-----------|--------|
| ALL items (selected + unselected) resolved | Status -> VALID, Triage -> COMPLETED |
| Unselected items remain | Triage -> PENDING (new cycle possible) |
| Selected items partially resolved | Triage -> IN_PROGRESS (escalated items recorded) |

---

## Step 5: Selective handoff and Dev input generation

### 5.1 Write improve_scope block to session log

After the selected items are successfully corrected, the Orchestrator MUST write an `improve_scope` block to `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md` so that `/u-dev` has a work entry. This block connects the triage to the development pipeline.

If `SESSION` was provided in the command: use it directly.
If `SESSION` was not provided: ask the human for the session name and create `{SESSIONS_DIR}/{SESSION}/` if it does not exist.

If `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md` does not exist: create it with the improve_scope block as the only content. If it already exists: append the block at the end of the file.

**Format:**

```yaml
improve_scope:
  source: spec-triage
  generated_on: {YYYY-MM-DD}
  session: {SESSION}
  affected_specs:
    - {path to each corrected spec file}
  estimated_task_contracts: {count of task_contracts entries}
  task_contracts:
    - description: "{correction description}"
      type: bugfix
      priority: P1
      affected_files:
        - {changed spec file}
        - {affected UI or flow file if applicable}
  planner_required: {true|false}
  spec_change_status: completed
```

**Field rules:**
- `source: spec-triage` — always set (distinguishes from `/u-improve` origin)
- `affected_specs` — list all spec files modified during triage (back.md, feature.spec.md, flow.md, etc.)
- `estimated_task_contracts` — set to `len(task_contracts)` for compatibility with u-improve-mode.md Planner activation
- `task_contracts` — one entry per corrected inconsistency group; type is always `bugfix`
- `planner_required: false` — when all items are cosmetic/patch corrections (typos, missing refs, isolated fields); `true` — when corrections affect an endpoint contract, UC flow, or multiple domains
- `spec_change_status: completed` — always set (specs were already corrected by triage before this block is written)

**Rules:**
- Write ONE `improve_scope` block per triage session (groups all corrected items)
- Never overwrite an existing `improve_scope` block — append a new one if the file already contains one

### 5.2 Spec handoff

#### When the domain reaches VALID after triage

Follow the normal handoff protocol (`u-spec-to-dev-handoff.md`).

#### When the domain has already been delivered to Dev

Append a new entry to `{SPECS_DIR}/spec-changelog-notify.yaml` per the handoff protocol (schema `.claude/skills/u-shared-templates/spec-changelog-notify.schema.yaml`), including:

```yaml
- id: NOTIFY-<YYYYMMDD-HHMMSS>
  notified_at: <ISO-8601>
  domain: <domain-name>
  version_from: <previous-version>
  version_to: <new-version>
  change_type: patch | minor | major
  origin: triage
  cr: null
  changed_files: [<paths>]
  summary: "<single structured sentence>"
  dev_impact: no_action | reevaluate_task_contracts | stop_domain_task_contracts
  processed_by: []
```

Impact mapping (drives `dev_impact`):
- `patch` → `no_action`
- `minor` → `reevaluate_task_contracts`
- `major` → `stop_domain_task_contracts`

#### When pending items remain

DO NOT hand off — the domain only goes to Dev when VALID. Record in the log that the triage is in progress.

### 5.3 Guide next step

When completing the triage, inform the human:

```
improve_scope block written to: {SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md

Next step:
  /u-dev [SPECS_DIR] [SESSIONS_DIR] [SESSION] — the Planner will generate a backlog from the triage improvements

Requirement: CLAUDE.md (project root) must contain the field `domain: frontend`, `domain: backend`, or `domain: fullstack`.
```

---

## Step 6: Audit trail

### In the validation report

Each triage session adds an entry in `## Triage History`:

```markdown
| Date | Selected items | Activated agents | Result |
|------|----------------|-----------------|--------|
| 2026-03-22 | #1, #2, #3 | Back Spec Agent, Spec Writer | #1 OK, #2 OK, #3 ESCALATED |
```

### In the Orchestrator log

Record in `log-orchestrator-spec.md`:

```markdown
| Date | Domain | Action | Result |
|------|--------|--------|--------|
| 2026-03-22 | auth | Triage: items #1,#2,#3 selected | #1 OK, #2 OK, #3 escalated |
```

---

## Safety rules

1. **Never fix unselected items** — respect the human's choice
2. **Never hand off with pending blocking items** — even if the human requests it
3. **ALWAYS persist the report** — do not depend on session context
4. **Maintain idempotency** — if the same item is selected in a later session and is already resolved, detect and skip
5. **Do not overwrite history** — each triage session ADDS to the history, never replaces
6. **Compatibility with synchronous flow** — if the human does not use `/u-spec-triage`, the current synchronous flow continues to work normally. Persistence is additive, not substitutive
7. **Stale reports** — before starting triage, read `{domain}-validation-result.yaml` field `validation.artifact_version` and compare with `version:` in the frontmatter of `{domain}.spec.md`. If they differ, alert the human before proceeding: "Validation result was generated from spec v{X}, current spec is v{Y}. Recommended: revalidate with `/u-spec` before triaging."
8. **Concurrency** — if `Triage: IN_PROGRESS`, alert the human before starting a new session: "Triage in progress for this domain. Do you want to continue the previous session or restart?"
