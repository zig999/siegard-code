# /u-improve -- Improvement Command

Captures incremental improvement requests through a quick guided questionnaire.

## Usage

```
/u-improve [SPECS_DIR] [SESSION]
```

## How it works

1. Reads the `u-improve` skill for the question flow
2. Asks 3 quick questions about the desired improvement
3. Generates an `improve##.md` file in `{SESSIONS_DIR}/{SESSION}` (sequential numbering)
4. Suggests the next command based on the improvement type:
   - If it affects the API contract: suggest `/u-spec` first, then `/u-dev`
   - If it's implementation-only: suggest `/u-dev` directly

## Generated artifact

`improve##.md` -- Structured improvement request consumed by the Planner agent during `/u-dev`.

## Multiple improvements

Run `/u-improve` multiple times to capture several improvements. Each generates a separate `improve##.md` file. When `/u-dev` runs in Improve mode, the Planner reads all `improve##.md` files and generates Task Contracts for each.
