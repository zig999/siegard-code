# Design System — Tokens

> Part of: `{SPECS_DIR}/front/design-system/` | Layer: permanent
> Index: [`_index.md`](./_index.md)

---

## Token Declarations

> Canonical source of truth for all agents. Two formats — keep both in sync.
> **CSS block**: implementation reference. Agents use Tailwind utility classes (`bg-surface`, `text-content`, `rounded-md`) exclusively.
> `var(--token-name)` is only allowed for dynamic inline values with no equivalent Tailwind utility.
> **YAML manifest**: machine-readable index for zero-ambiguity extraction by AI agents without CSS parsing.

> **Naming rule (Tailwind v4):** Token names follow the `--{category}-{semantic}` pattern where category maps to Tailwind utility prefixes:
> `--color-*` → `bg-*`, `text-*`, `border-*`, `ring-*` | `--spacing-*` → `p-*`, `m-*`, `gap-*` | `--radius-*` → `rounded-*` | `--shadow-*` → `shadow-*` | `--text-*` → `text-*` (font-size) | `--duration-*` → `duration-*` | `--ease-*` → `ease-*`
> Token name becomes the class suffix directly — name `--color-surface` → class `bg-surface`. Never use prefixes that duplicate the category (`--color-bg-surface` → `bg-bg-surface` ❌).

```css
/* Colors — OKLCH is the source of truth. Add hex comment for tooling reference.        */
/* Format: oklch({lightness%} {chroma} {hue})  — example: oklch(45% 0.15 250) ≈ #2855a0 */
/* Rules: chroma 0.005–0.01 for neutrals (tinted toward brand hue); reduce chroma above  */
/* 85% lightness; never use oklch(0% 0 0) or oklch(100% 0 0) for large surfaces.        */
/* Generated classes: --color-surface → bg-surface, text-surface, border-surface, etc.  */
--color-primary:        oklch({L%} {C} {H});  /* ≈ {#hex} — main application background */
--color-surface:        oklch({L%} {C} {H});  /* ≈ {#hex} — content surface over background */
--color-elevated:       oklch({L%} {C} {H});  /* ≈ {#hex} — elevated surface (dropdowns, modals) */
--color-content:        oklch({L%} {C} {H});  /* ≈ {#hex} — primary text (titles, labels) */
--color-body:           oklch({L%} {C} {H});  /* ≈ {#hex} — general content text */
--color-muted:          oklch({L%} {C} {H});  /* ≈ {#hex} — low-importance text (hints, metadata) */
--color-action:         oklch({L%} {C} {H});  /* ≈ {#hex} — primary action / CTA */
--color-action-hover:   oklch({L%} {C} {H});  /* ≈ {#hex} — action hover state */
--color-action-active:  oklch({L%} {C} {H});  /* ≈ {#hex} — action active / pressed state */
--color-data:           oklch({L%} {C} {H});  /* ≈ {#hex} — data / metrics highlight */
--color-warning:        oklch({L%} {C} {H});  /* ≈ {#hex} — warning / attention */
--color-danger:         oklch({L%} {C} {H});  /* ≈ {#hex} — error / destructive */
--color-border:         oklch({L%} {C} {H});  /* ≈ {#hex} — default border / separator */
--color-border-focus:   oklch({L%} {C} {H});  /* ≈ {#hex} — interactive / focus border */
--color-border-error:   oklch({L%} {C} {H});  /* ≈ {#hex} — validation error border */

/* Spacing — 4pt base scale. Generated classes: --spacing-xs → p-xs, m-xs, gap-xs, etc. */
--spacing-xs:  4px;    /* micro  — icon/label gap, badge padding */
--spacing-sm:  8px;    /* small  — inline element gap, tag padding */
--spacing-md:  12px;   /* base   — button padding, form field gap */
--spacing-lg:  16px;   /* medium — card padding, nearby sections */
--spacing-xl:  24px;   /* large  — section margins, container padding */
--spacing-2xl: 32px;   /* x-large — distinct content block separation */

/* Typography — font-size only. Weight and line-height set via Tailwind utilities.       */
/* Generated classes: --text-display → text-display, etc.                               */
--text-display:    {font-size};   /* main page titles, hero */
--text-heading:    {font-size};   /* section titles, card headers */
--text-subheading: {font-size};   /* subtitles, group labels */
--text-body-lg:    {font-size};   /* main body text, descriptions */
--text-body-sm:    {font-size};   /* secondary text, metadata */
--text-label:      {font-size};   /* field labels, table headers */
--text-caption:    {font-size};   /* hints, footers, timestamps */
--text-code:       {font-size};   /* technical values, snippets */

/* Elevation — Generated classes: --shadow-sm → shadow-sm, etc.; --radius-md → rounded-md */
--shadow-sm: {value};
--shadow-md: {value};
--shadow-lg: {value};
--radius-sm: {value};
--radius-md: {value};
--radius-lg: {value};
```

```yaml
# token-manifest — keep in sync with CSS block above
# Format: {category}.{token-suffix}: {value}
# Consumed by: UI Agent, Developer, Spec Validator (sync check)
color:
  primary:        "oklch({L%} {C} {H})"  # ≈ {#hex}
  surface:        "oklch({L%} {C} {H})"  # ≈ {#hex}
  elevated:       "oklch({L%} {C} {H})"  # ≈ {#hex}
  content:        "oklch({L%} {C} {H})"  # ≈ {#hex}
  body:           "oklch({L%} {C} {H})"  # ≈ {#hex}
  muted:          "oklch({L%} {C} {H})"  # ≈ {#hex}
  action:         "oklch({L%} {C} {H})"  # ≈ {#hex}
  action-hover:   "oklch({L%} {C} {H})"  # ≈ {#hex}
  action-active:  "oklch({L%} {C} {H})"  # ≈ {#hex}
  data:           "oklch({L%} {C} {H})"  # ≈ {#hex}
  warning:        "oklch({L%} {C} {H})"  # ≈ {#hex}
  danger:         "oklch({L%} {C} {H})"  # ≈ {#hex}
  border:         "oklch({L%} {C} {H})"  # ≈ {#hex}
  border-focus:   "oklch({L%} {C} {H})"  # ≈ {#hex}
  border-error:   "oklch({L%} {C} {H})"  # ≈ {#hex}
spacing:
  xs:  "4px"
  sm:  "8px"
  md:  "12px"
  lg:  "16px"
  xl:  "24px"
  2xl: "32px"
text:
  display:    "{font-size}"
  heading:    "{font-size}"
  subheading: "{font-size}"
  body-lg:    "{font-size}"
  body-sm:    "{font-size}"
  label:      "{font-size}"
  caption:    "{font-size}"
  code:       "{font-size}"
elevation:
  shadow-sm: "{value}"
  shadow-md: "{value}"
  shadow-lg: "{value}"
  radius-sm: "{value}"
  radius-md: "{value}"
  radius-lg: "{value}"
```

---

## 3. Color Tokens

### Semantic Tokens

| CSS Token | Tailwind Class | Usage Intent | Where to use | Where NOT to use |
|---|---|---|---|---|
| `--color-primary` | `bg-primary` | Main application background | Root layout, pages | Modals, tooltips, elevated cards |
| `--color-surface` | `bg-surface` | Content surface over the background | Cards, panels, sidebars | Page background |
| `--color-elevated` | `bg-elevated` | Elevated surface (higher prominence) | Dropdowns, modals, popovers | Page background, regular cards |
| `--color-content` | `text-content` | Highest-importance text | Titles, field labels, actions | Supporting text, placeholders |
| `--color-body` | `text-body` | General content text | Paragraphs, descriptions, values | Section titles |
| `--color-muted` | `text-muted` | Lowest-importance text | Placeholders, metadata, hints | Field labels, primary values |
| `--color-action` | `bg-action` / `text-action` | Primary action color | Primary buttons, action links | Backgrounds, content text |
| `--color-action-hover` | `bg-action-hover` | Primary action hover state | Primary button on hover | -- |
| `--color-action-active` | `bg-action-active` | Active/pressed state | Primary button on active | -- |
| `--color-data` | `text-data` / `bg-data` | Data/metrics highlight | Charts, status badges, KPIs | Actions, alerts |
| `--color-warning` | `text-warning` / `bg-warning` | Alert and attention | Warning messages, error borders | Positive actions, neutral data |
| `--color-danger` | `text-danger` / `bg-danger` | Error and danger | Error messages, delete confirmation | Warning alerts, neutral data |
| `--color-border` | `border-border` | Default separator / card border | Dividers, card borders | Focus states |
| `--color-border-focus` | `border-border-focus` | Interactive / focus border | Input on focus, selected elements | Default card borders |
| `--color-border-error` | `border-border-error` | Validation error border | Invalid field border | Warning alerts |

### Mandatory Semantics

| Token | Meaning | Can use in | Do not use in |
|---|---|---|---|
| `--color-action` | primary action | primary button, link, focus, contextual active item | KPI, positive data |
| `--color-data` | positive data / informational highlight | metrics, positive deltas, main series | primary action |
| `--color-warning` | attention | at-risk targets, warning | navigation action |
| `--color-danger` | error / risk | error, incident, decline | mild alerts |

> **Critical rule:** `--color-data` is not an action color. Never use `bg-data` on a button, link, or any element that triggers an operation.

### Text Hierarchy via Opacity (R7)

> **Mandatory.** Text hierarchy is created via opacity on the same base color — never via different hues.

| Level | Description | Light mode | Dark mode | Opacity |
|---|---|---|---|---|
| Primary | Titles, labels, active values | `text-content` (`text-gray-900`) | `text-white` | 100% |
| Secondary | Body text, descriptions | `text-body` (`text-gray-500`) | `text-gray-400` | ~60% |
| Tertiary / helper | Hints, metadata, timestamps | `text-muted` (`text-gray-400`) | `text-gray-500` | ~40% |
| Placeholder | Input placeholder text | `text-muted` | `text-gray-500` | ~40% |

**Forbidden:**
- Using different hue colors to create text hierarchy (e.g., blue for secondary, purple for tertiary)
- More than 3 text hierarchy levels per component

---

## 4. Spacing Tokens

| Token | Tailwind Class | Typical Usage |
|---|---|---|
| `--spacing-xs` | `p-xs`, `gap-xs`, `m-xs` | Micro — separation between icon and label, badge padding |
| `--spacing-sm` | `p-sm`, `gap-sm`, `m-sm` | Small — gap between inline elements, tag padding |
| `--spacing-md` | `p-md`, `gap-md`, `m-md` | Base — button padding, default gap between form fields |
| `--spacing-lg` | `p-lg`, `gap-lg`, `m-lg` | Medium — card padding, spacing between nearby sections |
| `--spacing-xl` | `p-xl`, `gap-xl`, `m-xl` | Large — margin between sections, container padding |
| `--spacing-2xl` | `p-2xl`, `gap-2xl`, `m-2xl` | Extra large — spacing between distinct content blocks |

> **Mandatory — 8pt grid (R1):** use only multiples of 4px: 4, 8, 12, 16, 24, 32, 48, 64px.
> **Forbidden values:** 5, 7, 9, 10, 13, 15, 17px — any odd or out-of-scale value.
> **Forbidden Tailwind classes:** `p-5`, `p-7`, `p-9`, `p-11` (map to 20/28/36/44px — outside 8pt grid).
> **Forbidden:** arbitrary values such as `p-[13px]` or `gap-[7px]`.

---

## 5. Typographic Scale

> **Mandatory — 1.25× Major Third ratio (R4):** required scale 12 → 14 → 16 → 20 → 24 → 30px.
> **Tailwind native classes:** `text-xs` (12px) · `text-sm` (14px) · `text-base` (16px) · `text-xl` (20px) · `text-2xl` (24px) · `text-3xl` (30px).
> **Forbidden sizes:** 13px, 15px, 17px, 18px, 22px — any size outside the 1.25× scale.
> **Component limit:** maximum 3 distinct font sizes per component — more = broken hierarchy.

| Token | Tailwind Class | px size | Native class | Default Color | Usage by level |
|---|---|---|---|---|---|
| `--text-display` | `text-display` | 30px | `text-3xl` | `text-content` | Hero, highlighted metric, price |
| `--text-heading` | `text-heading` | 24px | `text-2xl` | `text-content` | Page title, section title |
| `--text-subheading` | `text-subheading` | 20px | `text-xl` | `text-content` | Section subtitle, group label |
| `--text-body-lg` | `text-body-lg` | 16px | `text-base` | `text-body` | Primary body text, descriptions |
| `--text-body-sm` | `text-body-sm` | 14px | `text-sm` | `text-body` | Form labels, secondary body, placeholder |
| `--text-label` | `text-label` | 14px | `text-sm` | `text-content` | Field labels, table headers |
| `--text-caption` | `text-caption` | 12px | `text-xs` | `text-muted` | Helper text, caption, metadata, badge labels |
| `--text-code` | `text-code` | 14px | `text-sm` (mono) | `text-body` | Technical values, snippets |

---

## 5.1 Line-Height by Context

> **Mandatory (R5).** Apply based on the rendered font size, not the semantic role.

| Context | Font size | Tailwind class | Value | Rule |
|---|---|---|---|---|
| Headings | 20px+ (`text-xl`, `text-2xl`, `text-3xl`) | `leading-tight` | 1.2 | Tighter — titles are scanned, not read |
| Body | 14–16px (`text-sm`, `text-base`) | `leading-relaxed` | 1.6 | Looser — body is read linearly |
| Caption / helper | 12px (`text-xs`) | `leading-snug` | 1.4 | Compact but readable |

**Rule:** smaller font size → larger line-height.

**Forbidden:** `leading-none` or `leading-loose` in any UI context.

---

## 5.2 Font Weight by Role

> **Mandatory (R6).** Weight is determined by the element's semantic role, not aesthetic preference.

| Role | Weight | Tailwind | Applies to |
|---|---|---|---|
| Headings | `font-medium` (500) or `font-semibold` (600) | `font-medium` / `font-semibold` | Section titles, card headers, page titles |
| Form labels | `font-medium` (500) | `font-medium` | Field labels, group labels |
| Body text and values | `font-normal` (400) | `font-normal` | Paragraphs, descriptions, input values |
| Highlighted numbers | `font-bold` (700) | `font-bold` | Metrics, prices, KPI values |

**Forbidden:**
- `font-bold` (700) on running text or form labels
- `font-medium` (500) on running body paragraphs
- `font-light` (300) or below on any text smaller than 24px

---

## 6. Shadows and Borders

| Token | Tailwind Class | Usage Context |
|---|---|---|
| `--shadow-sm` | `shadow-sm` | Base-level cards, focused form fields |
| `--shadow-md` | `shadow-md` | Dropdowns, tooltips, floating elements |
| `--shadow-lg` | `shadow-lg` | Modals, side panels, drawers |
| `--radius-sm` | `rounded-sm` | Small buttons, badges, tags |
| `--radius-md` | `rounded-md` | Standard buttons, cards, inputs |
| `--radius-lg` | `rounded-lg` | Modals, panels, large containers |

---

## 7. Animation and Motion Tokens

> Animation tokens ensure consistent, accessible motion across the project.

```css
/* Motion — durations follow the 100/300/500 rule; exit = ~75% of enter */
/* Generated classes: --duration-instant → duration-instant, etc.       */
--duration-instant:   100ms;   /* hover, focus ring, toggle, checkbox, switch */
--duration-fast:      200ms;   /* dropdown, tooltip, fade in/out, popover */
--duration-moderate:  300ms;   /* modal, sidebar, drawer, bottom sheet */
--duration-entrance:  500ms;   /* page transition, onboarding, screen entrance */

/* Easing — use exponential curves; never linear, ease, bounce, or elastic */
/* Generated classes: --ease-out → ease-out, etc.                          */
--ease-out:          cubic-bezier(0.25, 1, 0.5, 1);   /* ease-out-quart  — elements entering (default) */
--ease-in:           cubic-bezier(0.7, 0, 0.84, 0);   /* ease-in-quart   — elements leaving */
--ease-in-out:       cubic-bezier(0.65, 0, 0.35, 1);  /* state toggles (enter → exit same element) */
--ease-out-quint:    cubic-bezier(0.22, 1, 0.36, 1);  /* more dramatic entrance */
--ease-out-expo:     cubic-bezier(0.16, 1, 0.3, 1);   /* snappy, high-impact entrance */
```

| Token | Tailwind Class | Value | Enter use case | Exit duration |
|---|---|---|---|---|
| `--duration-instant` | `duration-instant` | 100ms | Hover, focus ring, toggle, checkbox, switch | 75ms |
| `--duration-fast` | `duration-fast` | 200ms | Dropdown, tooltip, fade in/out, popover | 150ms |
| `--duration-moderate` | `duration-moderate` | 300ms | Modal, sidebar, drawer, bottom sheet | 225ms |
| `--duration-entrance` | `duration-entrance` | 500ms | Page transition, onboarding, screen entrance | 375ms |

**Mandatory rules (R23):**
- Every `transition` must reference a `duration-*` Tailwind class and an `ease-*` Tailwind class — never a bare `ms` value or `transition: all`
- Animate only `transform` and `opacity` — never `width`, `height`, `padding`, or `margin`
- For height transitions: use `grid-template-rows: 0fr → 1fr` instead of animating `height`
- Easing: `ease-out` for elements entering; `ease-in` for elements exiting; `ease-in-out` for hover/focus feedback
- **Forbidden durations:** 150ms, 250ms, 350ms, 400ms — any value outside 100/200/300/500ms
- **Maximum:** 2 CSS properties animated simultaneously on the same element
- **Maximum:** 500ms in functional UI flows (continuous skeleton loops are exempt)
- Bounce/elastic easing (`cubic-bezier` with y outside `[0, 1]`) is prohibited

**Accessibility rule:** all animations must be wrapped in `@media (prefers-reduced-motion: no-preference)`. The default (no `@media`) must produce no motion.

---

## 8. Semantic Usage Rules

- `--color-data` must never be used as an action color — it is exclusive to data visualization
- `--color-warning` indicates attention/warning; `--color-danger` indicates error/irreversible danger — do not interchange
- `--color-action` should appear on at most 1 element per screen as the primary action
- Text on dark backgrounds must use `text-content` or `text-body` — never highlight colors
- `border-border-focus` is exclusive to focus/selection states — do not use decoratively
- Spacing tokens must be used via Tailwind classes (`p-md`, `gap-lg`) — never arbitrary px values
- `style=""` / `style={{}}` inline is forbidden — except dynamic values with no equivalent in the style system
- Never use `transition: all` — specify animated properties explicitly
- Animations wrapped in `@media (prefers-reduced-motion: no-preference)`
