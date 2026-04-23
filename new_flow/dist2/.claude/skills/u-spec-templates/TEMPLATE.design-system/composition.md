# Design System — Composition

> Part of: `{SPECS_DIR}/front/design-system/` | Layer: permanent
> Index: [`_index.md`](./_index.md)

---

## 7. Visual Effects

<!-- INSTRUCTION: This section is OPTIONAL. Fill only if the project uses systematic visual effects. For each effect: document when to use, when not to use, maximum per viewport, and the base CSS snippet. Leave this section empty (with only the comment) if the project does not use effects beyond standard shadows and borders. -->

<!-- OPTIONAL EXTENSION — Effects available for projects with advanced aesthetics (dark mode, HUD, fintech, analytics):

  (1) GLASSMORPHISM: translucent surfaces with backdrop-filter: blur that create hierarchy without weight.
      When to use: modals, sticky topbar, floating cards, overlays, tooltips over complex backgrounds.
      When NOT to use: over solid backgrounds without texture (effect imperceptible); as the default style for all cards (loses hierarchical impact); on elements smaller than 100px.
      Define: depth levels (e.g., blur 8px / 16px / 24px), background opacity per level, and maximum elements with simultaneous backdrop-filter per viewport.

  (2) NEON GLOW: multi-layer text-shadow with accent-data as base color, creates neon glow with depth.
      When to use: hero titles, real-time status labels (LIVE, ACTIVE), critical metric values, highlight card borders, active sidebar item.
      When NOT to use: on body text or paragraphs; on more than 3 elements simultaneously per viewport; without a dark background as base.

  (3) SPOTLIGHT HOVER (pure CSS): radial gradient revealed on hover via ::before, no JavaScript.
      When to use: feature cards in grids, interactive dashboard panels, list items with actions.
      When NOT to use: in tables with many rows; on elements with dense body text; without combining with border-color transition.
      Mandatory rules: pointer-events: none on ::before; overflow: hidden on parent element; position: relative; z-index: 1 on child elements; max gradient opacity 0.12-0.15; minimum transition of 0.35s.

  (4) GRAIN TEXTURE: SVG noise layer in body::after as a fixed global layer.
      When to use: always — single instance, applied globally.
      When NOT to use: never duplicate on child elements; never increase opacity above 0.04.

  For each incorporated effect: define the usage hierarchy table (which components use which effect and whether it is mandatory, optional, or forbidden). -->

---

## 8. Z-Index — Fixed Layer Scale

> **Mandatory (R24).** Use only the values from this scale. Arbitrary z-index values are a blocking anti-pattern (`z-index-outside-scale`).

| Tailwind class | Value | Layer | Elements |
|---|---|---|---|
| `z-0` | 0 | Base | Layout, cards, static content |
| `z-10` | 10 | Sticky | Fixed header, footer, side nav |
| `z-20` | 20 | Floating | Dropdown, popover, tooltip |
| `z-30` | 30 | Partial overlay | Drawer, sidebar, bottom sheet |
| `z-40` | 40 | Modal | Dialog, backdrop + content |
| `z-50` | 50 | System | Toast, notification, snackbar |

**Forbidden:**
- z-index outside this scale: `z-99`, `z-100`, `z-999`, `z-9999`
- Inline `style={{ zIndex: 999 }}` without reference to the scale above
- Two elements at the same z-level that must visually stack — use adjacent levels

---

## 9. Information Hierarchy

<!-- INSTRUCTION: This section is CONDITIONAL — fill only if the project has explicit data hierarchy: dashboards, analytics, B2B with metrics, reports. For editorial projects, e-commerce, or conversational focus, this section may be omitted. The goal is that the difference between the highest and lowest level is readable in 3 seconds without reading the content. -->

| Level | Name | Font | Size | Color |
|---|---|---|---|---|
| 1 | {e.g., KPI} | {family} | {token} | {token} |
| 2 | {e.g., Indicator} | {family} | {token} | {token} |
| 3 | {e.g., Delta / variation} | {family} | {token} | semantic color |
| 4 | {e.g., Metadata} | {family} | {token} | `text-muted` |
| 5 | {e.g., Description} | {family} | {token} | `text-body` |

**Rules:**
- Never use the same font across all levels of a component
- Never use the same color for title, data, and metadata
- The difference between Level 1 and Level 4 must be readable in 3 seconds without reading the content

---

## 10. Layout Structure

<!-- INSTRUCTION: Define the grid system, recommended composition patterns, and responsive behavior. Every screen specified in ui-epic-XX.md must reference these patterns by name, without redefining the grid. -->

### Default Grid

- **Base system:** {e.g., 12 columns}
- **Default gap:** {e.g., gap-xl}

### Recommended Patterns

| Pattern | Composition |
|---|---|
| {name — e.g., Full-width} | {e.g., 12 cols} |
| {name — e.g., Main split} | {e.g., 8 cols + 4 cols} |
| {name — e.g., Metric cards} | {e.g., 4 cards × 3 cols each} |

### Responsiveness

| Breakpoint | Behavior |
|---|---|
| `lg` and below | {e.g., simplify composition, remove secondary column where possible} |
| `md` and below | {e.g., stack main blocks} |
| `sm` and below | {e.g., single column, minimum padding p-md} |

<!-- OPTIONAL EXTENSION — Background layering: projects with dark aesthetics and overlapping background layers may define the mandatory layer order: (1) base color bg-primary, (2) global grain texture (single instance in body::after), (3) optional grid overlay (max opacity rgba(255,255,255,0.03)), (4) optional radial accents (max opacity 0.12). -->

### Card Grid Rules (R18)

> **Mandatory.** Card grids must always use fluid `auto-fill` layouts. Fixed column counts and fixed px widths are blocking anti-patterns.

| Card type | Grid rule | Gap |
|---|---|---|
| Small cards (stat, metric) | `repeat(auto-fill, minmax(160px, 1fr))` | `gap-4` (16px) |
| Medium cards (product, user) | `repeat(auto-fill, minmax(240px, 1fr))` | `gap-4` or `gap-6` |
| Large cards (article, panel) | `repeat(auto-fill, minmax(320px, 1fr))` | `gap-6` (24px) |

**Forbidden:**
- `grid-template-columns: repeat(3, 300px)` or any fixed-column-count pattern
- `grid-template-columns` with fixed px values
- Gap between cards other than `gap-4` (16px) or `gap-6` (24px)

### Alignment Rules (R12)

> **Mandatory.** Every element must share a visual axis with at least one other element on screen.

| Rule | Specification |
|---|---|
| Axis sharing | Every element aligns (left, center, or right) with at least one other element |
| Text in block | Always on the same left axis — never mixed alignment within a block |
| Icon + base text | `items-center`, `gap-2` (8px) |
| Icon + small text (12px) | `items-center`, `gap-1.5` (6px) |
| Form labels | `text-left` — never `text-center` except in isolated metric cards |
| Row elements | Aligned by text baseline — use `items-baseline` for rows with mixed font sizes |

**Forbidden:**
- Elements positioned with arbitrary margin or padding without a visual anchor
- Mixed text alignment within the same content block

### Aspect Ratios (R10)

> **Mandatory.** All images and media containers must use one of these ratios. Arbitrary width/height combinations are a blocking anti-pattern.

| Ratio | Use case |
|---|---|
| 1:1 | Avatar, product icon, square thumbnail |
| 4:3 | Content card, standard thumbnail |
| 16:9 | Banner, hero, video thumbnail |
| 1:1.618 | Vertical editorial card (golden ratio) |

**Forbidden:**
- Setting arbitrary `width` and `height` on images without a defined ratio
- Images without `object-fit: cover` / `object-cover` — distortion is an absolute block

---

## 11. Visual Density

<!-- INSTRUCTION: Define quantitative limits for the use of highlight resources per viewport. These limits are review criteria — the UI Agent and QA Agent use this section to validate specs and implementations. -->

### Color Weight Distribution

Distribute visual weight across three roles. These are ratios of perceived visual weight, not pixel count.

| Role | Target weight | Tailwind Classes |
|---|---|---|
| Neutral surfaces | ~60% | `bg-primary`, `bg-surface`, `bg-elevated`, `text-body`, `text-muted` |
| Secondary content (borders, inactive states, supporting text) | ~30% | `border-border`, `text-muted`, inactive variants |
| Accent / primary action | ≤10% | `bg-action`, `bg-data`, `bg-warning`, `bg-danger` |

**Rule:** accent classes work because they are rare. Applying `bg-action` or `bg-data` / `bg-warning` / `bg-danger` to more than ~10% of visible elements removes their signaling power.

### Element Limits per Viewport

| Resource | Maximum per viewport |
|---|---|
| Dominant primary action | 1 |
| {e.g., elements with accent-data highlight} | {e.g., define limit} |
| {e.g., elements with simultaneous animation} | {e.g., define limit} |
| {e.g., simultaneous elevated surfaces} | {e.g., define limit} |

**Core rule:** if everything calls attention, nothing calls attention — highlight scarcity is a visual quality criterion.

**Forbidden (R9 — 60-30-10):**
- Accent color (`bg-action`, `text-action`, `bg-data`) on headings, section backgrounds, decorative icons, or dividers
- More than 2 distinct accent colors per component
- Semantic colors (error red, success green, warning yellow, info blue) used for decoration without semantic meaning
- Required semantic color bindings: error = red (`--color-danger`), success = green, warning = yellow/amber (`--color-warning`), info = blue

<!-- OPTIONAL EXTENSION — Limits for projects with visual effects: if the project uses neon glow, define max elements with active glow per viewport (recommended: 3) and max with flickering (recommended: 2). If using backdrop-filter (glassmorphism), define max simultaneous glass surfaces (recommended: 4-5). -->

---

## 12. Empty States — Required for Every List Component

> **Mandatory (R25).** Every list, table, or grid must have an empty state defined **before** implementation. A missing empty state is an absolute-ban anti-pattern (`list-without-empty-state`).

### Mandatory structure (in order)

| Position | Element | Specification |
|---|---|---|
| 1 | Illustrative icon | 40–48px (`w-10 h-10` to `w-12 h-12`), `text-muted` — never accent color |
| 2 | Title | Describes what is empty, not the error — `font-medium`, `text-base` |
| 3 | Description | Guides the next step — `text-sm`, `text-body` (secondary color) |
| 4 | Primary action | Button or direct link to resolve the empty state |

**Forbidden:**
- Displaying a blank area, em dash "—", or `null` text when a list is empty
- Using error styling (red tones, alert icon, `text-danger`) when the state is simply empty (no data)
- Empty state icon in accent color — always `text-muted` (tertiary)
- Releasing any list or table component without a defined empty state
