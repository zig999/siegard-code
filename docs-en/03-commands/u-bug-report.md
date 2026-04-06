# /u-bug-report -- Bug Report Command

Captures structured bug reports through a guided questionnaire.

## Usage

```
/u-bug-report [SPECS_DIR] [SESSION]
```

## How it works

1. Reads the `u-bug-report` skill for the question flow
2. Asks structured questions: Where? How to reproduce? Expected behavior? Actual behavior?
3. Generates a `bug##.md` file in `{SESSIONS_DIR}/{SESSION}` (sequential numbering)
4. Suggests the next command based on the bug type:
   - If it reveals a spec gap: suggest `/u-spec` first, then `/u-dev`
   - If it's a code-only issue: suggest `/u-dev` directly

## Generated artifact

`bug##.md` -- Structured bug report consumed by the Planner agent during `/u-dev` in Bug mode.

## Multiple bugs

Run `/u-bug-report` multiple times to capture several bugs. Each generates a separate `bug##.md` file. When `/u-dev` runs in Bug mode, the Planner reads all `bug##.md` files and generates fix Stories with priority classification (P0/P1).
