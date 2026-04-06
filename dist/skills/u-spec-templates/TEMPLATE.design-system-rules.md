# Design System — Rules (compact summary)

> Generated from: `{SPECS_DIR}/front/design-system/`
> This file is the **minimum context** that every agent receives. For complete details, consult the files in the `design-system/` directory.

<!-- INSTRUCTION FOR THE FRONT SPEC AGENT:
     This file is generated automatically after creating/updating the design-system/ directory.
     It consolidates ONLY mandatory rules and existing tokens — no CSS snippets,
     no optional extensions, no detailed component tables.
     Keep under 150 lines. If it exceeds that, summarize more aggressively. -->

---

## Context

- **Color mode:** {dark-only | light-only | both}
- **Visual personality:** {short description}
- **Full details:** `design-system/_index.md`

---

## Available Tokens

### Colors

| Token | Intent |
|---|---|
| `--bg-primary` | Main background |
| `--bg-surface` | Content surface |
| `--bg-elevated` | Elevated surface |
| `--text-primary` | Highlighted text |
| `--text-body` | General text |
| `--text-muted` | Secondary text |
| `--primary-action` | Primary action |
| `--primary-action-hover` | Action hover |
| `--accent-data` | Data/metrics |
| `--accent-warning` | Warning |
| `--accent-danger` | Error/danger |

<!-- Add project-specific tokens here (glass, neon, sidebar, etc.) -->

### Spacing

| Token | Usage |
|---|---|
| `--space-1` | Micro (icon-label, badge) |
| `--space-2` | Small (inline gap) |
| `--space-3` | Base (button padding, form gap) |
| `--space-4` | Medium (card padding) |
| `--space-6` | Large (between sections) |
| `--space-8` | Extra (between blocks) |

### Typography

| Token | Usage |
|---|---|
| `--text-display` | Page title |
| `--text-heading` | Section title |
| `--text-subheading` | Subtitle |
| `--text-body-lg` | Main body |
| `--text-body-sm` | Secondary text |
| `--text-label` | Field label |
| `--text-caption` | Hint, timestamp |
| `--text-code` | Technical value |

<!-- If using triple typography: list families and their roles here -->

### Elevation

| Token | Usage |
|---|---|
| `--shadow-sm` | Base card |
| `--shadow-md` | Dropdown, tooltip |
| `--shadow-lg` | Modal, drawer |
| `--radius-sm` | Badge, small button |
| `--radius-md` | Card, input |
| `--radius-lg` | Modal, panel |

---

## Mandatory Rules

1. **`--accent-data` is not an action color** — never use on button, link, or trigger
2. **1 primary action per screen** — `--primary-action` on at most 1 dominant element
3. **Spacing from the scale** — only `--space-*` tokens, never arbitrary px
4. **Semantic typography** — Display for structure, Body for content, Mono for data
5. **`tabular-nums`** required in numeric columns and metrics
6. **`style={{}}` inline is forbidden** — except dynamic values with no equivalent
7. **`transition: all` is forbidden** — specify properties explicitly
8. **Animations** wrapped in `@media (prefers-reduced-motion: no-preference)`
9. **Tokens only from `design-system/`** — never invent, never hardcode hex/px

---

## Where to Find Details

| I need... | File |
|---|---|
| Hex values, font families, weights | `design-system/tokens.md` |
| Effects (glass, neon, spotlight), layout, density | `design-system/composition.md` |
| Component table (slots × states), do/don't | `design-system/components.md` |
| Accessibility, animations, QA checklist | `design-system/implementation.md` |
| Principles, visual context, changelog | `design-system/_index.md` |
