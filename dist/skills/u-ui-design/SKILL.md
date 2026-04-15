---
name: u-ui-design
description: UI design amplification and audit skill. Reads design-system/tokens.md and visual_personality to apply calibrated design rules. Does not create design systems from scratch. Invoke with "audit" argument to produce a findings report instead of modified code.
user-invocable: true
argument-hint: "[audit] [target]"
---

# SKILL: UI Design

## Prerequisites

| Condition | Action if missing |
|---|---|
| `design-system/_index.md` exists and contains `visual_personality` | `AskUserQuestion` → define `direction` and `intensity` → write to `_index.md §2` |
| `design-system/tokens.md` exists | `status: blocked` — create design system first using `TEMPLATE.design-system/` |
| `target` provided or inferible from context | `AskUserQuestion: which component or file to modify` |

```yaml
# blocked output
status: blocked
reason: design_system_not_found | missing_visual_personality | missing_target
required: "{SPECS_DIR}/front/design-system/_index.md"
action: create_design_system_first
reference: dist/skills/u-spec-templates/TEMPLATE.design-system/
```

---

## Absolute Bans

Apply in all executions. No context overrides these.

| id | Detect when | Rewrite directive |
|---|---|---|
| `side-tab` | `border-left` or `border-right` > 1px with non-neutral color on card/container | Full border, background tint, or no indicator — never replace with inset box-shadow |
| `gradient-text` | `background-clip: text` combined with any gradient function | Solid color only — no exceptions |

---

## Font Reject List

Apply when selecting or changing fonts (target involves typography or no font is defined in `tokens.md`).

Reject any font from this list regardless of brief: Fraunces, Newsreader, Lora, Crimson, Crimson Pro, Crimson Text, Playfair Display, Cormorant, Cormorant Garamond, Syne, IBM Plex Mono, IBM Plex Sans, IBM Plex Serif, Space Mono, Space Grotesk, Inter, DM Sans, DM Serif Display, DM Serif Text, Outfit, Plus Jakarta Sans, Instrument Sans, Instrument Serif.

Selection criteria: chosen font must NOT be in this list AND must NOT be the same font used in the last referenced project in context.

---

## Execution Protocol

1. Read `design-system/_index.md` → extract `visual_personality.direction` and `visual_personality.intensity`
2. Read `design-system/tokens.md` → load token names and current values
3. Read `target` → assess current state
4. Enforce absolute bans on current state — fix any violations before proceeding
5. Look up directional parameters from the **Directional Rules** table below
6. Apply directional parameters to the target — all values must reference `var(--token-name)`
7. Run quality gate (anti-patterns scan) on output
8. Deliver modified code + output schema

If argument is `audit`: skip steps 4–6, run full anti-patterns scan, deliver `audit_report`.

---

## Directional Rules

Look up `direction` × `intensity` to get the parameter set for this execution.

| direction | intensity | scale_ratio | weight_pair | hero_gap | grid | neutral_weight | effects |
|---|---|---|---|---|---|---|---|
| `bold` | 1 | 1.5x | 700/400 | 48–64px | defined patterns | 58% | dramatic-shadows |
| `bold` | 2 | 2x | 700/400 | 64–96px | defined patterns | 55% | dramatic-shadows |
| `bold` | 3 | 2.5x | 800/300 | 96–128px | slight asymmetry for hero | 55% | grain, texture |
| `bold` | 4 | 3x | 800/300 | 128–160px | asymmetric sections | 50% | grain, halftone |
| `bold` | 5 | 3–5x | 900/200 | 160–200px | break grid, diagonal, full-bleed | 50% | grain, halftone, overlap |
| `balanced` | 1 | 1.5x | 600/400 | 32–48px | defined patterns | 60% | standard shadows |
| `balanced` | 2–3 | 1.75–2x | 700/400 | 48–64px | defined patterns | 60% | standard shadows |
| `balanced` | 4–5 | 2x | 700/400 | 64px | defined patterns | 60% | standard shadows |
| `minimal` | 1 | 1.5x | 500/400 | 24–32px | strict grid | 65% | none |
| `minimal` | 2 | 1.4x | 500/400 | 24px | strict grid | 68% | none |
| `minimal` | 3 | 1.33x | 500/400 | 16–24px | strict grid | 70% | none |
| `minimal` | 4 | 1.25x | 400/300 | 16px | strict grid | 75% | none |
| `minimal` | 5 | 1.25x | 400/300 | 16px | strict grid | 80% | none |

### Parameter definitions

| Parameter | How to apply |
|---|---|
| `scale_ratio` | Adjacent heading levels must differ by at least this ratio — e.g., 2x means h2 ≤ 50% of h1 font-size |
| `weight_pair` | Display/headline font-weight / body font-weight — reference project font tokens |
| `hero_gap` | Spacing between major page sections — applies to marketing/content layouts; not app UI rows |
| `grid` | `defined patterns` = follow `composition.md §10`; `asymmetric/break` = hero elements may deviate |
| `neutral_weight` | % of visible surface area using neutral background tokens (`--bg-*`) |
| `effects` | Which visual effect techniques are permitted — all others are prohibited for this execution |

### Constraints (all directions, all intensities)

- All values must reference `var(--token-name)` from `tokens.md` — never hardcode
- `u-fe-standards §2` (code quality) and `§3` (visual design rules) always apply — directional rules never override them
- Absolute bans always apply regardless of direction or intensity

---

## Quality Gate

Run before delivering any code output. Load `anti-patterns.md`.

```yaml
quality_gate:
  scan: anti-patterns.md rules against output
  blocking: findings with category = quality
  warning:  findings with category = slop
  pass_condition: blocking_count == 0
```

If `blocking_count > 0`: fix violations and rescan before delivering.
If `warning_count > 0`: include warnings in output schema — do not block delivery.

---

## Output Schema

```yaml
# code modification output
output:
  type: code_modification
  target: "{file or component}"
  produced_by: u-ui-design
  visual_personality:
    direction: bold | minimal | balanced
    intensity: 1 | 2 | 3 | 4 | 5
  tokens_referenced: ["{var(--token-name)}", ...]
  quality_gate:
    pass: true | false
    blocking_count: 0
    warning_count: 0
  changes:
    - rule: "{rule or parameter applied}"
      element: "{css selector or component}"
      before: "{previous value}"
      after: "{new value}"

# audit output — argument: audit
output:
  type: audit_report
  # full schema defined in anti-patterns.md
```
