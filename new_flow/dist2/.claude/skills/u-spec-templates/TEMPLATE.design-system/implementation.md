# Design System — Implementation

> Part of: `{SPECS_DIR}/front/design-system/` | Layer: permanent
> Index: [`_index.md`](./_index.md)

---

## 13. Animations and Micro-interactions

<!-- INSTRUCTION: Define the animation pattern per interaction type. Be specific: which CSS properties animate, what duration, what easing. Do not use "transition: all". -->

| Element | Duration | Easing | Animated Properties |
|---|---|---|---|
| Buttons (hover/active) | `duration-instant` (100ms) | `ease-in-out` | background-color, box-shadow |
| Inputs (focus) | `duration-instant` (100ms) | `ease-in-out` | border-color, box-shadow |
| Modals (entry) | `duration-moderate` (300ms) | `ease-out` | opacity, transform (scale) |
| Modals (exit) | 225ms (~75% of 300ms) | `ease-in` | opacity, transform (scale) |
| Toasts (entry) | `duration-fast` (200ms) | `ease-out` | opacity, transform (translateY) |
| Dropdowns / tooltips (entry) | `duration-fast` (200ms) | `ease-out` | opacity, transform |
| Sidebars / drawers (open) | `duration-moderate` (300ms) | `ease-out` | transform (translateX) |
| Page transitions (entry) | `duration-entrance` (500ms) | `ease-out` | opacity, transform |
| Skeletons (pulse) | 1500ms | ease-in-out | opacity (loop — continuous, exempt from 500ms cap) |
| Exit (any element) | ~75% of paired enter duration | `--ease-in` | same properties as enter, reversed |
| Staggered list items | enter duration + `calc(var(--i, 0) * 50ms)` delay | `--ease-out` | opacity, transform |

> **Stagger cap:** max 10 items × 50ms = 500ms total. For longer lists, reduce per-item delay or cap staggered count.

> All animations must be wrapped in `@media (prefers-reduced-motion: no-preference)`.

<!-- OPTIONAL EXTENSION — Component-specific animations: projects with charts, real-time data, or elaborate page transitions may add:
     Page entry: opacity 0->1 + translateY(8px)->0, 200ms ease-out.
     Area/line chart: stroke-dashoffset, 600ms ease-out.
     Bar chart: scaleY 0->1 with 40ms stagger between bars, 400ms ease-out.
     Live status (flickering): keyframes neon-flicker, minimum duration 4s, max 2 simultaneous elements. -->

---

## 14. Accessibility

<!-- INSTRUCTION: Document the token pairs that ensure sufficient contrast. Verify WCAG AA ratios (4.5:1 for normal text, 3:1 for large text and UI). -->

| Combination | Estimated Ratio | WCAG Level | Usage |
|---|---|---|---|
| `text-content` on `bg-primary` | >= 4.5:1 | AA | Main interface text |
| `text-body` on `bg-surface` | >= 4.5:1 | AA | General content |
| `text-muted` on `bg-surface` | >= 3:1 | AA (UI) | Metadata, placeholders |
| `text-action` on `bg-primary` | >= 3:1 | AA (UI) | Action elements |

> **Glassmorphism and contrast:** if the project uses surfaces with `backdrop-filter`, effective text contrast is reduced. Always use `text-content` (never `text-body` or `text-muted`) on glass elements.

**WCAG AA requirements (R8):**
- Normal text (below 18px): minimum contrast ratio **4.5:1** against background
- Large text (18px+ or 14px+ bold): minimum contrast ratio **3:1**
- Interactive UI elements (input border, active icon): minimum ratio **3:1**

**Forbidden:**
- Light gray text on white background without verifying the contrast ratio
- Communicating state or information through color alone — always combine color with shape or text

---

## 15. Visual QA Checklist — Hard Constraints

<!-- INSTRUCTION: Use during PR review and visual QA. Mark as completed only when verified in the actual implementation, not in the spec. -->

**Spacing (R1)**
- [ ] No spacing values outside the 8pt scale (4/8/12/16/24/32/48/64px)
- [ ] No forbidden Tailwind classes: `p-5`, `p-7`, `p-9`, `p-11`
- [ ] No arbitrary spacing values such as `p-[13px]` or `gap-[7px]`

**Forms and Cards (R2, R3)**
- [ ] Form element gaps follow the spec: label→input `gap-1.5`, input→helper `gap-1`, field→field `gap-4`, group→group `gap-8`, last field→submit `gap-6`
- [ ] Card padding matches the card size variant: compact `p-2`, small `p-3`, medium `p-4`, large `p-6`, extra-large `p-8`
- [ ] No same padding on cards of very different sizes

**Typography (R4, R5, R6)**
- [ ] All font sizes are within the 1.25× scale: 12/14/16/20/24/30px only
- [ ] No more than 3 distinct font sizes per component
- [ ] Line-height matches context: headings `leading-tight`, body `leading-relaxed`, caption `leading-snug`
- [ ] No `leading-none` or `leading-loose` anywhere
- [ ] Font weight matches role: headings/labels `font-medium`/`font-semibold`, body `font-normal`, metrics `font-bold`
- [ ] No `font-bold` on running text or labels; no `font-medium` on running body

**Text Hierarchy (R7)**
- [ ] Text hierarchy uses opacity levels (100%/60%/40%), not different hue colors
- [ ] No more than 3 text hierarchy levels per component

**Contrast (R8)**
- [ ] All text combinations meet WCAG AA: 4.5:1 normal text, 3:1 large text and interactive elements
- [ ] No light gray text on white background without verification
- [ ] No state communicated through color alone

**Colors (R9)**
- [ ] Accent color not applied to headings, section backgrounds, decorative icons, or dividers
- [ ] No more than 2 accent colors per component
- [ ] Semantic colors (error/success/warning/info) used only for their semantic meaning

**Media (R10)**
- [ ] All images use a defined ratio: 1:1 / 4:3 / 16:9 / 1:1.618
- [ ] All images have `object-cover`

**Touch Targets (R11)**
- [ ] No clickable element below 32px height in any context
- [ ] Mobile interactive elements at `h-11` (44px) minimum

**Alignment (R12)**
- [ ] Every element shares a visual axis with at least one other element
- [ ] Icons + text use `items-center gap-2` (base) or `gap-1.5` (small text)
- [ ] Form labels are `text-left`

**Border Radius (R13)**
- [ ] One border radius style used consistently throughout the project
- [ ] No mixing of Rounded/Neutral/Sharp styles

**Buttons (R14)**
- [ ] Is the primary action clear and unique per screen?
- [ ] No two Primary buttons in the same context
- [ ] Danger button not used as default form action

**Component States (R15)**
- [ ] All interactive elements implement all 5 states: Default/Hover/Focus/Active/Disabled
- [ ] Focus ring visible on all interactive elements (3px accent ring)

**Input Validation (R16)**
- [ ] Error and success states include helper text — not border color alone
- [ ] Validation errors are inline, not in popups or alerts

**Table Density (R17)**
- [ ] Single density variant per table (`py-2` / `py-3` / `py-4`)
- [ ] Table headers use `text-xs font-medium uppercase tracking-[0.06em] text-muted`

**Card Grid (R18)**
- [ ] Card grids use `repeat(auto-fill, minmax(Xpx, 1fr))` — no fixed column counts
- [ ] Card grid gaps are `gap-4` or `gap-6` only

**Loading Feedback (R19)**
- [ ] Async operations have inline loading state on the triggering element
- [ ] No full-screen spinners for partial operations
- [ ] Skeletons use simple opacity animation only

**Error Messages (R20)**
- [ ] All error messages have: status icon + title + description + action
- [ ] No error codes, stack traces, or technical info exposed to users
- [ ] No error messages that are only "Error" or "Something went wrong"

**Icons (R21)**
- [ ] Icons use explicit `width`/`height`: 14/16/20/24px — never inherited
- [ ] No functional icons above 24px

**Avatars (R22)**
- [ ] Avatar sizes from the fixed scale: 24/32/40/48/64/80px only

**Animations (R23)**
- [ ] Animation durations from 100/200/300/500ms only — no 150/250/350/400ms
- [ ] No more than 2 properties animated simultaneously on the same element
- [ ] No functional transitions above 500ms
- [ ] All animations wrapped in `@media (prefers-reduced-motion: no-preference)`
- [ ] No `transition: all`

**Z-Index (R24)**
- [ ] All z-index values from: `z-0` / `z-10` / `z-20` / `z-30` / `z-40` / `z-50`
- [ ] No inline `style={{ zIndex: N }}`

**Empty States (R25)**
- [ ] Every list, table, and grid has a defined empty state
- [ ] Empty states contain: icon (40–48px, tertiary) + title + description + action
- [ ] Empty state icon is `text-muted`, never accent color

**General**
- [ ] Is `bg-data` / `text-data` being improperly used as an action color?
- [ ] Are the visual density limits (composition.md §11) being respected?
- [ ] Is the grid organized per layout patterns (composition.md §10)?
- [ ] Are there components using tokens outside their declared semantics?
- [ ] Is there `style=""` / `style={{}}` inline without dynamic value justification?

<!-- OPTIONAL EXTENSION — Additional checks for projects with visual effects: neon active limit per viewport respected? simultaneous backdrop-filter limit respected? grain texture duplicated in child elements (forbidden)? -->

---

<!-- OPTIONAL EXTENSION — Team guidelines: projects with larger teams may add a guidelines section by role (Design / Frontend / Product), with "Do" and "Don't" lists for each. -->

## 17. Loading Feedback

> **Mandatory (R19).** Every async operation must provide time-appropriate visual feedback. `no-loading-state` is an absolute-ban anti-pattern.

| Duration | Feedback | Implementation |
|---|---|---|
| 0–100ms | No feedback needed | — |
| 100ms–1s | Inline spinner on the triggering element | Spinner replaces or overlays the button/element that initiated the action |
| 1s+ | Skeleton screen replacing the loading content | Skeleton with same dimensions as real content |

**Skeleton specification:**
- Same dimensions as the real content it replaces
- Matching border-radius from the project's defined style
- Color: `bg-surface` with reduced opacity, `border-border` as pulse base
- Animation: simple opacity fade — `opacity-50 → opacity-100` loop — nothing else

**Forbidden:**
- Full-screen overlay spinner for a partial page operation
- Button or trigger without a loading state during an async operation
- Shimmer, multi-color pulse, or any skeleton animation beyond opacity fade

---

## 18. Error Messages — 4 Mandatory Elements

> **Mandatory (R20).** Every error message must contain all 4 elements in this exact order. Missing any element is a blocking anti-pattern (`error-message-incomplete`).

| Position | Element | Specification |
|---|---|---|
| 1 | Status icon | 16px (`w-4 h-4`), semantic color matching the error type (`text-danger` for errors) |
| 2 | Title | What happened — short phrase, no technical jargon, no trailing period |
| 3 | Description | Why it happened — one sentence, user-facing language |
| 4 | Action | What to do next — link or button (e.g., "Try again", "Go back") |

**Positioning:** always inline, close to the element that caused the error.

**Forbidden:**
- Displaying error codes, stack traces, or internal technical messages to the user
- Using only "Error" or "Something went wrong" without specific context
- Positioning error messages in a disconnected modal or toast when an inline location exists
- Error messages missing any of the 4 elements

---

## 16. Tailwind v4 Configuration

> **Mandatory** when `design_system.tailwind_integration: theme` in `CLAUDE.md`.
> File: `src/styles/global.css` (or project equivalent entry CSS).
> Constraint: `tailwind.config.ts` must NOT exist. All configuration lives in CSS.

```css
@import "tailwindcss";

@theme {
  /* Colors — each token generates bg-*, text-*, border-*, ring-* utilities */
  --color-primary:        oklch({L%} {C} {H});
  --color-surface:        oklch({L%} {C} {H});
  --color-elevated:       oklch({L%} {C} {H});
  --color-content:        oklch({L%} {C} {H});
  --color-body:           oklch({L%} {C} {H});
  --color-muted:          oklch({L%} {C} {H});
  --color-action:         oklch({L%} {C} {H});
  --color-action-hover:   oklch({L%} {C} {H});
  --color-action-active:  oklch({L%} {C} {H});
  --color-data:           oklch({L%} {C} {H});
  --color-warning:        oklch({L%} {C} {H});
  --color-danger:         oklch({L%} {C} {H});
  --color-border:         oklch({L%} {C} {H});
  --color-border-focus:   oklch({L%} {C} {H});
  --color-border-error:   oklch({L%} {C} {H});

  /* Spacing — generates p-*, m-*, gap-*, w-*, h-* utilities */
  --spacing-xs:  4px;
  --spacing-sm:  8px;
  --spacing-md:  12px;
  --spacing-lg:  16px;
  --spacing-xl:  24px;
  --spacing-2xl: 32px;

  /* Typography — generates text-* font-size utilities */
  --text-display:    {font-size};
  --text-heading:    {font-size};
  --text-subheading: {font-size};
  --text-body-lg:    {font-size};
  --text-body-sm:    {font-size};
  --text-label:      {font-size};
  --text-caption:    {font-size};
  --text-code:       {font-size};

  /* Elevation — generates shadow-* and rounded-* utilities */
  --shadow-sm: {value};
  --shadow-md: {value};
  --shadow-lg: {value};
  --radius-sm: {value};
  --radius-md: {value};
  --radius-lg: {value};

  /* Motion — generates duration-* and ease-* utilities */
  --duration-instant:   100ms;   /* hover, focus ring, toggle, checkbox, switch */
  --duration-fast:      200ms;   /* dropdown, tooltip, fade in/out, popover */
  --duration-moderate:  300ms;   /* modal, sidebar, drawer, bottom sheet */
  --duration-entrance:  500ms;   /* page transition, onboarding, screen entrance */

  --ease-out:       cubic-bezier(0.25, 1, 0.5, 1);
  --ease-in:        cubic-bezier(0.7, 0, 0.84, 0);
  --ease-in-out:    cubic-bezier(0.65, 0, 0.35, 1);
  --ease-out-quint: cubic-bezier(0.22, 1, 0.36, 1);
  --ease-out-expo:  cubic-bezier(0.16, 1, 0.3, 1);
}
```

**Constraints enforced by `u-fe-validate`:**
- `tailwind.config.ts` must not exist
- `style={{}}` is forbidden for any value covered by a token above
- Arbitrary values (`bg-[#fff]`, `p-[12px]`) are forbidden when a named token class exists
- All token values must match `tokens.md` — `@theme` block is generated from it, not authored independently
