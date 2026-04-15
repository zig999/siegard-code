---
name: u-fe-validate
description: Standalone frontend validation skill. Applies u-fe-standards §2 (code quality) and §3 (visual design rules) against target files without requiring a Task Contract, delivery file, or test execution.
user-invocable: false
scope: frontend-only
---

# SKILL: Frontend Validate

## Purpose

Apply the full set of frontend quality rules from `u-fe-standards` against a target file or glob pattern, independent of any Task Contract or development session.

> **Scope: frontend only.** This skill validates TypeScript/TSX/CSS files against code quality and visual design rules.
> Backend architecture rules (DI, DTO, pagination) are out of scope — use `/u-be-validate` if that exists.

---

## Input contract

| Field | Required | Description |
|---|---|---|
| `TARGET` | yes | File path or glob pattern (e.g., `src/pages/dashboard.tsx`, `src/components/**/*.tsx`) |
| `SPECS_DIR` | no | Path to the project's `design-system/` directory. Required for token validation. If absent, token validation is skipped with a warning. |
| `RULES` | no | Subset of rules to apply. Values: `code_quality`, `visual_design`, or `all` (default: `all`) |

---

## Validation process

### Step 1 — Resolve target files

1. Expand `TARGET` (glob or direct path) into a list of matching files
2. Filter to: `.tsx`, `.ts`, `.jsx`, `.js`, `.css`, `.scss`, `.module.css`
3. If zero files match: return `status: failed`, `verdict: rejected`, with a single finding `rule: no-files-matched` (severity high)
4. Record `files_scanned` count

### Step 2 — Read design_system config from CLAUDE.md

Read `CLAUDE.md` and extract the `design_system` block. Apply canonical defaults for any absent field:

| Field | Default |
|---|---|
| `path` | `{specs_dir}/front/design-system/` |
| `token_prefix` | `"--color-"` |
| `color_mode` | `both` |
| `component_library` | `none` |
| `enforce_tokens` | `true` |
| `motion_policy` | `strict` |

**How config affects validation:**

| Field | Effect |
|---|---|
| `enforce_tokens: false` | Downgrade all `design-token` findings from `medium` to `low` |
| `motion_policy: permissive` | Skip `layout-animation` and `cubic-bezier-overshoot` rules; keep only `transition-all` rule |
| `path` | Resolves the path to `tokens.md` for token validation (used when `SPECS_DIR` is provided) |
| `token_prefix` | CSS custom property prefix used to identify design tokens (e.g. `"--color-"` matches `--color-primary`, `--color-surface`) |

> If `CLAUDE.md` is not present in the project root, apply all defaults and proceed.

### Step 3 — Load rules context

1. Read `u-fe-standards/SKILL.md` — §2 Code Quality Rules + §3 Visual Design Rules
2. If `SPECS_DIR` provided: read `{design_system.path}/tokens.md` to build the valid token list
3. If `SPECS_DIR` not provided: proceed without token validation; add warning to `findings`:
   ```yaml
   - id: FINDING-001
     rule_set: code_quality
     rule: specs-dir-missing
     file: <none>
     line: null
     severity: low
     description: "SPECS_DIR not provided — design token validation skipped."
     suggested_fix: "Pass SPECS_DIR to enable full token validation: /u-fe-validate [TARGET] [SPECS_DIR]"
   ```

### Step 4 — Apply code quality rules (u-fe-standards §2)

For each file in the target list, scan for violations of the rules below.
Each confirmed violation becomes one entry in `findings`.

#### §2.2 Code Standards

| Rule slug | What to detect | Severity |
|---|---|---|
| `design-token` | Hardcoded color, font, or spacing values (hex, rgb, rem literals outside token usage); invented or undefined `var(--*)` tokens | medium |
| `inline-css` | `style=""` or `style={{}}` in JSX/TSX | medium |
| `transition-all` | `transition: all` in CSS/inline styles | medium |
| `todo-no-ref` | `TODO` or `FIXME` without `(TC-XX)` reference | medium |
| `eslint-disable-no-reason` | `eslint-disable` without a justification comment on the same or preceding line | medium |
| `i18n-hardcode` | Hardcoded user-facing strings rendered in JSX (only when `i18n: true` is declared in `CLAUDE.md`) | medium |
| `commented-out-code` | Commented-out code blocks (multi-line or obvious disabled logic) | low |
| `xss-dangerous-html` | `dangerouslySetInnerHTML` without DOMPurify sanitization | critical |
| `xss-href-injection` | User input interpolated into `href`, `src`, or event handler strings | critical |
| `error-boundary-missing` | New page/route component not wrapped in `<ErrorBoundary>` with non-empty fallback | high |
| `no-code-splitting` | Page components imported eagerly (no `React.lazy` + `Suspense`) — applies only to route-level files | medium |
| `animation-no-reduced-motion` | CSS transitions or animations not wrapped in `@media (prefers-reduced-motion: no-preference)` | medium |

#### Token validation (requires SPECS_DIR)

| Rule slug | What to detect | Severity |
|---|---|---|
| `design-token` | `var(--token-name)` where token-name is NOT in `design-system/tokens.md` | medium |
| `design-token` | Hardcoded color/spacing/font values instead of `var(--token-name)` | medium |

---

### Step 5 — Apply visual design rules (u-fe-standards §3)

Scan `.css`, `.scss`, `.module.css`, and inline style blocks in `.tsx`/`.jsx` files.

#### §3.1 Typography

| Rule slug | What to detect | Severity |
|---|---|---|
| `line-height` | `line-height < 1.3` on elements expected to display ≥ 2 lines | medium |
| `font-size-small` | `font-size < 12px` on content elements | medium |
| `uppercase-body` | `text-transform: uppercase` on element with > 20 chars of text content | medium |
| `letter-spacing` | `letter-spacing > 0.05em` on body/paragraph elements | medium |
| `heading-skip` | Heading levels that skip (h1 → h3 with no h2 in DOM order) | medium |
| `justify-no-hyphens` | `text-align: justify` without `hyphens: auto` | medium |

#### §3.2 Color

| Rule slug | What to detect | Severity |
|---|---|---|
| `gray-on-color` | Neutral gray text (HSL saturation < 10%) on a non-neutral background | medium |
| `pure-black-bg` | `background-color: #000`, `rgb(0,0,0)`, or `oklch(0% 0 0)` on large surfaces | medium |
| `gradient-text` | `background-clip: text` combined with any gradient function | medium |

#### §3.3 Layout

| Rule slug | What to detect | Severity |
|---|---|---|
| `line-length` | `<p>`, `<li>`, `<article>` body text with no `max-width` and rendered width > 75ch | medium |
| `container-padding` | `padding < 8px` on bordered or colored containers with text content | medium |

#### §3.4 Motion

| Rule slug | What to detect | Severity |
|---|---|---|
| `layout-animation` | `transition` or `animation` targeting `width`, `height`, `padding`, or `margin` | medium |
| `cubic-bezier-overshoot` | `cubic-bezier` with y1 or y2 outside `[0, 1]` range | medium |

#### §3.5 CSS Patterns

| Rule slug | What to detect | Severity |
|---|---|---|
| `side-tab-border` | `border-left` or `border-right` ≥ 3px non-neutral color on card/container; or ≥ 1px when `border-radius` is set | medium |
| `rounded-accent-border` | `border-top` or `border-bottom` ≥ 2px non-neutral on element with `border-radius > 8px` | medium |

---

### Step 6 — Build and output the report

1. Assign sequential IDs: `FINDING-001`, `FINDING-002`, etc. (ordered by severity desc, then by file)
2. Compute `summary` counts
3. Determine `verdict`:
   - `approved` → `summary.total == 0`
   - `approved_with_caveats` → `summary.critical == 0 AND summary.high == 0 AND summary.total > 0`
   - `rejected` → `summary.critical > 0 OR summary.high > 0`
4. Set `status`:
   - `passed` → verdict is `approved` or `approved_with_caveats`
   - `failed` → verdict is `rejected`
5. Write output file using template `.claude/skills/u-shared-templates/fe-validate-report.yaml`
6. Output path: `{OUTPUT_DIR}/fe-validate-{run_id}.yaml`

---

## Output format

```yaml
# fe-validate-{run_id}.yaml
# Schema: .claude/skills/u-shared-templates/fe-validate-report.schema.yaml

meta:
  run_id: FV-20260414-143022
  target: src/pages/dashboard/**/*.tsx
  files_scanned: 4
  validated_by: u-fe-validate
  timestamp: 2026-04-14T14:30:22Z
  rules_applied: [code_quality, visual_design]
  specs_dir_used: docs/specs

status: failed

verdict: rejected

summary:
  total: 3
  critical: 1
  high: 0
  medium: 2
  low: 0

findings:
  - id: FINDING-001
    rule_set: code_quality
    rule: xss-dangerous-html
    file: src/pages/dashboard/components/widget.tsx
    line: 42
    severity: critical
    description: "dangerouslySetInnerHTML used without DOMPurify sanitization."
    suggested_fix: "Wrap content with DOMPurify.sanitize() and add // eslint-disable-next-line react/no-danger with justification comment."

  - id: FINDING-002
    rule_set: code_quality
    rule: design-token
    file: src/pages/dashboard/dashboard.module.css
    line: 17
    severity: medium
    description: "Hardcoded color value '#3b82f6' detected. Token var(--color-brand-primary) should be used."
    suggested_fix: "Replace '#3b82f6' with var(--color-brand-primary) from design-system/tokens.md."

  - id: FINDING-003
    rule_set: visual_design
    rule: side-tab-border
    file: src/pages/dashboard/components/card.module.css
    line: 8
    severity: medium
    description: "border-left: 4px solid var(--color-brand-primary) detected on card container with border-radius set."
    suggested_fix: "Replace side-tab border with full border, background tint, or remove the indicator."
```

---

## Behavioral rules

- Do not fix violations — only report them
- Do not invent rules not listed in this skill or in `u-fe-standards`
- Skip a rule silently if detecting it requires runtime execution (e.g., actual rendered width for line-length) — log as `low` warning instead
- If `SPECS_DIR` is provided but `design-system/tokens.md` does not exist: add a single `low` finding with `rule: tokens-file-missing`; continue validation without token checks
- Output the YAML report first, then present a human-readable summary
