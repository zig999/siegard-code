---
description: >
  Validates frontend code quality rules and design system rules against target files.
  No Task Contract or development session required — runs standalone against any file or glob.
  Scope: frontend only (TSX/TS/CSS). Backend validation is out of scope.
  Usage: /u-fe-validate [TARGET] [SPECS_DIR] [RULES]
  Examples:
    /u-fe-validate src/pages/dashboard.tsx docs/specs
    /u-fe-validate "src/components/**/*.tsx" docs/specs visual_design
    /u-fe-validate src/pages/home.tsx
---

## Scope

This command applies **frontend rules only**:
- **code_quality** — `u-fe-standards §2`: inline CSS, design tokens, XSS, Error Boundary, transitions, etc.
- **visual_design** — `u-fe-standards §3`: typography, color, layout, motion, CSS patterns

Backend architecture rules (DI, DTOs, pagination) are **not validated here**.

---

## Variable Resolution

Extract from `$ARGUMENTS`:

```
/u-fe-validate [TARGET] [SPECS_DIR] [RULES]
```

| Variable | Position | Required | Description |
|---|---|---|---|
| `TARGET` | 1st | yes | File path or glob (e.g., `src/pages/**/*.tsx`) |
| `SPECS_DIR` | 2nd | no | Project specs directory — enables design token validation |
| `RULES` | 3rd | no | `code_quality`, `visual_design`, or `all` (default: `all`) |

**Resolving `TARGET`:**
1. First argument → use as-is
2. If not provided → stop and request: `"Provide a target path or glob: /u-fe-validate [TARGET]"`

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in `CLAUDE.md` (project root) → use *(canonical source — preferred)*
2. Second argument containing `/` or `\` → use as `SPECS_DIR` *(fallback)*
3. None → proceed without token validation; the skill will log a `low` warning

**Resolving `RULES`:**
1. Third argument → validate against allowed values: `code_quality`, `visual_design`, `all`
2. If invalid value: stop and request valid options
3. If not provided: default to `all`

**Resolving `OUTPUT_DIR`:**
1. `sessions_dir:` field in `CLAUDE.md` → use `{sessions_dir}/fe-validate/`
2. None → use `./fe-validate-reports/` in the project root

---

## Files to Read

1. `.claude/skills/u-fe-standards/SKILL.md` — §2 Code Quality Rules + §3 Visual Design Rules (rule source of truth)
2. `CLAUDE.md` — check for `i18n: true` flag (affects i18n-hardcode rule)
3. If `SPECS_DIR` provided: `{SPECS_DIR}/front/design-system/tokens.md` — valid token list

---

## Execution

This command is self-contained: `u-fe-standards` §2/§3 is the rule source of truth and the steps below are the validation process. For a broader audit (anti-patterns, accessibility, `--fix`), use the `u-fe-review` skill instead.

1. Expand TARGET into file list
2. Load rule context
3. Apply code_quality rules (if `RULES` includes `code_quality` or `all`)
4. Apply visual_design rules (if `RULES` includes `visual_design` or `all`)
5. Build and write report

Output the report file at `{OUTPUT_DIR}/fe-validate-{run_id}.yaml`.

After writing the YAML report, present a human-readable summary:

```
## /u-fe-validate — {TARGET}

Status: passed | failed
Verdict: approved | approved_with_caveats | rejected

Files scanned: {N}
Findings: {critical} critical · {high} high · {medium} medium · {low} low

[Table of findings if any]

Report: {OUTPUT_DIR}/fe-validate-{run_id}.yaml
```

---

## Related commands

| Command | Scope | When to use |
|---|---|---|
| `/u-fe-validate` | Frontend — code quality + visual design | Ad-hoc validation of pages/components without a TC |
| `/u-dev` | Frontend + Backend | Full development session with Task Contracts |
| `/u-spec` | Specs | Generate or review technical specifications |
