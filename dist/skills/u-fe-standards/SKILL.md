---
name: u-fe-standards
description: Shared quality standards used by both Developer and QA agents (frontend). Defines mandatory tests per Story type, universal edge-case checklist, and test quality criteria. Single source of truth to avoid divergence between implementation and verification.
user-invocable: false
---

# SKILL: Standards (shared)

## Purpose
This skill is the **single source of truth** for the quality standards the Developer must follow when implementing and the QA must use when verifying. Both agents receive this file in context — any change here automatically propagates to both sides.

---

## Mandatory tests per Story type

| Story type | What the Developer must deliver | What the QA must verify |
|---|---|---|
| **New feature** | Unit for utils/hooks + Component for each new component + Integration for API flows | All criteria + edge cases. Documentation required for new artifacts |
| **Improvement** | Tests for modified behaviors (unit or component) + update of affected existing tests | Modified criteria + in-scope edge cases. Regression required. Docs if new artifacts |
| **Refactoring** | Tests for preserved behaviors must keep passing; do not add new logic without a test | Preserved behaviors. Regression required. Docs only if the interface changed |
| **Visual fix** | Snapshot or render test confirming the component still renders correctly. Verify that tokens used exist in `design-system/` | Visual behavior + accessibility + design-system/ conformance. Visual regression required |
| **Bugfix** | Regression test required: reproduces the bug before the fix and confirms it passes after | Only the reported case + immediate regression |

---

## Test quality criteria

These criteria apply to both writing (Developer) and validation (QA).

| Criterion | Approved | Rejected (quality BUG) |
|---|---|---|
| Criteria coverage | Every acceptance criterion has at least 1 test | Criterion without test — High BUG |
| Edge case coverage | Required edge cases for the Story type have tests | Edge case without test — Medium BUG |
| Test behavior | `expect(screen.getByText(...))` | `expect(component.state...)` — Medium BUG |
| Integration covers API error | There is a 4xx/5xx mock + visual feedback verification | Only tests success — Medium BUG |
| Regression on bugfix | Reproduces the bug and confirms the fix | Missing — High BUG |
| Tests pass | All tests pass on execution | Failure — High BUG |
| Design system | Visual styles use `var(--token-name)` from `design-system/tokens.md` — no hardcoded color, font, or spacing values | Hardcode detected or invented token — Medium BUG |
| Inline CSS | No use of `style=""` or `style={{}}` in JSX — all styling via CSS classes, CSS Modules, or Tailwind | Inline CSS detected — Medium BUG |
| `transition: all` | CSS transitions must specify explicit properties (e.g., `transition: opacity 200ms`) — never `transition: all` | `transition: all` detected — Medium BUG |
| `TODO`/`FIXME` | Forbidden in committed code — open an issue/task before committing. Exception: `// TODO(US-XX):` linked to an active Story | `TODO`/`FIXME` without issue reference — Medium BUG |
| `eslint-disable` | Forbidden without a comment justifying the reason on the same line or the line above | `eslint-disable` without justification — Medium BUG |
| Animation accessibility | Animations and transitions must respect `@media (prefers-reduced-motion: reduce)` — disable or reduce motion | Animation without `prefers-reduced-motion` — Medium BUG |

**Additional rules:**
- Test **behavior**, not implementation: prefer `expect(screen.getByText("Saved!")).toBeVisible()` over `expect(component.state.saved).toBe(true)`
- Each acceptance criterion of the Story must have at least one mapped test
- Edge cases handled in production code must have a corresponding test
- Integration tests with API must cover both success **and** error responses
- Avoid tests that always pass (`expect(true).toBe(true)`) — the QA will reject them

---

## Edge cases — universal checklist

For every Story, verify the following:

**Handling patterns (Developer):**

| Scenario | How to handle |
|---|---|
| Null or undefined input | Guard clause at the beginning of the function |
| Empty list | Return `[]`, never `null` |
| Resource not found | Return `null` or throw `NotFoundError` (document which one) |
| API call returns error (4xx/5xx) | Throw typed error with status, never let it propagate as `unknown` |
| Data outside expected range | Validate at the input layer (DTO/schema) before processing |

**Input data:**
- [ ] Null or undefined input
- [ ] Empty string `""`
- [ ] Zero or negative number
- [ ] Empty list `[]`
- [ ] Boundary values (e.g., max characters, min/max of a range)
- [ ] Special characters and unicode in text fields

**System state:**
- [ ] Behavior when the requested resource does not exist (404 vs error 500)
- [ ] Behavior with unauthorized user
- [ ] Behavior with expired session

**API calls (front end consumes as a black box):**
- [ ] Behavior when the API returns an error (4xx / 5xx) — error message shown to the user?
- [ ] Behavior with network timeout — loading state interrupted correctly?
- [ ] Behavior with malformed payload or missing field — crash or graceful fallback?

**Interaction and accessibility:**
- [ ] Interactive elements work with keyboard (Tab, Enter, Esc)
- [ ] Images have alt text; forms have associated labels
- [ ] Focus indicator is visible on focusable elements

> **Developer:** handle the applicable scenarios for your Story and document them in the delivery file.
> **QA:** verify that applicable scenarios were handled and have a corresponding test.

---

## Bug severity classification

| Severity | Criterion | Impact on the Story |
|---|---|---|
| **Critical** | System crashes, data corruption, security breach | Reject + block other tests |
| **High** | Acceptance criterion not met, main flow broken | Reject the Story |
| **Medium** | Edge case not handled, inconsistent behavior | Approve with mandatory caveat |
| **Low** | Cosmetic issue, unclear error message | Log it, does not block approval |
