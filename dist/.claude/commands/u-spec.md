---
description: Starts the Spec-Driven Development pipeline. Initializes or resumes the SDD phase for a project. Usage: /u-spec [SPECS_DIR] [workflow_id] ["requirement"] (e.g., /u-spec docs/specs my-session "Add payment flow to checkout domain")
---

## Variable Resolution

Extract from `$ARGUMENTS`:
- **First argument** = `SPECS_DIR` (optional if `specs_dir:` is set in `CLAUDE.md`)
- **Last non-quoted argument** = `workflow_id` (optional — human-readable identifier for this workflow; must not contain `/` or `\`)
- **Remaining quoted text** = `REQUIREMENT` (optional — the requirement to specify)
- **`INVOCATION_SOURCE`** (optional — set by parent agent, never by human): one of `human | u-improve | spec-triage`. Defaults to `human` when absent.

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in `CLAUDE.md` (project root) → use *(canonical source — preferred)*
2. First argument containing `/` or `\` → use as `SPECS_DIR` *(fallback — warn the human: "specs_dir is not configured in CLAUDE.md. Recommended to add it for consistency across sessions.")*
3. None → **stop** and request: "Configure `specs_dir:` in CLAUDE.md or provide it as an argument: `/u-spec [specs_dir]`"

**Resolving `ORCH_PROJECT_DIR`:**
Derive from `pwd` at command invocation (absolute path to project root).

**Resolving `workflow_id`:**
1. Last non-quoted argument (string without `/` or `\`)
2. If not provided: check `.orch/log.jsonl` for an existing workflow_id — if found, use it. If none, generate one: `spec-<YYYYMMDD>`

**Resolving `REQUIREMENT`:**
1. Quoted string in `$ARGUMENTS` → pass to orchestrator as inline requirement
2. None → `orchestrator-sdd` will prompt the human after dispatch

---

## Initial Validation

1. Read `CLAUDE.md` (project root). If it does not exist, stop and advise: "Create the `CLAUDE.md` file at the project root with the configuration (domain, stack, conventions) before continuing."

2. Confirm that `SPECS_DIR` was resolved. If not, stop.

3. Confirm that the `{SPECS_DIR}` directory exists on the filesystem — or will be initialized (new mode).

---

## Mode Detection

Check the event log for existing workflow state:

```bash
python3 .claude/skills/orch-state/scripts/detect_mode.py
```

Output JSON fields: `mode` (`"new"` | `"resume"`), `workflow_id`, `last_seq`.

Additional checks for reverse-engineering context:

| Condition | Mode |
|-----------|------|
| No log / empty log | **new** |
| Log has sdd phase events | **resume** |
| `{SPECS_DIR}/_meta/origin-reverse-spec.md` exists, no log | **reverse-eng review** |
| `{SPECS_DIR}/_meta/merge-pending-review.md` exists, no log | **merge review** |

---

## Pre-execution Estimate

Before initializing, present an estimate to the human based on detected mode:

```
## Estimate — /u-spec [SPECS_DIR]

Mode: {detected mode}
Domains: {N} (list domains found in specs/ or provided in the requirement)

| Stage | Agents | Per-worker context | Estimated Time |
|-------|--------|--------------------|----------------|
| Writer | 1 | ~5K per domain | 2-3 min |
| Reviewer | 1 | ~3K per domain | 1-2 min |
| Back+Front | 2 (parallel) | ~8K per domain | 3-5 min |
| Validator | 1 | ~3K per domain | 1-2 min |
| **Per-domain context** | **5** | **~{N}K** | **~{N} min** |

Note: Fast-track skips Back+Front (~40% reduction).
Note: Reverse-eng review skips Writer (~20% reduction).

Proceed? [Y / N]
```

**Simplified per-worker context estimate (planning proxy, NOT billed token spend):**
- New/major mode: `{domains} × 19K tokens` (~7-12 min per domain)
- Fast-track mode: `{domains} × 11K tokens` (~4-7 min per domain)
- Review mode: `{domains} × 14K tokens` (~5-8 min per domain)

> **These figures are per-worker context-window sizes, used only to size each spawn.**
> Cumulative *billed* tokens for the whole workflow are materially higher — often
> several times these numbers — because each worker re-sends its context every turn
> and the pipeline runs many workers (× turns × any retries) plus orchestrator
> overhead. Do NOT read the per-domain figure as total spend. The authoritative
> per-spawn budget check is the orchestrator's `context_budget_evaluated` event
> (§5.2.5); this table is only a pre-flight sizing hint.

If `INVOCATION_SOURCE = u-improve`: suppress the `[Y/N]` prompt — confirmation already happened at the `/u-improve` gate. Emit estimate as informational only and proceed.

---

## Initialization — new mode

1. Read global spec files (for context — pass to orchestrator-sdd):
   - `.claude/skills/u-spec-globals/conventions.md`
   - `.claude/skills/u-spec-globals/error-codes.md`
   - `.claude/skills/u-spec-globals/glossary.md`

2. If `{SPECS_DIR}/` does not exist, create the initial directory structure:
   ```
   {SPECS_DIR}/
     _global/     (copy conventions, error-codes, glossary here)
     _templates/  (copy templates here)
     domains/     (empty — domain subdirectories created by spec workers)
     front/       (empty — design-system/ created by spec-front worker)
   ```
   > `front/design-system/` must not be created empty — it is the spec-front worker's responsibility.

3. Invoke the meta-orchestrator:

   ```yaml
   subagent_type: orchestrator
   description: "Start SDD phase — new spec run"
   prompt: |
     Start a new SDD workflow.
     workflow_id: {workflow_id}
     ORCH_PROJECT_DIR: {ORCH_PROJECT_DIR}
     SPECS_DIR: {SPECS_DIR}
     log_seq_at_spawn: 0
     {if REQUIREMENT provided}
     requirement: "{REQUIREMENT}"
     {/if}
     {if INVOCATION_SOURCE = u-improve}
     invocation_source: u-improve
     {/if}
   ```

---

## Initialization — resume mode

Invoke the meta-orchestrator directly. State is derived from the log — no manual re-initialization needed.

```yaml
subagent_type: orchestrator
description: "Resume SDD workflow"
prompt: |
  Resume workflow.
  workflow_id: {workflow_id}
  ORCH_PROJECT_DIR: {ORCH_PROJECT_DIR}
  SPECS_DIR: {SPECS_DIR}
  log_seq_at_spawn: {last_seq}
```

---

## Initialization — reverse-eng review mode

1. Read `{SPECS_DIR}/_meta/origin-reverse-spec.md` — generation metadata.
2. Read `{SPECS_DIR}/_temp/analysis-report.md` if it exists.
3. Read the global spec files (conventions, error-codes, glossary).

4. Invoke the meta-orchestrator with reverse-eng context:

   ```yaml
   subagent_type: orchestrator
   description: "SDD phase — reverse-engineering review"
   prompt: |
     Start SDD workflow in reverse-engineering review mode.
     workflow_id: {workflow_id}
     ORCH_PROJECT_DIR: {ORCH_PROJECT_DIR}
     SPECS_DIR: {SPECS_DIR}
     log_seq_at_spawn: 0
     reverse_eng_mode: true
     Specs in {SPECS_DIR}/ were generated from existing code and have draft status.
     All domains must go through the review pipeline: spec-reviewer → [spec-back/spec-front adjustments if needed] → spec-validator.
     analysis_report_path: {SPECS_DIR}/_temp/analysis-report.md
     Items marked with <!-- TO CONFIRM --> require special attention from spec-reviewer.
   ```

---

## Initialization — merge review mode

Same as reverse-eng review but read `{SPECS_DIR}/_meta/merge-pending-review.md` as context instead. Remove the marker file after the orchestrator confirms approval.

---

## Completion

When the orchestrator returns `status: phase_complete`, display:

```
Specification completed for: {list of domains}

Files produced in {SPECS_DIR}/:
  - {list of files}

Next steps:
  - To start implementation: /u-dev {workflow_id}
  - To apply a targeted improvement: /u-improve "{description}"
```
