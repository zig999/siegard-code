## Epic Integration Protocol

When all Task Contracts in an Epic reach `Done`:

1. Activate **QA & Docs** with:
   - All `{SESSIONS_DIR}/{SESSION}/tc-XX-delivery.md` from the Epic
   - All `{SESSIONS_DIR}/{SESSION}/tc-XX-qa.md` from the Epic
   - `{SESSIONS_DIR}/{SESSION}/ui-[epic].md` — visual consistency
   - **Shared component regression entries** from `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md` (search for "Shared component regression risk:" lines relevant to this Epic's Task Contracts)
2. Verifications:
   - [ ] Task Contracts work in sequence (end-to-end flow)
   - [ ] No contract breakage between Task Contracts
   - [ ] Visual consistency preserved
   - [ ] **Shared component regression:** for each component modified by this Epic and flagged in the orchestrator log, verify that prior Epics' Task Contracts that consume the component still pass their QA acceptance criteria. Reference the specific traceability entries from the log when reporting failures.
3. If rejected: technical bug -> Developer, UX inconsistency -> human
4. Record as `In testing — integration (round N)`
5. Only mark Epic as `Done` after approval

### Traceability Matrix

After Epic integration approval, QA MUST generate `{SESSIONS_DIR}/{SESSION}/traceability-matrix.md` with the complete requirements-to-code mapping:

```markdown
# Traceability Matrix — Epic {name}

> Date: {YYYY-MM-DD} | Session: {SESSION} | Task Contracts: {N}

## Tracing UC -> Task Contract -> Test -> Code

| UC | Task Contract | Acceptance Criterion | Test File | Main Code | Status |
|----|-------|---------------------|-----------|-----------|--------|
| UC-01 | TC-01 | Login with valid credentials | test-login.ts | src/auth/login.tsx | Yes |
| UC-01 | TC-01 | Login with wrong password | test-login.ts | src/auth/login.tsx | Yes |
| UC-02 | TC-03 | Automatic token refresh | test-refresh.ts | src/auth/refresh.tsx | Yes |

## Tracing BR -> Implementation

| BR | Task Contract | Implemented in | Tested in | Status |
|----|-------|---------------|-----------|--------|
| BR-01 | TC-01 | src/auth/validate.ts | test-validation.ts | Yes |
| BR-02 | TC-01 | src/auth/validate.ts | test-validation.ts | Yes |

## Tracing UI -> Component

| UI | Screen | Component | Test | Status |
|----|--------|-----------|------|--------|
| UI-01 | login.feature.spec.md | LoginForm.tsx | test-login-form.ts | Yes |
| UI-04 | login.feature.spec.md | ErrorAlert.tsx | test-error-alert.ts | Yes |

## Coverage

| Metric | Total | Implemented | Tested | Coverage |
|--------|-------|-------------|--------|----------|
| UC | {N} | {N} | {N} | {N}% |
| BR | {N} | {N} | {N} | {N}% |
| UI | {N} | {N} | {N} | {N}% |
| FL | {N} | {N} | {N} | {N}% |
```

**Rules:**
- Generate ONCE at the end of Epic integration (not per Task Contract)
- Use `tc-XX-delivery.md` to extract code and test paths
- Use `tc-XX-qa.md` to extract test coverage
- If Spec-first mode: cross-reference with specs to validate complete coverage
- The file is permanent — it stays in `{SESSIONS_DIR}/{SESSION}/` as a delivery record
