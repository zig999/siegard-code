---
name: u-fe-review
description: Ad-hoc audit of a frontend component or feature against all quality rules (code quality, design system, visual design, anti-patterns, accessibility). User-invocable. Produces a structured report; with --fix flag also applies mechanical auto-fixes.
user-invocable: true
invocation: /u-fe-review [target] [--fix]
dependencies:
  required:
    - skill: u-fe-standards
      path: .claude/skills/u-fe-standards/SKILL.md
      sections: ["§2.2 Code quality", "§3 Visual design", "§4 Accessibility"]
      on_missing: "halt — report status: error / reason: dependency_not_found / dependency: u-fe-standards"
    - skill: u-ui-design
      path: .claude/skills/u-ui-design/anti-patterns.md
      on_missing: "halt — report status: error / reason: dependency_not_found / dependency: u-ui-design/anti-patterns.md"
  optional:
    - artifact: design-system/tokens.md
      resolve_order:
        - arg: --design-system
        - path: "{SPECS_DIR}/front/design-system/tokens.md"
      on_missing: set ds_available=false — skip DS-02 — emit Warning
---

# SKILL: Frontend Review

## Purpose

Audit one or more frontend files against the complete set of quality rules used in the development pipeline. Produces a structured report with findings grouped by severity. With `--fix`, applies mechanical auto-fixes directly to the files.

> This skill is **out-of-pipeline** — it does not require a Task Contract or active session. It can be run at any time on any frontend file or directory.

---

## Invocation

```
/u-fe-review <target> [--fix] [--design-system <path>]
```

| Argument | Required | Description |
|---|---|---|
| `target` | yes | File path or directory. If directory: scan all `.tsx`, `.ts`, `.jsx`, `.js`, `.css`, `.scss` files recursively |
| `--fix` | no | Apply auto-fixable findings in-place. Report still generated — fixed items marked `status: fixed` |
| `--design-system` | no | Path to `design-system/tokens.md`. If omitted: look for `{SPECS_DIR}/front/design-system/tokens.md`. If not found: skip token existence checks (flag Warning) |

---

## Audit scope

### 1. Code quality — `u-fe-standards §2.2`

| Rule ID | What to detect | Severity | Auto-fix |
|---|---|---|---|
| CQ-01 | `style=` or `style={{` in JSX | Medium | no — requires CSS class extraction |
| CQ-02 | `transition: all` | Medium | yes — replace with `transition: opacity 200ms ease` + comment `/* TODO: specify property */` |
| CQ-03 | `TODO` or `FIXME` without `(TC-XX)` reference | Medium | no — requires TC number |
| CQ-04 | `eslint-disable` without justification comment | Medium | no — requires context |
| CQ-05 | Commented-out code block (2+ consecutive commented lines) | Low | yes — remove block |
| CQ-06 | `dangerouslySetInnerHTML` without `DOMPurify.sanitize` | Critical | no — requires dev judgment |
| CQ-07 | User input interpolated in `href`, `src`, or event handler string | Critical | no — requires dev judgment |
| CQ-08 | Page/route component without `<ErrorBoundary>` wrapper | High | no — requires hierarchy context |
| CQ-09 | Page component imported eagerly (missing `React.lazy` + `Suspense`) | Medium | no — requires routing context |
| CQ-10 | `import *` from large library (lodash, date-fns, etc.) | Medium | yes — convert to named import if single usage is detectable |
| CQ-11 | Animation/transition without `@media (prefers-reduced-motion: no-preference)` | Medium | yes — wrap existing animation block |
| CQ-12 | `console.log` / `console.error` / `console.warn` in non-test file | Medium | yes — remove line |
| CQ-13 | Hardcoded color value (hex, rgb, hsl, oklch literal) not inside token definition | Medium | no — requires token mapping |
| CQ-14 | Hardcoded spacing or font-size literal (px, rem) not inside token definition | Medium | no — requires token mapping |
| CQ-15 | Component file longer than 300 lines | Medium | no — requires decomposition into subcomponents |
| CQ-16 | Dashboard widget without its own data fetch, skeleton, or `ErrorBoundary` (single request hydrating the whole dashboard) | Medium | no — requires data/boundary restructuring |
| CQ-17 | Array index used as React `key` in a dynamic list | Medium | no — requires a stable unique id from the data |

### 2. Design system compliance

| Rule ID | What to detect | Severity | Auto-fix |
|---|---|---|---|
| DS-01 | CSS property value not using `var(--*)` for color, spacing, or typography | Medium | no — token name unknown without design-system |
| DS-02 | Token name used in code does not exist in `design-system/tokens.md` | Medium | no — flag Warning for Spec Team |
| DS-03 | New token defined locally inside component file | Medium | no — must be escalated to design system |

> If `--design-system` path is not resolvable: skip DS-02 and flag:
> `Warning: design-system/tokens.md not found — DS-02 checks skipped`

### 3. Visual design rules — `u-fe-standards §3`

#### 3.1 Typography
| Rule ID | Detection | Threshold | Severity | Auto-fix |
|---|---|---|---|---|
| VD-01 | `line-height` < 1.3 on multi-line text element | < 1.3 | Medium | yes — set to `1.5` |
| VD-02 | `font-size` < 12px on content element | < 12px | Medium | yes — set to `0.75rem` |
| VD-03 | `text-transform: uppercase` on element likely to exceed 20 chars | > 20 chars of static text | Medium | no — requires content knowledge |
| VD-04 | `letter-spacing` > 0.05em on body/paragraph element | > 0.05em | Medium | yes — set to `0.02em` |
| VD-05 | Heading level skips (h1 → h3 with no h2 in JSX) | any skip | Medium | no — requires structural context |
| VD-06 | `text-align: justify` without `hyphens: auto` | — | Medium | yes — add `hyphens: auto` |

#### 3.2 Color
| Rule ID | Detection | Threshold | Severity | Auto-fix |
|---|---|---|---|---|
| VD-07 | Neutral gray text (HSL saturation < 10%) on non-neutral background | sat < 10% | Medium | no — requires design intent |
| VD-08 | `background-color: #000` or `rgb(0,0,0)` or `oklch(0% 0 0)` on large surface | pure black | Medium | no — requires brand token |
| VD-09 | `background-clip: text` combined with any gradient | any combination | Medium | no — absolute ban, requires redesign |

#### 3.3 Layout
| Rule ID | Detection | Threshold | Severity | Auto-fix |
|---|---|---|---|---|
| VD-10 | `<p>`, `<li>`, `<article>` body text with no `max-width` constraint | > 75ch rendered | Medium | yes — add `max-width: 70ch` |
| VD-11 | Bordered or colored container with padding < 8px | < 8px | Medium | yes — set to `padding: 0.5rem` |

#### 3.4 Motion
| Rule ID | Detection | Threshold | Severity | Auto-fix |
|---|---|---|---|---|
| VD-12 | `transition` or `animation` targeting `width`, `height`, `padding`, or `margin` | any | Medium | no — requires grid-template-rows pattern |
| VD-13 | `cubic-bezier` with y1 or y2 outside `[0, 1]` | y ∉ [0,1] | Medium | yes — clamp control points to `[0, 1]` |

#### 3.5 CSS patterns (absolute bans)
| Rule ID | Detection | Threshold | Severity | Auto-fix |
|---|---|---|---|---|
| VD-14 | `border-left` or `border-right` ≥ 3px with non-neutral color on card/container | ≥ 3px non-neutral | **High** (absolute ban) | no — requires redesign |
| VD-15 | `border-left` or `border-right` ≥ 1px with non-neutral color + any `border-radius` | ≥ 1px + radius | **High** (absolute ban) | no — requires redesign |
| VD-16 | `border-top` or `border-bottom` ≥ 2px with non-neutral color on element with `border-radius` > 8px | ≥ 2px + radius > 8px | Medium | no — requires redesign |

### 4. Anti-patterns — `u-ui-design/anti-patterns.md`

Run the full 25-rule registry. For each rule, apply the detection threshold from `anti-patterns.md` exactly — do not redefine thresholds here.

```yaml
anti_patterns_source: ".claude/skills/u-ui-design/anti-patterns.md"
apply_all: true
absolute_bans: [gradient-text, side-tab]   # block — must be flagged as High
slop_category: warn                         # flag as Medium
```

### 5. Accessibility — `u-fe-standards §4`

| Rule ID | What to detect | Severity | Auto-fix |
|---|---|---|---|
| A11-01 | `<img>` without `alt` attribute | High | yes — add `alt=""` (decorative) + comment |
| A11-02 | `<input>` without associated `<label>` or `aria-label` | High | no — label text unknown |
| A11-03 | Interactive element with `outline: none` or `outline: 0` without replacement focus style | High | no — requires focus style design |
| A11-04 | Dynamic content region without `aria-live` or focus management | Medium | no — requires behavioral context |
| A11-05 | `role="button"` on a `<button>` element (redundant) | Low | yes — remove redundant role |
| A11-06 | Color used as sole conveyor of state (error class with no icon or text) | Medium | no — requires content change |
| A11-07 | Touch target smaller than 44×44px (inline `width`/`height` < 44px on interactive element) | Medium | yes — set min-width/min-height to 2.75rem |
| A11-08 | `<input>`/`<select>`/`<textarea>` in an error state without `aria-invalid` (WCAG 2.2 AA) | Medium | no — requires error-state wiring |

---

## Dependencies

Resolve before executing any audit step. Halt on missing required dependency.

```yaml
dependencies:
  required:
    - skill: u-fe-standards
      path: .claude/skills/u-fe-standards/SKILL.md
      used_in: [CQ-01..CQ-17, VD-01..VD-16, A11-01..A11-08]
      on_missing:
        status: error
        reason: dependency_not_found
        dependency: u-fe-standards

    - artifact: u-ui-design/anti-patterns.md
      path: .claude/skills/u-ui-design/anti-patterns.md
      used_in: [AP-01..AP-25]
      on_missing:
        status: error
        reason: dependency_not_found
        dependency: u-ui-design/anti-patterns.md

  optional:
    - artifact: design-system/tokens.md
      resolve_order:
        - arg: --design-system
        - path: "{SPECS_DIR}/front/design-system/tokens.md"
      on_missing:
        action: set ds_available=false
        skip_rules: [DS-02]
        emit: "Warning: design-system/tokens.md not found — DS-02 checks skipped"
```

---

## Execution process

```
Step 0 — Resolve dependencies
  - Read .claude/skills/u-fe-standards/SKILL.md — halt if not found
  - Read .claude/skills/u-ui-design/anti-patterns.md — halt if not found
  - Attempt design-system/tokens.md resolution (see ## Dependencies)

Step 1 — Resolve target
  - If file: add to scan list
  - If directory: glob *.tsx, *.ts, *.jsx, *.js, *.css, *.scss recursively
  - Skip: node_modules/, dist/, build/, *.test.*, *.spec.*

Step 2 — Resolve design system
  - If --design-system provided: read tokens.md
  - Else: attempt {SPECS_DIR}/front/design-system/tokens.md
  - If not found: set ds_available = false, skip DS-02

Step 3 — Audit each file
  For each file in scan list:
    - Read file content
    - Run all rules in §1–§5 above
    - Collect findings: {rule_id, file, line, excerpt, severity, auto_fixable}

Step 4 — If --fix: apply auto-fixes
  For each finding where auto_fixable = true:
    - Apply transformation (see Auto-fix column above)
    - Mark finding status: fixed
    - Log change: {rule_id, file, line, before, after}

Step 5 — Generate report (always)
```

---

## Output format

```yaml
# review-gate
target: "<path>"
timestamp: "<YYYY-MM-DDTHH:MM:SSZ>"
fix_mode: true | false
design_system_available: true | false
files_scanned: <int>
findings_total: <int>
findings_by_severity:
  critical: <int>
  high: <int>
  medium: <int>
  low: <int>
auto_fixed: <int>        # 0 when fix_mode: false
ready_for_review: true   # always true — this block is informational only
```

Followed by the Markdown report:

```markdown
# Frontend Review — <target>

> Scanned: <N> files | Findings: <N> | Auto-fixed: <N> | Date: YYYY-MM-DD

---

## Critical findings

| # | Rule | File | Line | Excerpt | Action |
|---|------|------|------|---------|--------|
| 1 | CQ-06 | Button.tsx | 42 | `dangerouslySetInnerHTML={{__html: userInput}}` | Add DOMPurify.sanitize |

## High findings
[same table]

## Medium findings
[same table]

## Low findings
[same table]

---

## Auto-fixes applied
[only when --fix]

| Rule | File | Line | Before | After |
|---|---|---|---|---|
| CQ-02 | Card.tsx | 18 | `transition: all 200ms` | `transition: opacity 200ms ease /* TODO: specify property */` |

---

## Warnings

- `Warning: design-system/tokens.md not found — DS-02 checks skipped`
- [other non-finding warnings]
```

---

## Auto-fix safety rules

```yaml
auto_fix_constraints:
  - never_modify_test_files: true          # *.test.*, *.spec.* excluded from --fix
  - never_modify_without_reading: true     # file must be read before any write
  - one_fix_per_rule_per_line: true        # do not apply multiple fixes to the same line
  - preserve_indentation: true
  - preserve_comments_above_line: true
  - do_not_fix_critical_bugs: true         # CQ-06, CQ-07 are flag-only regardless of --fix
  - do_not_fix_structural_issues: true     # CQ-08, CQ-09, VD-05 require hierarchy context
```

---

## Quality rules

| Condition | Action |
|---|---|
| `target` path does not exist | Halt — report `status: error / reason: target_not_found` |
| `target` is a binary or non-text file | Skip file — log in Warnings |
| Finding in a file that cannot be read | Skip file — log in Warnings |
| `--fix` applied but file is read-only | Skip fix for that file — log in Warnings |
| Critical finding detected | Always flag — never auto-fix |
| `design_system_available: false` | Run all rules except DS-02; flag Warning |
