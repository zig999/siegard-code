# Template: us-XX-qa.md (Backend)

Save to `{SESSIONS_DIR}/{SESSION}/us-XX-qa.md`:

```markdown
# QA Report: US-XX — [Story Title]

**Date:** YYYY-MM-DD
**Round:** 1 | 2 | 3
**Verdict:** Approved | Approved with caveats | Rejected

---

## Test Matrix

| ID    | Scenario                       | Type        | Priority | Result     |
|-------|-------------------------------|-------------|----------|------------|
| T-01  | [description]                 | Integration | High     | Passed      |
| T-02  | [description]                 | Unit        | High     | Failed      |
| T-03  | Edge case: [description]      | Unit        | Medium   | Passed      |

---

## Bugs Found

[list with bug report template, or "No bugs found"]

### BUG-XX: [Short descriptive title]

**Severity:** Critical | High | Medium | Low
**Related Story:** US-XX
**File/module:** `path/file.ts` (approximate line if known)

**Steps to reproduce:**
1. [HTTP request or initial state]
2. [action executed — endpoint, payload, headers]
3. [next action if needed]

**Actual result:**
[What actually happens — status code, body, error in log]

**Expected result:**
[What should happen according to the acceptance criterion or API spec]

**Evidence:**
[Error log, response body, stack trace]

---

## Edge Cases — Results

- Null input — validation returns 400
- Duplicate resource — returns 500 instead of 409 -> BUG-01
- Request without auth — returns 401 (ok, but generic message)

---

## Security — Verification

- Parameterized queries — verified
- No secrets in logs — verified
- Rate limiting — not implemented (recorded as debt)

---

## Documentation Verification

- JSDoc on UserService.createUser — present and adequate
- `.env.example` — DATABASE_URL added
- JSDoc missing on AuthMiddleware -> BUG-02 (Low)

---

## Recommendation

[Approved] Story can move to Done.
[Rejected] Return to Developer Agent with BUG-01 and BUG-02 for correction.
```
