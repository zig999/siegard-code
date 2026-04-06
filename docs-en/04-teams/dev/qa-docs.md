# QA & Docs Agent

Tests and documents completed Stories. Exists in two variants:
- `u-be-qa-docs.md` -- Backend QA
- `u-fe-qa-docs.md` -- Frontend QA

## Responsibilities

- Verify that tests pass (test-gate)
- Analyze test coverage per Story type
- Check for edge cases and regression
- Classify bugs by severity
- Generate QA report
- Approve or reject the Story

## Two-phase operation

### Phase 1: Test-gate (fast)
Ensures all tests pass before proceeding to qualitative analysis. If tests fail, the Story is immediately rejected for rework.

### Phase 2: Full mode
Comprehensive analysis:
- Coverage verification per Story type
- Edge case testing
- Regression testing
- Documentation completeness
- Spec compliance

### Frontend-specific checks
- UI state coverage (loading, empty, error, success)
- Error mapping to UI handling
- Design system conformance
- Accessibility verification (keyboard navigation, ARIA attributes, focus management)
- Visual regression

## Bug severity classification

| Severity | Description |
|----------|-------------|
| **Critical** | Blocks core functionality or causes data loss |
| **High** | Major feature broken but workaround exists |
| **Medium** | Minor feature issue, low user impact |
| **Low** | Cosmetic issue, no functional impact |

## Definition of Done

### Spec-first Stories
- All acceptance criteria met
- Test coverage per spec requirements
- Traceability to UC-NN (BE) or UI-NN (FE) verified
- No critical or high bugs

### Bug/Improve Stories
- Bug is fixed and non-reproducible
- Regression tests added
- No new bugs introduced

## Rework cycle

When QA rejects a Story:
1. Developer is reactivated in short mode with QA feedback
2. Developer fixes and resubmits
3. QA retests
4. Max **3 rework rounds** before escalation to human

## Embedded skills

- **QA skill** (`u-be-qa-docs` / `u-fe-qa-docs`) -- Test types, verification scope, report template
- **Standards skill** (`u-be-standards` / `u-fe-standards`) -- Test quality criteria, edge cases, severity classification

## Output

`{SESSIONS_DIR}/{SESSION}/us-XX-qa.md` -- QA report (archived to `_temp/` after Story completion).
