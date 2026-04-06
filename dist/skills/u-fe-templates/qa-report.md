# Template: us-XX-qa.md

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
| T-01  | [description]                 | Unit        | High     | Passed      |
| T-02  | [description]                 | Manual      | High     | Failed      |
| T-03  | Edge case: [description]      | Unit        | Medium   | Passed      |

---

## Bugs Found

[list with bug report template, or "No bugs found"]

### BUG-XX: [Short descriptive title]

**Severity:** Critical | High | Medium | Low
**Related Story:** US-XX
**File/component:** `path/file.ts` (approximate line if known)

**Steps to reproduce:**
1. [initial system state]
2. [action executed]
3. [next action if needed]

**Actual result:**
[What actually happens]

**Expected result:**
[What should happen according to the acceptance criterion]

**Evidence:**
[Error log, screenshot, response payload]

---

## Edge Cases — Results

- Null input — handled correctly
- Empty list — returns 500 instead of [] -> BUG-01
- Network timeout — no visual feedback (low severity, recorded)

---

## Documentation Verification

- JSDoc on ProductCard — props documented (name, price, onAdd)
- `.env.example` — NEXT_PUBLIC_API_URL added
- JSDoc missing on useProductFilter hook -> BUG-02 (Low)

---

## Recommendation

[Approved] Story can move to Done.
[Rejected] Return to Developer Agent with BUG-01 and BUG-02 for correction.
```
