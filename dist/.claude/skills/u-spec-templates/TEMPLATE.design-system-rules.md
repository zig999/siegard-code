# Design System — Rules (compact summary)

> Generated from: `{SPECS_DIR}/front/design-system/` | Layer: permanent
> This file is the **minimum context** that every agent receives. For complete details, consult the files in the `design-system/` directory.

---

## Context

- **Color mode:** {dark-only | light-only | both}
- **Visual personality:** {short description}
- **Full details:** `design-system/_index.md`

---

## Available Tokens

> All tokens follow Tailwind v4 naming. Use Tailwind utility classes directly (`bg-surface`, `text-content`, `rounded-md`).
> `var(--token-name)` only for dynamic inline values with no equivalent Tailwind utility.

### Colors

| Token | Tailwind Class | Intent |
|---|---|---|
| `--color-primary` | `bg-primary` | Main background |
| `--color-surface` | `bg-surface` | Content surface |
| `--color-elevated` | `bg-elevated` | Elevated surface |
| `--color-content` | `text-content` | Primary / highlighted text |
| `--color-body` | `text-body` | General text |
| `--color-muted` | `text-muted` | Secondary / hint text |
| `--color-action` | `bg-action` / `text-action` | Primary action (CTA) |
| `--color-action-hover` | `bg-action-hover` | Action hover state |
| `--color-data` | `bg-data` / `text-data` | Data / metrics highlight |
| `--color-warning` | `bg-warning` / `text-warning` | Warning / attention |
| `--color-danger` | `bg-danger` / `text-danger` | Error / destructive |
| `--color-border` | `border-border` | Default border |
| `--color-border-focus` | `border-border-focus` | Focus / interactive border |
| `--color-border-error` | `border-border-error` | Validation error border |

### Spacing

| Token | Tailwind Class | Usage |
|---|---|---|
| `--spacing-xs` | `p-xs`, `gap-xs` | Micro (icon-label, badge) |
| `--spacing-sm` | `p-sm`, `gap-sm` | Small (inline gap) |
| `--spacing-md` | `p-md`, `gap-md` | Base (button padding, form gap) |
| `--spacing-lg` | `p-lg`, `gap-lg` | Medium (card padding) |
| `--spacing-xl` | `p-xl`, `gap-xl` | Large (between sections) |
| `--spacing-2xl` | `p-2xl`, `gap-2xl` | Extra (between blocks) |

### Typography

| Token | Tailwind Class | Usage |
|---|---|---|
| `--text-display` | `text-display` | Page title |
| `--text-heading` | `text-heading` | Section title |
| `--text-subheading` | `text-subheading` | Subtitle |
| `--text-body-lg` | `text-body-lg` | Main body |
| `--text-body-sm` | `text-body-sm` | Secondary text |
| `--text-label` | `text-label` | Field label |
| `--text-caption` | `text-caption` | Hint, timestamp |
| `--text-code` | `text-code` | Technical value |


### Elevation

| Token | Tailwind Class | Usage |
|---|---|---|
| `--shadow-sm` | `shadow-sm` | Base card |
| `--shadow-md` | `shadow-md` | Dropdown, tooltip |
| `--shadow-lg` | `shadow-lg` | Modal, drawer |
| `--radius-sm` | `rounded-sm` | Badge, small button |
| `--radius-md` | `rounded-md` | Card, input |
| `--radius-lg` | `rounded-lg` | Modal, panel |

---

## Mandatory Rules

1. **`bg-data` / `text-data` is not an action color** — never use on button, link, or trigger
2. **1 primary action per screen** — `bg-action` on at most 1 dominant element
3. **Spacing from the scale** — only `p-*`, `gap-*`, `m-*` from token set; never arbitrary px; never `p-5`, `p-7`, `p-9`, `p-11`
4. **Semantic typography** — Display for structure, Body for content, Mono for data
5. **`tabular-nums`** required in numeric columns and metrics
6. **`style={{}}` inline is forbidden** — except dynamic values with no equivalent Tailwind utility
7. **`transition: all` is forbidden** — specify properties explicitly
8. **Animations** wrapped in `@media (prefers-reduced-motion: no-preference)`
9. **Tokens only from `design-system/`** — never invent, never hardcode hex/px
10. **No `tailwind.config.ts`** — all tokens live in `@theme {}` in `global.css`
11. **Reuse before build** — compose existing primitives from `components/ui/` (Card, Badge, Table, Form…); never hand-roll markup that duplicates one (`reimplemented-primitive`)

---

## Hard Constraints — R1–R25 (enforced)

> Every rule below is a **blocking** constraint. Violations must be corrected before delivery.
> Full specification in each rule's source file. Anti-pattern IDs map to `u-ui-design/anti-patterns.md`.

| Rule | Constraint | Anti-pattern ID |
|---|---|---|
| R1 — Spacing | Allowed px: 4/8/12/16/24/32/48/64 only. Forbidden: `p-5`, `p-7`, `p-9`, `p-11`, arbitrary `p-[Xpx]` | `arbitrary-spacing`, `forbidden-spacing-class` |
| R2 — Form gaps | label→input `gap-1.5`; input→helper `gap-1`; field→field `gap-4`; group→group `gap-8`; last field→submit `gap-6` | — |
| R3 — Card padding | Compact `p-2` · Small `p-3` · Medium `p-4` · Large `p-6` · XL `p-8`. Never same padding on very different cards | — |
| R4 — Type scale | Sizes: 12/14/16/20/24/30px only. Max 3 sizes per component. Forbidden: 13/15/17/18/22px | `forbidden-font-size`, `too-many-font-sizes` |
| R5 — Line-height | Headings `leading-tight`; body `leading-relaxed`; caption `leading-snug`. Forbidden: `leading-none`, `leading-loose` | `forbidden-leading` |
| R6 — Font weight | Headings/labels `font-medium`/`font-semibold`; body `font-normal`; metrics `font-bold`. Forbidden: `font-bold` on labels | `font-weight-on-body` |
| R7 — Text hierarchy | Hierarchy via opacity only (100%/60%/40%). Forbidden: different hues per level. Max 3 levels per component | `hue-based-text-hierarchy` |
| R8 — Contrast | 4.5:1 normal text; 3:1 large/interactive. Forbidden: state via color alone | `color-only-state` |
| R9 — 60-30-10 | Accent only on CTAs. Forbidden: accent on headings, dividers, decorative icons. Max 2 accents per component. Required semantic: error=red · success=green · warning=yellow/amber · info=blue. Forbidden: semantic colors used decoratively | `accent-on-structural`, `semantic-color-decorative` |
| R10 — Aspect ratios | Images: 1:1 / 4:3 / 16:9 / 1:1.618 only. Always `object-cover` | `arbitrary-image-ratio`, `image-distortion` |
| R11 — Touch targets | Min `h-8` (32px) desktop; `h-11` (44px) mobile. Buttons: `px-4` small / `px-6` large | `clickable-below-32px` |
| R12 — Alignment | Every element shares axis with at least one other. Icon+text `items-center gap-2`. Labels `text-left` | — |
| R13 — Border radius | Pick ONE style and apply everywhere. **Rounded**: cards `rounded-xl`, inputs/buttons `rounded-lg`. **Neutral**: cards `rounded-lg`, inputs/buttons `rounded-md`. **Sharp**: cards `rounded-md`, inputs/buttons `rounded`. Forbidden: mixing styles; radius on single-side borders | `mixed-border-radius`, `radius-single-side` |
| R14 — Button hierarchy | Never 2 Primary buttons in same context. Danger only for irreversible destructive actions | `two-primary-buttons`, `danger-as-default` |
| R15 — 5 states | All interactive elements: Default/Hover/Focus/Active/Disabled. Focus ring mandatory (3px accent) | `incomplete-states`, `focus-ring-missing` |
| R16 — Input validation | Error/success always with helper text. Never border color alone. Never popup for field errors | `error-border-only`, `error-as-popup` |
| R17 — Table density | `py-2` compact / `py-3` default / `py-4` relaxed. One variant per table. Header: `text-xs font-medium uppercase` | `table-density-mixed`, `table-density-invalid` |
| R18 — Card grid | Always `repeat(auto-fill, minmax(Xpx, 1fr))`. Gap: `gap-4` or `gap-6` only. No fixed columns | `fixed-grid-columns`, `grid-gap-invalid` |
| R19 — Loading feedback | <100ms: nothing; 100ms–1s: inline spinner; 1s+: skeleton. No full-screen spinner for partial ops | `no-loading-state`, `fullscreen-spinner-partial` |
| R20 — Error messages | Always: icon (16px) + title + description + action. No codes/stack traces. No "Something went wrong" alone | `error-message-incomplete`, `error-shows-technical` |
| R21 — Icons | Sizes: 14/16/20/24px only. Always explicit `w-* h-*`. Max 24px functional | `icon-size-inherited`, `icon-above-24px-functional` |
| R22 — Avatars | Sizes: 24/32/40/48/64/80px only. Always 1:1. `rounded-full` or `rounded-lg` | `avatar-off-scale` |
| R23 — Animations | Durations: 100/200/300/500ms only. Max 2 properties. Max 500ms functional. `ease-out` enter / `ease-in` exit | `animation-duration-forbidden`, `animation-3-properties` |
| R24 — Z-index | Only: `z-0`/`z-10`/`z-20`/`z-30`/`z-40`/`z-50`. No `z-99`, `z-100`, `z-9999`. No inline style | `z-index-outside-scale` |
| R25 — Empty states | Every list/table/grid must have empty state: icon+title+description+action. Defined before implementation | `list-without-empty-state`, `empty-area-blank` |

---

## Where to Find Details

| I need... | File |
|---|---|
| OKLCH values, font families, @theme block | `design-system/tokens.md` |
| Spacing scale, typography rules, animation tokens | `design-system/tokens.md` |
| Effects (glass, neon, spotlight), layout, density, empty states, z-index | `design-system/composition.md` |
| Component catalog, form/card spacing, touch targets, button hierarchy, states | `design-system/components.md` |
| Accessibility, animations, loading feedback, error messages, QA checklist | `design-system/implementation.md` |
| Principles, visual context, changelog | `design-system/_index.md` |
| Anti-pattern IDs (audit enforcement) | `u-ui-design/anti-patterns.md` |
