# Design System — Composition

> Part of: `{SPECS_DIR}/front/design-system/`
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

## 9. Information Hierarchy

<!-- INSTRUCTION: This section is CONDITIONAL — fill only if the project has explicit data hierarchy: dashboards, analytics, B2B with metrics, reports. For editorial projects, e-commerce, or conversational focus, this section may be omitted. The goal is that the difference between the highest and lowest level is readable in 3 seconds without reading the content. -->

| Level | Name | Font | Size | Color |
|---|---|---|---|---|
| 1 | {e.g., KPI} | {family} | {token} | {token} |
| 2 | {e.g., Indicator} | {family} | {token} | {token} |
| 3 | {e.g., Delta / variation} | {family} | {token} | semantic color |
| 4 | {e.g., Metadata} | {family} | {token} | `--text-muted` |
| 5 | {e.g., Description} | {family} | {token} | `--text-body` |

**Rules:**
- Never use the same font across all levels of a component
- Never use the same color for title, data, and metadata
- The difference between Level 1 and Level 4 must be readable in 3 seconds without reading the content

---

## 10. Layout Structure

<!-- INSTRUCTION: Define the grid system, recommended composition patterns, and responsive behavior. Every screen specified in ui-epic-XX.md must reference these patterns by name, without redefining the grid. -->

### Default Grid

- **Base system:** {e.g., 12 columns}
- **Default gap:** {e.g., --space-4 (24px)}

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
| `sm` and below | {e.g., single column, minimum padding --space-3} |

<!-- OPTIONAL EXTENSION — Background layering: projects with dark aesthetics and overlapping background layers may define the mandatory layer order: (1) base color --bg-primary, (2) global grain texture (single instance in body::after), (3) optional grid overlay (max opacity rgba(255,255,255,0.03)), (4) optional radial accents (max opacity 0.12). -->

---

## 11. Visual Density

<!-- INSTRUCTION: Define quantitative limits for the use of highlight resources per viewport. These limits are review criteria — the UI Agent and QA Agent use this section to validate specs and implementations. -->

| Resource | Maximum per viewport |
|---|---|
| Dominant primary action | 1 |
| {e.g., elements with accent-data highlight} | {e.g., define limit} |
| {e.g., elements with simultaneous animation} | {e.g., define limit} |
| {e.g., simultaneous elevated surfaces} | {e.g., define limit} |

**Core rule:** if everything calls attention, nothing calls attention — highlight scarcity is a visual quality criterion.

<!-- OPTIONAL EXTENSION — Limits for projects with visual effects: if the project uses neon glow, define max elements with active glow per viewport (recommended: 3) and max with flickering (recommended: 2). If using backdrop-filter (glassmorphism), define max simultaneous glass surfaces (recommended: 4-5). -->
