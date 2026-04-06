# Bug Fix Flow

Structured bug documentation and correction.

## When to use

- Known bug that needs to be fixed
- Unexpected behavior reported by users
- Failed test that reveals a code issue

## Command sequence

### Code-only bug
```
/u-bug-report {SPECS_DIR} {SESSION} -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
```

### Bug that reveals a spec gap
```
/u-bug-report {SPECS_DIR} {SESSION} -> /u-spec {SPECS_DIR} -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
```

## Step-by-step

1. Run `/u-bug-report` -- Answer the structured questionnaire (where, how to reproduce, expected, actual)
2. The command generates `bug##.md` and suggests next steps
3. If the bug reveals a spec gap:
   - Run `/u-spec` to correct the specification first
4. Run `/u-dev` -- The orchestrator detects Bug mode
5. Planner classifies bug priority (P0/P1) and generates fix Stories

### Bug pipeline variants

| Bug type | Pipeline |
|----------|----------|
| **Visual/UI adjustment** | Lean pipeline: Developer direct (no Planner, no TDD), visual QA only |
| **Incorrect behavior / integration error / unknown** | Full pipeline: Planner -> Developer (TDD) -> QA |

### Quality gate
The `bug reproducao` field must be filled before the Developer starts work -- ensuring the bug can be verified as fixed.
