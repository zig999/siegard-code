# Anti-Patterns

> Standalone rule registry for UI quality scanning.
> Consumed by: `u-ui-design` quality gate, `u-fe-standards` §3 validation, any agent auditing visual output.
> No external dependencies. Self-contained.

---

## Categories

| Category | Enforcement | Description |
|---|---|---|
| `quality` | blocking | Objective violations — accessibility, readability, or performance issues regardless of aesthetic intent |
| `slop` | warning | AI aesthetic tells — patterns that signal generated output; taste-sensitive, not correctness violations |

**Gate rule:** `quality` findings block delivery. `slop` findings are reported as warnings without blocking.

**Absolute bans:** rules marked `absolute` in the table below are blocking regardless of category.

---

## Rule Registry

### Typography

| id | category | name | detection_condition | threshold | absolute |
|---|---|---|---|---|---|
| `tight-leading` | quality | Tight line height | `line-height` < 1.3 × font-size on paragraph or body text | 1.3 | — |
| `tiny-text` | quality | Tiny body text | `font-size` < 12px on body, paragraph, or list content | 12px | — |
| `all-caps-body` | quality | All-caps body text | `text-transform: uppercase` on text block ≥ 20 characters | 20 chars | — |
| `wide-tracking` | quality | Wide letter spacing | `letter-spacing` > 0.05em on body text | 0.05em | — |
| `skipped-heading` | quality | Skipped heading level | `<h1>` followed by `<h3>` or higher without intermediate level | — | — |
| `justified-text` | quality | Justified text | `text-align: justify` without `hyphens: auto` | — | — |
| `overused-font` | slop | Overused font | Primary font is Inter, Roboto, Open Sans, Lato, Montserrat, or Arial | — | — |
| `single-font` | slop | Single font for everything | Only one font-family used across all text roles (display + body + label) | — | — |
| `flat-type-hierarchy` | slop | Flat type hierarchy | Ratio between adjacent heading sizes < 1.25 | 1.25 | — |
| `icon-tile-stack` | slop | Icon tile above heading | Rounded-square icon container (40–100px) immediately above a heading element | 40–100px | — |

---

### Color & Contrast

| id | category | name | detection_condition | threshold | absolute |
|---|---|---|---|---|---|
| `low-contrast` | quality | Low contrast text | Contrast ratio below WCAG AA: < 4.5:1 for normal text, < 3:1 for large text (≥ 18px or ≥ 14px bold) | 4.5:1 / 3:1 | — |
| `pure-black-white` | quality | Pure black background | `background-color: #000000` or `oklch(0% 0 0)` on large surface (> 100px height) | — | — |
| `gray-on-color` | quality | Gray text on colored background | Text color HSL saturation < 10% on background with HSL saturation ≥ 20% — or OKLCH chroma < 0.01 on background chroma ≥ 0.05 | chroma 0.01 / 0.05 | — |
| `gradient-text` | slop | Gradient text | `background-clip: text` combined with any gradient function (`linear-gradient`, `radial-gradient`, `conic-gradient`) | — | **yes** |
| `ai-color-palette` | slop | AI color palette | Purple/violet (`hue 270–310`) or cyan-on-dark as primary accent or gradient | hue 270–310 | — |
| `dark-glow` | slop | Dark mode glowing accents | Colored `box-shadow` with non-neutral color on dark background (`L < 20%` in OKLCH) | L < 20% | — |

---

### Layout & Space

| id | category | name | detection_condition | threshold | absolute |
|---|---|---|---|---|---|
| `line-length` | quality | Line length too long | Text container without `max-width` where rendered line exceeds 80 characters | 80 chars | — |
| `cramped-padding` | quality | Cramped padding | Padding < 8px (vertical or horizontal) on bordered or colored container | 8px | — |
| `nested-cards` | slop | Nested cards | Card or panel element (`border`, `box-shadow`, or colored background) as direct child of another card | — | — |
| `monotonous-spacing` | slop | Monotonous spacing | Single spacing value accounts for > 60% of all spacing declarations on a page | 60% | — |
| `everything-centered` | slop | Everything centered | > 50% of text elements on a page have `text-align: center` | 50% | — |

---

### Visual Details

| id | category | name | detection_condition | threshold | absolute |
|---|---|---|---|---|---|
| `side-tab` | slop | Side-tab accent border | `border-left` or `border-right` ≥ 3px with non-neutral color on card or container — OR ≥ 1px with any `border-radius` | 3px / 1px+radius | **yes** |
| `border-accent-on-rounded` | slop | Accent border on rounded element | `border-top` or `border-bottom` ≥ 2px non-neutral color combined with `border-radius` > 8px | 2px + radius > 8px | — |

---

### Motion

| id | category | name | detection_condition | threshold | absolute |
|---|---|---|---|---|---|
| `layout-transition` | quality | Layout property animation | `transition` or `animation` targets `width`, `height`, `padding`, or `margin` | — | — |
| `transition-all` | quality | Transition all properties | `transition: all`, `transition-property: all`, or Tailwind class `transition-all` | — | — |
| `bounce-easing` | slop | Bounce or elastic easing | `cubic-bezier` with any y-control-point outside `[0, 1]` — or `animate-bounce` / `ease: bounce` / `ease: elastic` | y ∉ [0,1] | — |

---

### Architecture

| id | category | name | detection_condition | threshold | absolute |
|---|---|---|---|---|---|
| `reimplemented-primitive` | quality | Reimplemented DS primitive | UI markup hand-rolls a structure equivalent to a primitive available in the DS primitive layer (`components/ui/`: Card, Badge, Table, Form…) instead of composing it | — | — |

> Detection is semantic (review / QA level) — not statically automatable by a linter. Enforcement points: the Developer decision order (`u-fe-development`) and `u-fe-standards §2.2 Primitive reuse`; this id is for audit reporting.

---

## Absolute Enforcement Patterns

Rules marked `absolute` must be detected and rejected in **all** contexts. No design direction or intensity overrides them.

### `gradient-text`

```css
/* DETECT — any of these patterns triggers a violation */
background: linear-gradient(...);
background-clip: text;
-webkit-background-clip: text;
color: transparent;

/* Tailwind equivalent */
class="bg-clip-text text-transparent bg-gradient-*"

/* REWRITE directive */
/* Use solid color only. Remove background-clip: text and gradient. */
color: var(--color-content);
```

### `side-tab`

```css
/* DETECT — card or container with: */
border-left: Npx solid <non-neutral-color>;   /* N ≥ 3, or N ≥ 1 when border-radius is set */
border-right: Npx solid <non-neutral-color>;  /* same thresholds */

/* REWRITE directive — choose one: */
/* Option A: full border */
border: 1px solid var(--color-border);
/* Option B: background tint */
background-color: color-mix(in oklch, var(--color-action) 8%, var(--color-surface));
/* Option C: no indicator */
/* remove border-left/right entirely */

/* NEVER rewrite as: */
box-shadow: inset 4px 0 0 var(--color-action); /* inset box-shadow is not a valid substitute */
```

---

## Detection Thresholds — Quick Reference

| id | metric | flag when |
|---|---|---|
| `tight-leading` | line-height / font-size ratio | < 1.3 |
| `tiny-text` | font-size (body context) | < 12px |
| `all-caps-body` | text-transform + char count | uppercase + ≥ 20 chars |
| `wide-tracking` | letter-spacing | > 0.05em |
| `flat-type-hierarchy` | adjacent size ratio | < 1.25 |
| `icon-tile-stack` | icon container size + heading sibling | 40–100px container directly above heading |
| `low-contrast` | contrast ratio | < 4.5:1 (body) / < 3:1 (large text) |
| `pure-black-white` | background luminance | L = 0% in OKLCH on large surface |
| `gray-on-color` | text chroma vs bg chroma | text chroma < 0.01, bg chroma ≥ 0.05 |
| `gradient-text` | background-clip + gradient | any combination |
| `ai-color-palette` | primary hue | 270–310 (purple/violet) as dominant accent |
| `dark-glow` | background L + box-shadow color | bg L < 20% + non-neutral shadow |
| `line-length` | chars per line | > 80 |
| `cramped-padding` | padding inside bordered/colored container | < 8px vertical or horizontal |
| `nested-cards` | card inside card | any depth |
| `monotonous-spacing` | dominant spacing value share | > 60% of all spacing |
| `everything-centered` | centered text elements share | > 50% of page text elements |
| `side-tab` | side border width + color | ≥ 3px non-neutral, or ≥ 1px + border-radius |
| `border-accent-on-rounded` | top/bottom border + radius | ≥ 2px non-neutral + radius > 8px |
| `layout-transition` | animated properties | width / height / padding / margin |
| `transition-all` | transition property | `transition: all` or `transition-property: all` |
| `bounce-easing` | cubic-bezier control points | any y ∉ [0, 1] |
| `reimplemented-primitive` | equivalent primitive in `components/ui/` | hand-rolled markup duplicates an available primitive instead of composing it |
| `radius-single-side` | border sides active | border-radius on element with single-side border only |
| `reduced-motion-missing` | animation context | any animation outside `@media (prefers-reduced-motion: no-preference)` |

---

## Hard Constraints — Design Rules R1–R25

> Rules in this section are derived from the project's **Hard Constraint design rules**.
> All entries below are `category: quality` (blocking) unless marked `slop`.
> Cross-reference with the full spec in `design-system/components.md`, `tokens.md`, `composition.md`, and `implementation.md`.

---

### Spacing (R1)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `arbitrary-spacing` | quality | Arbitrary spacing value | `p-[Xpx]`, `gap-[Xpx]`, or `m-[Xpx]` with a non-token px value | — |
| `forbidden-spacing-class` | quality | Forbidden Tailwind spacing class | Classes `p-5`, `p-7`, `p-9`, `p-11` (map to 20/28/36/44px — outside 8pt grid) | — |

> **Allowed spacing:** 4, 8, 12, 16, 24, 32, 48, 64px only. Tailwind: `p-1`/`p-2`/`p-3`/`p-4`/`p-6`/`p-8`/`p-12`/`p-16`.

---

### Typography Additions (R4, R5, R6)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `forbidden-font-size` | quality | Font size outside 1.25× scale | Font size not in 12/14/16/20/24/30px scale (e.g. 13px, 15px, 18px, 22px) | — |
| `too-many-font-sizes` | quality | Too many font sizes per component | More than 3 distinct font sizes in a single component | — |
| `forbidden-leading` | quality | Forbidden line-height | `leading-none` or `leading-loose` in any UI context | — |
| `font-weight-on-body` | quality | Bold/medium weight on body text | `font-bold` (700) on running text or labels; `font-medium` (500) on running body text | — |

> **Line-height rules:** `leading-tight` (1.2) for 20px+ headings; `leading-relaxed` (1.6) for 14–16px body; `leading-snug` (1.4) for 12px caption.
> **Weight rules:** headings/labels → `font-medium` or `font-semibold`; body → `font-normal`; metrics/price → `font-bold`.

---

### Text Hierarchy (R7)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `hue-based-text-hierarchy` | quality | Different hues for text hierarchy | Different hue colors used to differentiate text hierarchy levels | — |
| `more-than-3-text-levels` | quality | More than 3 text levels | More than 3 distinct text hierarchy levels in a single component | — |

> **Text hierarchy must use opacity, not hue:** 100% (primary) / 60% (secondary) / 40% (tertiary/placeholder).

---

### Color (R9)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `accent-on-structural` | quality | Accent on structural element | Accent color (`bg-action`, `text-action`, `bg-data`) on headings, section backgrounds, decorative icons, or dividers | — |
| `too-many-accents` | quality | More than 2 accent colors | More than 2 distinct accent colors in a single component | — |
| `semantic-color-decorative` | quality | Semantic color used decoratively | Error/success/warning/info colors applied without semantic meaning | — |
| `color-only-state` | quality | State via color alone | Interactive state communicated through color change with no accompanying shape, text, or icon | **yes** |

---

### Media (R10)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `arbitrary-image-ratio` | quality | Image with arbitrary ratio | `width` and `height` set on image without a defined ratio (1:1, 4:3, 16:9, 1:1.618) | — |
| `image-distortion` | quality | Image without object-cover | Image element without `object-fit: cover` / Tailwind `object-cover` | — |

---

### Components — Touch Targets, Radius, Buttons, States, Inputs (R11, R13, R14, R15, R16)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `clickable-below-32px` | quality | Clickable element below 32px | Any clickable element with height below 32px in any context | **yes** |
| `touch-target-mobile` | quality | Touch target below 44px on mobile | Clickable element below `h-11` (44px) in mobile breakpoint context | — |
| `mixed-border-radius` | quality | Mixed border radius styles | Border radius styles from different levels mixed in the same project | — |
| `radius-single-side` | quality | Border radius on single-side border | `border-radius` applied on element with only one border side active (`border-left`, `border-top`, `border-right`, or `border-bottom` without full `border`) | — |
| `two-primary-buttons` | quality | Two Primary buttons in context | Two or more `bg-action` (Primary) buttons in the same form, dialog, or section | **yes** |
| `danger-as-default` | quality | Danger button as default action | Danger button (`bg-danger`/`border-danger`) used as the default form submission | — |
| `incomplete-states` | quality | Missing interactive state(s) | Interactive element missing any of: Default / Hover / Focus / Active / Disabled | — |
| `focus-ring-missing` | quality | No visible focus ring | No `box-shadow` or `outline` ring on interactive element | **yes** |
| `error-border-only` | quality | Error shown by border alone | Input error with colored border but no helper text | **yes** |
| `error-as-popup` | quality | Field error in popup | Field-level validation error shown in modal, toast, or alert instead of inline | — |

---

### Components — Table, Icons, Avatars (R17, R21, R22)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `table-density-mixed` | quality | Mixed table density | More than one row padding variant in the same table | — |
| `table-density-invalid` | quality | Invalid table row padding | Row padding outside `py-2`, `py-3`, `py-4` | — |
| `icon-size-inherited` | quality | Icon size inherited | Icon `width`/`height` not explicitly set — inherits from container `font-size` | — |
| `icon-above-24px-functional` | quality | Icon too large for functional use | Icon > 24px in functional (non-illustrative) context | — |
| `avatar-off-scale` | slop | Avatar off fixed scale | Avatar size outside 24/32/40/48/64/80px | — |

---

### Grid & Layout (R18)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `fixed-grid-columns` | quality | Fixed-column grid | `grid-template-columns` with fixed px values or explicit column count (e.g. `repeat(3, 300px)`) | — |
| `grid-gap-invalid` | quality | Invalid card grid gap | Card grid gap not equal to `gap-4` (16px) or `gap-6` (24px) | — |

---

### Feedback (R19, R20)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `no-loading-state` | quality | No loading state on async | Button or element triggers async operation with no loading indicator | **yes** |
| `fullscreen-spinner-partial` | quality | Full-screen spinner for partial op | Full-page overlay spinner used for a partial-page operation | — |
| `complex-skeleton-animation` | quality | Complex skeleton animation | Skeleton uses shimmer, multi-color pulse, or any animation beyond opacity fade | — |
| `error-message-incomplete` | quality | Error message missing elements | Error message missing any of: status icon / title / description / action | — |
| `error-shows-technical` | quality | Technical info in error | Error message exposes error codes, stack traces, or internal details | **yes** |
| `error-too-vague` | quality | Error message too vague | Only "Error" or "Something went wrong" with no additional context | — |

---

### Layers (R24)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `z-index-outside-scale` | quality | Z-index outside fixed scale | z-index value outside 0/10/20/30/40/50 (e.g. `z-99`, `z-100`, `z-9999`) | — |
| `inline-z-index` | slop | Inline z-index | z-index set via `style={{ zIndex: N }}` without reference to the fixed layer scale | — |

---

### Empty States (R25)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `list-without-empty-state` | quality | List with no empty state | List, table, or grid component without a defined empty state | **yes** |
| `empty-state-error-toned` | quality | Error-toned empty state | Empty state uses error styling (red tones, alert icon) when state is simply empty | — |
| `empty-area-blank` | quality | Blank empty area | List/table/grid renders blank area, em dash, or `null` text when empty | **yes** |

---

### Motion Additions (R23)

| id | category | name | detection_condition | absolute |
|---|---|---|---|---|
| `animation-duration-forbidden` | quality | Forbidden animation duration | Duration outside 100/200/300/500ms scale (e.g. 150ms, 250ms, 350ms, 400ms) | — |
| `animation-above-500ms` | quality | Animation above 500ms | Any functional transition above 500ms (skeleton loops exempt) | — |
| `animation-3-properties` | quality | Too many animated properties | More than 2 CSS properties animated simultaneously on the same element | — |
| `reduced-motion-missing` | quality | Animation without reduced-motion guard | `transition` or `animation` declaration outside `@media (prefers-reduced-motion: no-preference)` block | — |

---

## Audit Output Schema

Produced when `u-ui-design` is invoked with the `audit` argument, or by any agent running a standalone audit pass.

```yaml
# Single finding
finding:
  id: "{rule-id}"                        # from registry above
  category: quality | slop
  name: "{rule name}"
  element: "{css selector or component}" # most specific selector available
  snippet: "{offending value or pattern}"
  severity: blocking | warning           # quality = blocking, slop = warning; absolute = blocking regardless

# Full audit report
output:
  type: audit_report
  target: "{file, component, or route}"
  produced_by: u-ui-design | {agent-id}
  scan_date: "{ISO 8601}"
  summary:
    total: {n}
    blocking_count: {n}
    warning_count: {n}
    pass: true | false                   # true only when blocking_count == 0
  findings:
    - id: "{rule-id}"
      category: quality | slop
      name: "{rule name}"
      element: "{selector}"
      snippet: "{offending value}"
      severity: blocking | warning
```

**Pass condition:** `blocking_count == 0`. `warning_count > 0` does not prevent delivery — include warnings in report.
