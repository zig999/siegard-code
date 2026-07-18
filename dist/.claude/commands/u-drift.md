---
description: >
  Analyze drift between approved specs and implemented code. Builds a deterministic
  spec inventory, extracts a code inventory (evidence-checked), matches them by exact
  keys, and emits a machine-consumable drift-report.json plus a human-readable
  drift-report.md. Read-only: writes only under {SPECS_DIR}/_validation/. Every finding
  cites evidence and carries a mechanical follow-up action. Backend scope.
  Usage: /u-drift [CODE_DIR]
---

# Command: /u-drift — Spec ↔ Code Drift Analysis

Runs **standalone, outside the orchestration engine** (mirrors `/u-reverse-spec`): no
`.orch` events, no worker registration, no retry/supervisor coverage. A dead subagent
during this run is recovered manually. The auditable trail is `drift-report.json`
itself — every finding cites evidence; the report pins `spec_content_hash` +
`code_commit_sha` so consumers can detect a stale report before acting.

> **Read-only contract.** This command NEVER modifies specs or source code. Its only
> writes are under `{SPECS_DIR}/_validation/`.

## Variable Resolution

Extract from `$ARGUMENTS`:
- **First argument** = `CODE_DIR` (required — path to the project with code).

**Resolving `CODE_DIR` (priority):**
1. First argument containing `/` or `\` → use as `CODE_DIR`
2. None → stop and request: "Provide the project path: `/u-drift [path]`"

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in the project's `CLAUDE.md`
2. Default: `{CODE_DIR}/specs`

## Initial Validation

1. Confirm `CODE_DIR` was provided; else stop and request it.
2. Confirm `{CODE_DIR}` exists on the filesystem; else stop and request the correct path.
3. Confirm `{SPECS_DIR}` exists and contains at least one `openapi.yaml`; else stop:
   "No specs found under `{SPECS_DIR}`. Run `/u-reverse-spec {CODE_DIR}` first, or set `specs_dir:` in CLAUDE.md."
4. Create `{SPECS_DIR}/_validation/` if it does not exist.

## Execution Process (foreground — do not background these steps)

### Step 1 — Spec inventory (deterministic)

```bash
python3 .claude/skills/u-drift-analysis/scripts/spec_inventory.py \
  --specs-dir "{SPECS_DIR}" \
  --out "{SPECS_DIR}/_validation/spec-inventory.json" \
  --skipped-out "{SPECS_DIR}/_validation/spec-skipped.json"
```

- Exit `3` → **stop** with `E_no_approved_specs`: "No `Status: approved` backend specs under `{SPECS_DIR}`. Approve specs via `/u-spec` before auditing drift; drafts cannot be audited against the code that generated them."
- Exit `2`/`1` → stop and report the JSON error.
- Exit `0` → continue. Note the `approved_domains` ids from stderr for the next step.

### Step 2 — Code inventory (LLM, evidence-checked)

Invoke the analyzer via the **Agent** tool in **code-inventory mode**:

```
## Task
Produce a code-inventory.json for the source in {CODE_DIR}.

## Mode
code-inventory   (standalone — do NOT emit any orchestration event; no task_id is issued)

## Inputs
- CODE_DIR: {CODE_DIR}
- OUT_FILE: {SPECS_DIR}/_validation/code-inventory.json
- approved_domains: {list of approved spec domain ids from Step 1}

## Agent
Read and follow: .claude/agents/reverse-spec/u-reverse-spec-analyzer.md
Follow the section "Mode: code-inventory (used by /u-drift)".
Load the skill: .claude/skills/u-reverse-spec-analysis/SKILL.md
Name each module id to match an approved spec domain id where the code implements it.
```

### Step 3 — Validate the code inventory (determinism guard)

```bash
python3 .claude/skills/u-drift-analysis/scripts/validate_inventory.py \
  --code-inventory "{SPECS_DIR}/_validation/code-inventory.json" \
  --code-dir "{CODE_DIR}"
```

- Exit `0` → continue.
- Exit `1` → **re-dispatch the analyzer exactly once** (Step 2) with the returned
  `violations` list appended to the prompt under `## Fix these violations`. Re-run this
  step. If it fails again → **stop** with `E_inventory_validation_failed` and attach the
  violations. Never proceed on an unvalidated inventory.

### Step 4 — Match (deterministic)

```bash
python3 .claude/skills/u-drift-analysis/scripts/match_drift.py \
  --spec-inventory "{SPECS_DIR}/_validation/spec-inventory.json" \
  --code-inventory "{SPECS_DIR}/_validation/code-inventory.json" \
  --skipped "{SPECS_DIR}/_validation/spec-skipped.json" \
  --generated-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --out "{SPECS_DIR}/_validation/drift-report.json"
```

If any finding has `artifact_type: base_path` (status `undecidable`), tell the user the
router `base_path` could not be aligned and that endpoint findings for that domain were
suppressed to avoid noise — the fix is in the finding's `handoff`.

### Step 4B — Semantic verdicts (behavioral drift + business rules)

Structural matching decides only presence/absence. This step examines the pairs that
matched — `aligned` endpoints (contract drift) and business rules (no code key) — via
the semantic analyzer. Invoke via the **Agent** tool, standalone:

```
## Task
Produce drift-verdicts.json for the already-matched spec↔code pairs.

## Mode
standalone — emit NO orchestration event; no task_id is issued.

## Inputs
- SPEC_INVENTORY: {SPECS_DIR}/_validation/spec-inventory.json
- CODE_INVENTORY: {SPECS_DIR}/_validation/code-inventory.json
- DRIFT_REPORT:   {SPECS_DIR}/_validation/drift-report.json
- CODE_DIR:       {CODE_DIR}
- OUT_FILE:       {SPECS_DIR}/_validation/drift-verdicts.json

## Agent
Read and follow: .claude/agents/spec/u-drift-analyzer.md
```

Then validate the verdicts (determinism guard — same fail-closed contract as Step 3):

```bash
python3 .claude/skills/u-drift-analysis/scripts/validate_findings.py \
  --verdicts "{SPECS_DIR}/_validation/drift-verdicts.json" \
  --code-dir "{CODE_DIR}"
```

- Exit `1` → re-dispatch the analyzer once with the `violations` appended under
  `## Fix these violations`; re-validate. Still failing → **skip the merge** and note in
  the completion summary that the semantic layer was unavailable (the structural report
  stands on its own). Never merge unvalidated verdicts.

Merge the validated verdicts into the report (deterministic):

```bash
python3 .claude/skills/u-drift-analysis/scripts/merge_semantic.py \
  --report "{SPECS_DIR}/_validation/drift-report.json" \
  --verdicts "{SPECS_DIR}/_validation/drift-verdicts.json" \
  --out "{SPECS_DIR}/_validation/drift-report.json"
```

> Step 4B is additive. If it is skipped (validation failed twice), the Step-4 structural
> report is the deliverable and every count remains valid — `drifted`/`undecidable`
> semantic findings are simply absent.

### Step 5 — Render (deterministic)

```bash
python3 .claude/skills/u-drift-analysis/scripts/render_report.py \
  --report "{SPECS_DIR}/_validation/drift-report.json" \
  --out "{SPECS_DIR}/_validation/drift-report.md"
```

## Completion — present outcome and handoffs

Read `drift-report.json` and present the summary counts, then group actionable handoffs:

```
## Drift analysis complete — {SPECS_DIR}/_validation/drift-report.md

| Metric | Count |
|--------|-------|
| Domains analyzed | {domains_analyzed} |
| Aligned | {aligned} |
| Not implemented (missing in code) | {missing_in_code} |
| Undocumented (missing in spec) | {missing_in_spec} |
| Undecidable | {undecidable} |
| Skipped (draft) | {skipped_draft} |

### Suggested follow-ups (mechanical — no interpretation)
- `create_implementation_cr` findings → implement via `/u-dev {SPECS_DIR} <workflow_id>`
- `update_spec` findings → document via `/u-improve`
- `no_spec_domain` skips → run `/u-reverse-spec {CODE_DIR}` scoped to that module
- `needs_human` / `base_path` findings → human triage (finding carries fix_spec + fix_code)
```

Do NOT act on any handoff automatically — `/u-drift` is analysis-only. Emit no
free-form recommendation; the report's `default_action` per finding is the contract.

## Artifacts written (all under `{SPECS_DIR}/_validation/`)
- `spec-inventory.json` — spec side (schema `spec-inventory.schema.yaml`)
- `spec-skipped.json` — draft domains excluded
- `code-inventory.json` — code side (schema `code-inventory.schema.yaml`)
- `drift-report.json` — the report (schema `drift-report.schema.yaml`)
- `drift-report.md` — human-readable render

## Escalation codes
| Code | Condition | Recovery |
|------|-----------|----------|
| `E_no_approved_specs` | Step 1 exit 3 — no approved backend specs | Approve specs via `/u-spec`, then re-run |
| `E_inventory_validation_failed` | Step 3 failed twice | Inspect `violations`; fix the analyzer inputs or code paths; re-run |
| `E_base_path_mismatch` | A `base_path` finding is present | Set the real router prefix and re-run (finding carries the fix) |
