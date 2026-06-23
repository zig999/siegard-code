# Template: tc-XX-qa.md

Save to `$SESSION_DIR/qa/$ORCH_TASK_ID-qa.md`:

```markdown
---
task_id: <task_id>
verdict: <approved|rejected>
documentation_verified: <true|false>
---

# QA Report: TC-XX — [Task Contract Title]

**Date:** YYYY-MM-DD
**Layer:** semi-permanent
**Round:** 1 | 2 | 3
**Verdict:** Approved | Rejected
**fe-validate report:** {OUTPUT_DIR}/fe-validate-{run_id}.yaml | skipped

> **Machine-read fields (contract — do not decorate):** the YAML frontmatter above is the
> single source of truth read by the review-phase gates (`read_qa_verdict.py`,
> `check_all_qa_verdicts_approved.py`, `check_micro_unanimous_clean.py`,
> `check_documentation_verified.py`). Emit `verdict` and `documentation_verified` as **bare,
> lowercase** values — `verdict` ∈ {`approved`, `rejected`} (binary only — no "with caveats");
> `documentation_verified` ∈ {`true`, `false`}. The `**Verdict:**` line below is a human label and
> MUST match the frontmatter `verdict`. Set `documentation_verified: true` only after the
> Documentation Verification section below is complete.

> **Note:** This document is semi-permanent — it records the verdict and bugs, not raw test output.
> Do not paste full console logs or CI pipeline output here; summarize in the Test Matrix below.
> Raw execution output is ephemeral — discard after analysis.

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
**Related Task Contract:** TC-XX
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

[Approved] Task Contract can move to Done.
[Rejected] Return to Developer Agent with BUG-01 and BUG-02 for correction.
```
