---
name: u-fe-standards
description: Shared quality standards used by both Developer and QA agents (frontend). Defines mandatory tests per Task Contract type, code quality rules, visual design rules, universal edge-case checklist, and bug severity criteria. Single source of truth to avoid divergence between implementation and verification.
user-invocable: false
---

# SKILL: Standards (shared)

## Purpose

This skill is the **single source of truth** for the quality standards the Developer must follow when implementing and the QA must use when verifying. Both agents receive this file in context — any change here automatically propagates to both sides.

---

## 1. Test Requirements by Task Contract Type

> TC type values match `exec_type` in the Task Contract YAML. Use exact strings below — case-sensitive.

| Task Contract type | What the Developer must deliver | What the QA must verify |
|---|---|---|
| **feature** | Unit for utils/hooks + Component for each new component + Integration for API flows | All criteria + edge cases. Documentation required for new artifacts |
| **enhancement** | Tests for modified behaviors (unit or component) + update of affected existing tests | Modified criteria + in-scope edge cases. Regression required. Docs if new artifacts |
| **refactoring** | Tests for preserved behaviors must keep passing; do not add new logic without a test | Preserved behaviors. Regression required. Docs only if the interface changed |
| **visual-adjustment** | Snapshot or render test confirming the component still renders correctly. Verify that tokens used exist in `design-system/` | Visual behavior + accessibility + design-system/ conformance. Visual regression required |
| **bugfix** | Regression test required: reproduces the bug before the fix and confirms it passes after | Only the reported case + immediate regression |

---

## 2. Code Quality Rules

### 2.1 Test Coverage

| Criterion | Approved | Rejected (quality BUG) |
|---|---|---|
| Criteria coverage | Every acceptance criterion has at least 1 test | Criterion without test — High BUG |
| Edge case coverage | Required edge cases for the Task Contract type have tests | Edge case without test — Medium BUG |
| Test behavior | `expect(screen.getByText(...))` | `expect(component.state...)` — Medium BUG |
| Integration covers API error | There is a 4xx/5xx mock + visual feedback verification | Only tests success — Medium BUG |
| Regression on bugfix | Reproduces the bug and confirms the fix | Missing — High BUG |
| Tests pass | All tests pass on execution | Failure — High BUG |

### 2.2 Code Standards

| Criterion | Approved | Rejected (quality BUG) |
|---|---|---|
| Design system | Visual styles use `var(--token-name)` from `design-system/tokens.md` — no hardcoded color, font, or spacing values | Hardcode detected or invented token — Medium BUG |
| Inline CSS | No use of `style=""` or `style={{}}` in JSX — all styling via CSS classes, CSS Modules, or Tailwind | Inline CSS detected — Medium BUG |
| `transition` | CSS transitions must specify explicit properties (e.g., `transition: opacity 200ms`) — never `transition: all` | `transition: all` detected — Medium BUG |
| `TODO`/`FIXME` | Forbidden in committed code. Exception: `// TODO(TC-XX):` linked to an active Task Contract | `TODO`/`FIXME` without issue reference — Medium BUG |
| Entry-surface composition | A route/page that is the feature's entry surface MUST render its real children by the end of the feature wave — never ship a placeholder ("em construção", "swaps the inner content", "Placeholder X") deferred to a later TC unless that TC's acceptance criteria explicitly own the wiring AND the dependency is declared | Entry surface renders a placeholder/stub with no owning composition TC — **High BUG** (gated by `check_no_orphan_placeholders`) |
| `eslint-disable` | Forbidden without a comment justifying the reason on the same or preceding line | `eslint-disable` without justification — Medium BUG |
| i18n (when `i18n: true`) | No hardcoded user-facing strings — all text via translation keys | Hardcoded string in rendered output — Medium BUG |
| Commented-out code | Delete disabled code — do not commit commented-out blocks | Commented-out code block detected — Low BUG |
| XSS — `dangerouslySetInnerHTML` | Forbidden without DOMPurify sanitization + `// eslint-disable-next-line react/no-danger` with justification comment | Raw HTML injection without sanitization — **Critical BUG** |
| XSS — user input in attributes | User input never interpolated into `href`, `src`, or event handler strings | Unsanitized input in href/src — **Critical BUG** |
| Error Boundary | Each page/route component wrapped in `<ErrorBoundary>` with non-empty fallback | Missing ErrorBoundary at page level — High BUG |
| Code splitting | Routes use `React.lazy` + `Suspense` — no eager import of page components | All pages imported eagerly — Medium BUG |
| Bundle imports | Named imports only for tree-shaking (`import { format } from 'date-fns'`) | `import *` from large library — Medium BUG |
| Animation accessibility | Animations and transitions wrapped in `@media (prefers-reduced-motion: no-preference)` | Animation without `prefers-reduced-motion` — Medium BUG |
| Component size | Component file ≤ 300 lines — split into subcomponents past that | Component file > 300 lines — Medium BUG |
| Primitive reuse | UI markup composes existing primitives from the DS primitive layer declared in `CLAUDE.md` (convention: `components/ui/` — Card, Badge, Table, Form…) | Hand-rolled markup duplicating an available primitive instead of composing it — Medium BUG (`reimplemented-primitive`) |
| List `key` stability | Dynamic-list items keyed by a stable unique id | Array index used as `key` in a reorderable/insertable/deletable list — Medium BUG |
| Dashboard widget isolation | Each independently loadable dashboard widget owns its data fetch, its skeleton, and its `ErrorBoundary` | Single request hydrates the whole dashboard, or a widget lacks its own boundary/skeleton — Medium BUG |

---

## 2.3 Security, Architecture, and Accessibility

> Full rationale, code examples, and enforcement patterns: `.claude/skills/u-fe-development/SKILL.md` §Security, §Error boundaries, §Performance.
> The rows in §2.2 above are the enforcement checklist — this section is the reference for implementation guidance.

---

## 3. Visual Design Rules

> **Canonical thresholds:** `u-ui-design/anti-patterns.md` is the single source of truth for detection thresholds. In case of conflict between this section and `anti-patterns.md`, `anti-patterns.md` prevails.

### 3.1 Typography

| Rule | Compliant | Violation (quality BUG) |
|---|---|---|
| Line height | `line-height ≥ 1.3` on elements with ≥ 2 lines of text | `line-height < 1.3` on multi-line text — Medium BUG |
| Body text size | `font-size ≥ 12px` on content elements | `font-size < 12px` on text content — Medium BUG |
| All-caps body | `text-transform: uppercase` restricted to labels and headings with ≤ 20 characters | `text-transform: uppercase` on element with > 20 characters of text content — Medium BUG |
| Letter spacing | `letter-spacing ≤ 0.05em` on paragraph and body-level elements | `letter-spacing > 0.05em` on body text — Medium BUG |
| Heading hierarchy | Heading levels increment by 1 in DOM order (h1 → h2 → h3) | Heading level skips (e.g. h1 → h3 with no h2) — Medium BUG |
| Justified text | `text-align: left` or `text-align: start` for body text | `text-align: justify` without `hyphens: auto` — Medium BUG |

### 3.2 Color

| Rule | Compliant | Violation (quality BUG) |
|---|---|---|
| Gray on color | Text on colored background uses a shade of the background hue — not a neutral gray | Neutral gray text (HSL saturation < 10%) on non-neutral background — Medium BUG |
| Pure black background | Large surfaces tinted toward brand hue (e.g. `oklch(12% 0.01 250)`) | `background-color: #000` or `rgb(0,0,0)` or `oklch(0% 0 0)` on large surfaces — Medium BUG |
| Gradient text | Text color is a solid value | `background-clip: text` combined with any gradient function — Medium BUG |

### 3.3 Layout

| Rule | Compliant | Violation (quality BUG) |
|---|---|---|
| Line length | Text containers have `max-width` between `65ch` and `75ch` | `<p>`, `<li>`, `<article>` body text with no `max-width` constraint and rendered width > 75ch — Medium BUG |
| Container padding | Elements with `border` or non-neutral `background-color` have `padding ≥ 8px` | Padding < 8px on bordered or colored container with text content — Medium BUG |
| Padding/width proportion | Container padding scales proportionally with container size: padding ≈ 1/6–1/4 of the container's own width. Visually distinct containers (e.g., small card and extra-large card on the same screen) must not share the same padding value | Padding < 1/8 or > 1/3 of container width on a visually distinct element; or identical padding applied to containers of clearly different sizes — Medium BUG. **Detection: visual/QA only — not statically automatable (depends on computed layout width)** |

### 3.4 Motion

| Rule | Compliant | Violation (quality BUG) |
|---|---|---|
| Layout property animation | Transitions and animations target only `transform` and `opacity`. For height transitions: use `grid-template-rows: 0fr → 1fr` | `transition` or `animation` targeting `width`, `height`, `padding`, or `margin` — Medium BUG |
| Easing | Easing uses `cubic-bezier` values within `[0, 1]` range (e.g. `cubic-bezier(0.25, 1, 0.5, 1)`) | `cubic-bezier` with y1 or y2 outside `[0, 1]` (overshoot / bounce) — Medium BUG |

### 3.5 CSS Patterns

| Rule | Compliant | Violation (quality BUG) |
|---|---|---|
| Side-tab border | Cards and containers use full border, background tint, or no side indicator | `border-left` or `border-right` ≥ 3px with non-neutral color on card/container — or ≥ 1px when `border-radius` is set — Medium BUG |
| Border on rounded element | Rounded elements (`border-radius > 8px`) do not use top/bottom accent borders | `border-top` or `border-bottom` ≥ 2px with non-neutral color on element with `border-radius > 8px` — Medium BUG |

### 3.6 Composition / Alignment

> Rules in this section are Gestalt-based layout principles. Detection is visual/QA — not statically automatable via linter unless noted.

| Rule | Compliant | Violation (quality BUG) |
|---|---|---|
| Axis-sharing | Every visible element shares at least one axis (horizontal or vertical) with another element in the same composition. No element is positioned with arbitrary offsets unanchored to a neighbor | Element with arbitrary offset sharing no axis with any sibling — Medium BUG. **Exception:** intentionally offset absolute-positioned elements (tooltips, badges, overlays) with offset documented in code |
| Text block start-axis | Text elements within the same content block (same section, card, or semantic group) share the same inline-start edge (`left` in LTR, `right` in RTL). Intentional indentation (nested list, blockquote, code block) is accepted only when semantically justified | Text elements in the same block with different inline-start offsets and no semantic indentation justification — Medium BUG. CSS-agnostic: applies to flow, flex column, and grid. Use `start` (not `left`) to support RTL |
| Row baseline | Multiple text elements arranged in a single horizontal row with different `font-size` values use typographic baseline alignment (`align-items: baseline` in flex/grid) | Horizontal flex/grid row with mixed `font-size` text using `align-items: center` or `align-items: start` — Medium BUG. **Scope: text-only rows. Rows that contain icons must follow the icon + text centering rule instead — these two rules are mutually exclusive per row** |
| Form label alignment | Form labels use `text-align: start` (or `text-align: left` in LTR-only projects). Centering labels is forbidden | `text-align: center` on a `<label>` or label-equivalent element outside an isolated stat-card context — Medium BUG. **Exception:** a label that belongs visually to a large centered metric/stat number (e.g., `"Total Revenue"` below a centered `"$1.2M"`) |
| Icon + text vertical centering | An icon adjacent to text (same horizontal row, same group) uses vertical center alignment (`align-items: center`). Gap between icon and text must be consistent across all occurrences of the same visual pattern within the same feature | Icon and adjacent text vertically misaligned; or gap value inconsistent across occurrences of the same icon+text pattern within the same feature — Medium BUG. **Note:** specific gap values (e.g., Tailwind `gap-2`, `gap-1.5`) are project-specific — define them in the project's own CLAUDE.md, not here |

---

## 4. Edge Case Checklist

> **Accessibility single source of truth:** this section (§4 WCAG 2.2 AA checklist) is the canonical accessibility reference. All other files that reference accessibility (UI spec, design system implementation.md, QA checklist) defer to this section.

### Handling patterns

| Scenario | Developer: handle as | QA: verify |
|---|---|---|
| Null or undefined input | Guard clause at function entry | Guard clause present and covered by test |
| Empty list | Return `[]`, never `null` | `[]` returned and rendered without crash |
| Resource not found | Return `null` or throw `NotFoundError` — document which | Behavior matches documented contract |
| API error (4xx/5xx) | Throw typed error with status — never propagate as `unknown` | Typed error thrown and visual feedback shown to user |
| Data outside expected range | Validate at input layer (DTO/schema) before processing | Boundary values tested |

### Input data
- [ ] Null or undefined input
- [ ] Empty string `""`
- [ ] Zero or negative number
- [ ] Empty list `[]`
- [ ] Boundary values (e.g., max characters, min/max of a range)
- [ ] Special characters and unicode in text fields

### System state
- [ ] Behavior when the requested resource does not exist (404 vs error 500)
- [ ] Behavior with unauthorized user
- [ ] Behavior with expired session

### API calls
- [ ] Behavior when the API returns an error (4xx / 5xx) — error message shown to the user?
- [ ] Behavior with network timeout — loading state interrupted correctly?
- [ ] Behavior with malformed payload or missing field — crash or graceful fallback?

### Interaction and accessibility (WCAG 2.2 AA)
- [ ] Interactive elements work with keyboard (Tab, Enter, Esc, Space for toggles)
- [ ] Images have meaningful `alt` text; decorative images use `alt=""`
- [ ] Forms have associated `<label>` or `aria-label` for every input
- [ ] Invalid fields expose `aria-invalid` and link their message via `aria-describedby`
- [ ] Focus indicator visible on all focusable elements (`outline` not suppressed without replacement)
- [ ] Focus is never fully hidden by sticky headers, overlays, or other content (WCAG 2.2 SC 2.4.11 Focus Not Obscured)
- [ ] Dynamic content updates announced via `aria-live` or focus management (e.g., modals trap focus)
- [ ] ARIA roles are semantically correct (`role="button"` only on non-button elements that behave as buttons)
- [ ] Color is not the only means of conveying information (error state uses icon + text, not red color alone)
- [ ] Contrast ratio meets WCAG AA: 4.5:1 for normal text, 3:1 for large text and UI components
- [ ] Interactive targets meet WCAG 2.2 SC 2.5.8 Target Size (Minimum) — ≥ 24×24px CSS. Project floor is stricter: ≥ 32px in any context and ≥ 44×44px on mobile (see Responsive design)

### Responsive design
- [ ] Layout is usable at 320px (mobile), 768px (tablet), 1024px (desktop), and 1440px (wide)
- [ ] No horizontal scroll at any standard breakpoint
- [ ] Touch targets are at least 44 × 44px on mobile

> **Developer:** handle the applicable scenarios for your Task Contract and document them in the delivery file.
> **QA:** verify that applicable scenarios were handled and have a corresponding test.

---

## 5. Bug Severity Classification

| Severity | Criterion | Impact on the Task Contract |
|---|---|---|
| **Critical** | System crashes, data corruption, security breach | Reject + block other tests |
| **High** | Acceptance criterion not met, main flow broken | Reject the Task Contract |
| **Medium** | Edge case not handled, inconsistent behavior | Approve with mandatory caveat |
| **Low** | Cosmetic issue, unclear error message | Log it, does not block approval |

---

## 6. Root-cause falsification (R5)

A finding can be real but its diagnosed cause wrong — and a wrong cause sends the dev fix in the wrong direction (SIEGARD D5: QA blamed a static import for a `routes.spec.tsx` timeout and prescribed `React.lazy`; the real cause was CPU contention under the full 83-file parallel suite — the spec passed in isolation (~1.3s) and unchanged with `--testTimeout=30000`. `React.lazy` did NOT fix it).

**QA side — before assigning a cause to any timeout / flake / performance finding:**
1. Reproduce in isolation vs. under load — run the failing test alone, then under the full suite.
2. Vary the relevant knob — `testTimeout`, concurrency (`--maxWorkers` / `poolOptions`), test ordering/seed.
3. Record the result in the finding's `root_cause.evidence`, and set `root_cause.confidence`:
   - `high` only when the cause was reproduced/verified by steps 1–2;
   - `low` when the cause is inferred from reading and was NOT reproduced.

Heuristic: **a test that times out in the full suite but passes in isolation ⇒ suspect contention / ordering / shared-state, NOT the code under test, until proven otherwise.**

**Dev side — consuming a QA finding:** a finding with `root_cause.confidence` below `high` carries a *hypothesis*, not a verified cause. Reproduce it before applying the suggested fix; do not apply the prescribed fix verbatim on a `low`-confidence cause.
