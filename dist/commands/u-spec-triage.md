---
description: Select and fix spec validation errors incrementally. Displays persisted reports and allows choosing which inconsistencies to resolve. Usage: /u-spec-triage [SPECS_DIR] [SESSION] (e.g., /u-spec-triage docs/specs fix-error-states)
---

## Variable Resolution

Extract from `$ARGUMENTS`:
- **First argument** = `SPECS_DIR` (optional if `specs_dir:` is set in `CLAUDE.md`)
- **Last argument** = `SESSION` (optional — string without `/` or `\`)

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in `CLAUDE.md` (project root) -> use *(canonical source — preferred)*
2. First argument containing `/` or `\` -> use as `SPECS_DIR` *(fallback — warn the human: "specs_dir is not configured in CLAUDE.md. Recommended to add it for consistency across sessions.")*
3. None -> **stop** and request: "Configure `specs_dir:` in CLAUDE.md or provide it as an argument: `/u-spec-triage [specs_dir]`"

**Resolving `SESSIONS_DIR` (priority):**
1. `sessions_dir:` field in `CLAUDE.md` (project root) -> use *(canonical source — preferred)*
2. None -> **stop** and request: "Configure `sessions_dir:` in CLAUDE.md before continuing."

If `SESSION` is provided, the session directory is `{SESSIONS_DIR}/{SESSION}/`.

If `SESSION` is not provided, triage runs normally but when writing the improve_scope block (Step 5), it will ask the human which session to save to.

## Initial Validation

1. Read `CLAUDE.md` (project root). Confirm the field `domain: frontend`, `domain: backend`, or `domain: fullstack` exists. If the field is missing, **stop** and request: "Set the field `domain: frontend`, `domain: backend`, or `domain: fullstack` in CLAUDE.md before continuing."

2. Confirm that `SPECS_DIR` was resolved. If not, stop and request: "Configure `specs_dir:` in CLAUDE.md or provide it as an argument: `/u-spec-triage [specs_dir] [session]`".

3. Confirm that the `{SPECS_DIR}` directory exists on the filesystem. If it does not exist, stop and request the correct path.

3. Check if `{SPECS_DIR}/_validation/` exists and contains `*-validation.md` files. If it does not exist or is empty:

```
No validation reports found in {SPECS_DIR}/_validation/.

Possible actions:
  - /u-spec [SPECS_DIR] — run spec pipeline (includes validation)
  - /u-reverse-spec [SPECS_DIR] — generate specs from existing code
```

## Report Detection

1. List all files in `{SPECS_DIR}/_validation/` matching the `*-validation.md` pattern
2. For each report, read the header and extract: domain, version, date, status, triage
3. Filter only reports with status `INVALID` and triage other than `COMPLETED`

If no pending reports found:

```
All validation reports have status VALID or COMPLETED.

No action needed. To revalidate: /u-spec [SPECS_DIR]
```

## Staleness Check

For each pending report, compare the validation file timestamp with the spec file timestamps for that domain.

If specs were modified after the report:

```
Warning: specs for domain {domain} were modified after the last validation.
Recommended: revalidate with /u-spec [SPECS_DIR] before triaging.
Continue anyway? [Y / N]
```

## Initialization

1. Read `CLAUDE.md` — project configuration.

2. Read the global spec files:
   - `.claude/skills/u-spec-globals/conventions.md`
   - `.claude/skills/u-spec-globals/error-codes.md`

3. Load the orchestrator agent with triage mode instruction:
   - `.claude/agents/spec/u-spec-orchestrator.md`
   - `.claude/agents/spec/u-spec-orchestrator-protocols.md`
   - Instruction: "Triage mode. Validation reports found in `{SPECS_DIR}/_validation/`. Follow the protocol `protocols/u-spec-validation-triage.md` to present errors, collect human selection, route fixes to agents, and revalidate."

4. The Orchestrator takes control following the triage protocol.

## Completion

When finished (all selected errors processed):

```
Triage completed for: {list of processed domains}

Result:
  - {N} errors fixed
  - {N} errors pending (not selected)
  - {N} errors escalated to human

improve_scope block written to: {SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md

Next steps:
  - Implement the fixes: /u-dev [SPECS_DIR] [SESSIONS_DIR] [SESSION]
  - If errors remain: /u-spec-triage [SPECS_DIR] [SESSION] (new cycle)
  - To fully revalidate: /u-spec [SPECS_DIR]

Note: `domain:` was validated at session start.
```

## Available Protocols (load on demand)
- `.claude/agents/spec/protocols/u-spec-validation-triage.md` — triage protocol
- `.claude/agents/spec/protocols/u-spec-context-mounting.md` — minimal context per agent
- `.claude/agents/spec/protocols/u-spec-versioning.md` — versioning rules

## Available Agents (invoked by the Orchestrator via Agent tool)
- `.claude/agents/spec/u-spec-writer.md`
- `.claude/agents/spec/u-spec-back.md`
- `.claude/agents/spec/u-spec-front.md`
- `.claude/agents/spec/u-spec-validator.md`

## Available Skills (loaded by agents as needed)
- `.claude/skills/u-spec-writing/SKILL.md`
- `.claude/skills/u-spec-validation/SKILL.md`
- `.claude/skills/u-spec-globals/`
