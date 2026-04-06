---
description: Quick questionnaire to capture incremental improvements. Generates improve##.md files in the dev session. Usage: /u-improve [SPECS_DIR] [SESSION] (e.g., /u-improve docs/specs fix-error-states)
---

Read the following file:
1. .claude/skills/u-improve/SKILL.md

## Variable Resolution

Extract from `$ARGUMENTS`:
- **First argument** = `SPECS_DIR` (optional if `specs_dir:` is set in `CLAUDE.md`)
- **Second argument** = `SESSIONS_DIR` (optional)
- **Last argument** = `SESSION`

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in `CLAUDE.md` (project root) -> use *(canonical source — preferred)*
2. First argument containing `/` or `\` -> use as `SPECS_DIR` *(fallback — warn the human: "specs_dir is not configured in CLAUDE.md. Recommended to add it for consistency across sessions.")*
3. None -> ask the human for the desired SPECS_DIR (first question in the flow)

**Resolving `SESSIONS_DIR` (priority):**
1. `sessions_dir:` field in `CLAUDE.md` (project root) -> use *(canonical source — preferred)*
2. Second argument containing `/` or `\` (only if 3+ args) -> use as `SESSIONS_DIR` *(fallback)*
3. None -> **stop** and request: "Configure `sessions_dir:` in CLAUDE.md before continuing."

If `SESSION` is not provided:
1. Check if sessions exist in `{SESSIONS_DIR}` and list them
2. Ask the human: "Which session? (existing or new name)"

Create `{SESSIONS_DIR}/{SESSION}/` if it does not exist.

## Execution

Follow the skill's question flow to collect improvements.
Ask one question at a time. After each improvement, generate the `improve##.md` file in `{SESSIONS_DIR}/{SESSION}`.

> **Note:** when suggesting next steps, use the syntax with SESSION: `/u-dev [SPECS_DIR] [SESSIONS_DIR] [SESSION]`
