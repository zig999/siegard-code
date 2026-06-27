---
description: Reverse-engineers specs from existing code. Analyzes source code, identifies entities, endpoints and business rules, and generates complete spec documentation (OpenAPI, .spec.md, .back.md, screens, flows) with draft status. Usage: /u-reverse-spec [project-path]
---

## Variable Resolution

Extract from `$ARGUMENTS`:
- **First argument** = `CODE_DIR` (required — path to the project with code)

**Resolving `CODE_DIR` (priority):**
1. First argument containing `/` or `\` -> use as `CODE_DIR`
2. None -> stop and request: "Provide the project path: `/u-reverse-spec [path]`"

**Resolving `SPECS_DIR` (where specs will be generated — priority):**
1. `specs_dir:` field in the project's `CLAUDE.md`
2. Default: `{CODE_DIR}` (specs generated at `{CODE_DIR}/specs/`, legacy behavior)

## Initial Validation

1. Confirm that `CODE_DIR` was provided as an argument. If not, stop and request: "Provide the path to the project with existing code: `/u-reverse-spec [path]`".

2. Confirm that the `{CODE_DIR}` directory exists on the filesystem. If it does not exist, stop and request the correct path.

3. Confirm that the directory contains source code. Check for the existence of at least one of the following:
   - `package.json`, `tsconfig.json` (Node.js/TypeScript)
   - `requirements.txt`, `pyproject.toml` (Python)
   - `pom.xml`, `build.gradle` (Java/Kotlin)
   - `go.mod` (Go)
   - `Cargo.toml` (Rust)
   - `src/` folder with code files

   If no indicators are found, stop and advise: "The directory does not appear to contain a software project. Check the path and try again."

4. Read `CLAUDE.md` if it exists — extract stack, conventions, and configurations that can accelerate detection.

## Mode Detection

Check for the existence of `{SPECS_DIR}/log-reverse-spec.md` and `{SPECS_DIR}/`:

| log exists | specs/ exists | Mode |
|------------|---------------|------|
| No | No | **New** — first run, generate everything |
| No | Yes | **Merge** — specs exist, analyze and compare |
| Yes | * | **Resume** — previous session interrupted |

- **New mode:** follow full initialization below
- **Merge mode:** SUSPENDED — see block below
- **Resume mode:** load the Orchestrator with instruction to read the log and resume

**If mode == "merge": stop immediately.**

The merge submode is suspended. Deterministic conflict-resolution rules are not yet
implemented — running merge risks silently overwriting valid spec content with stale
code-derived content, with no auditable resolution trail.

Inform the user:

> **reverse_eng merge is currently unavailable.**
> Deterministic conflict-resolution rules have not yet been implemented.
> Available alternatives:
> - Delete the existing `{SPECS_DIR}/` and re-run `/u-reverse-spec {CODE_DIR}` → triggers **new** mode
> - If a prior session was interrupted, re-run `/u-reverse-spec {CODE_DIR}` with the existing log → triggers **resume** mode

Do not invoke `orchestrator-reverse-spec`. Do not modify any file. Stop.

## Initialization (new mode)

1. Create the `{SPECS_DIR}/_temp/` folder if it does not exist (for analysis-report.md).

2. Read the global spec files:
   - `.claude/skills/u-spec-globals/conventions.md`
   - `.claude/skills/u-spec-globals/error-codes.md`
   - `.claude/skills/u-spec-globals/glossary.md`

3. Load the orchestrator agent:
   - `.claude/agents/reverse-spec/orchestrator-reverse-spec.md`

4. The Orchestrator takes control and starts stack detection.

## Initialization (merge mode)

1. Read `{SPECS_DIR}/` to inventory existing specs.
2. Create `{SPECS_DIR}/_temp/` if it does not exist.
3. Load the Orchestrator with instruction: "Merge mode. Existing specs in specs/. Analyze code and compare."

## Initialization (resume mode)

1. Read `{SPECS_DIR}/log-reverse-spec.md` to identify the last state.
2. Load the Orchestrator with instruction: "Session resume. Read the log and continue from where it left off."

## Completion

When the pipeline finishes, the Orchestrator displays a summary of generated artifacts. After that, display:

```
Reverse engineering completed for: {list of domains}

Artifacts generated in {SPECS_DIR}/:
  - {list of files}

Status: All artifacts with DRAFT status

Next steps:
  - To review and approve generated specs: /u-spec [SPECS_DIR]
  - To re-analyze after code changes: /u-reverse-spec [CODE_DIR]
  - To implement improvements on the documented base: /u-dev [SPECS_DIR] [workflow_id]
```

## Available Agents (invoked by the Orchestrator via Agent tool)
- `.claude/agents/reverse-spec/u-reverse-spec-analyzer.md` — analyzes source code
- `.claude/agents/reverse-spec/u-reverse-spec-writer.md` — generates specs from analysis

## Available Skills (loaded by agents as needed)
- `.claude/skills/u-reverse-spec/SKILL.md` — code -> spec mapping
- `.claude/skills/u-reverse-spec-analysis/SKILL.md` — search patterns by stack
- `.claude/skills/u-spec-globals/` — conventions, error codes, glossary
- `.claude/skills/u-spec-templates/` — templates for all spec types
- `.claude/skills/u-spec-writing/SKILL.md` — OpenAPI quality

