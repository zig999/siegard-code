## Epic Integration Protocol

When all Stories in an Epic reach `Done`:

1. Activate **QA & Docs** with:
   - All `{SESSIONS_DIR}/{SESSION}/us-XX-delivery.md` from the Epic
   - All `{SESSIONS_DIR}/{SESSION}/us-XX-qa.md` from the Epic
   - `{SESSIONS_DIR}/{SESSION}/ui-[epic].md` — visual consistency
2. Verifications:
   - [ ] Stories work in sequence (end-to-end flow)
   - [ ] No contract breakage between Stories
   - [ ] Visual consistency preserved
3. If rejected: technical bug -> Developer, UX inconsistency -> human
4. Record as `In testing — integration (round N)`
5. Only mark Epic as `Done` after approval

### Traceability Matrix

After Epic integration approval, QA MUST generate `{SESSIONS_DIR}/{SESSION}/traceability-matrix.md` with the complete requirements-to-code mapping:

```markdown
# Traceability Matrix — Epic {name}

> Date: {YYYY-MM-DD} | Session: {SESSION} | Stories: {N}

## Tracing UC -> Story -> Test -> Code

| UC | Story | Acceptance Criterion | Test File | Main Code | Status |
|----|-------|---------------------|-----------|-----------|--------|
| UC-01 | US-01 | Login with valid credentials | test-login.ts | src/auth/login.tsx | Yes |
| UC-01 | US-01 | Login with wrong password | test-login.ts | src/auth/login.tsx | Yes |
| UC-02 | US-03 | Automatic token refresh | test-refresh.ts | src/auth/refresh.tsx | Yes |

## Tracing BR -> Implementation

| BR | Story | Implemented in | Tested in | Status |
|----|-------|---------------|-----------|--------|
| BR-01 | US-01 | src/auth/validate.ts | test-validation.ts | Yes |
| BR-02 | US-01 | src/auth/validate.ts | test-validation.ts | Yes |

## Tracing UI -> Component

| UI | Screen | Component | Test | Status |
|----|--------|-----------|------|--------|
| UI-01 | login.screen.md | LoginForm.tsx | test-login-form.ts | Yes |
| UI-04 | login.screen.md | ErrorAlert.tsx | test-error-alert.ts | Yes |

## Coverage

| Metric | Total | Implemented | Tested | Coverage |
|--------|-------|-------------|--------|----------|
| UC | {N} | {N} | {N} | {N}% |
| BR | {N} | {N} | {N} | {N}% |
| UI | {N} | {N} | {N} | {N}% |
| FL | {N} | {N} | {N} | {N}% |
```

**Rules:**
- Generate ONCE at the end of Epic integration (not per Story)
- Use `us-XX-delivery.md` to extract code and test paths
- Use `us-XX-qa.md` to extract test coverage
- If Spec-first mode: cross-reference with specs to validate complete coverage
- The file is permanent — it stays in `{SESSIONS_DIR}/{SESSION}/` as a delivery record
