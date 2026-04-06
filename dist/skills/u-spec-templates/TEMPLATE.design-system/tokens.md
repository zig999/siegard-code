# Design System — Tokens

> Part of: `{SPECS_DIR}/front/design-system/`
> Index: [`_index.md`](./_index.md)

---

## 3. Color Tokens

<!-- INSTRUCTION: Define the semantic intent of each token. Answer: what does this token represent conceptually? Where should it be used? Where should it NOT be used? Do not include hex values — this is the spec file, not the implementation. The actual values live in the project's global CSS file. -->

<!-- OPTIONAL EXTENSION — Color origins: if the project has a brand manual, add an origin table before the semantic tokens with columns: Color | Pantone (optional) | HEX | Role in the system. Also document background tokens derived from the brand color (e.g., dark backgrounds with progressively reduced brightness, maintaining the identity hue). This preserves coherence across future iterations and allows the agent to regenerate the palette without consulting the brand manual each time. -->

### Semantic Tokens

| Semantic Token | Usage Intent | Where to use | Where NOT to use |
|---|---|---|---|
| `--bg-primary` | Main application background | Root layout, pages | Modals, tooltips, elevated cards |
| `--bg-surface` | Content surface over the background | Cards, panels, sidebars | Page background |
| `--bg-elevated` | Elevated surface (higher prominence) | Dropdowns, modals, popovers | Page background, regular cards |
| `--text-primary` | Highest-importance text | Titles, field labels, actions | Supporting text, placeholders |
| `--text-body` | General content text | Paragraphs, descriptions, values | Section titles |
| `--text-muted` | Lowest-importance text | Placeholders, metadata, hints | Field labels, primary values |
| `--primary-action` | Primary action color | Primary buttons, action links | Backgrounds, content text |
| `--primary-action-hover` | Primary action hover state | Primary button on hover | -- |
| `--primary-action-active` | Active/pressed state | Primary button on active | -- |
| `--accent-data` | Data/metrics highlight | Charts, status badges, KPIs | Actions, alerts |
| `--accent-warning` | Alert and attention | Warning messages, error borders | Positive actions, neutral data |
| `--accent-danger` | Error and danger | Error messages, delete confirmation | Warning alerts, neutral data |

<!-- OPTIONAL EXTENSION — Visual effect tokens: projects with glass/neon/dark aesthetics may add tokens like:
     --bg-glass (rgba with opacity for translucent surfaces),
     --bg-sidebar (darker variant of the background for side navigation),
     --border-glass (subtle border for glassmorphism elements),
     --neon-glow-color (base color for text-shadow and box-shadow neon — typically same as accent-data),
     --neon-glow-rgb (RGB components of the neon color for use in rgba()),
     --bg-primary-rgb (RGB components of the main background for glass surface composition).
     Only add tokens the project actually uses systematically — unused tokens pollute the system and confuse agents. -->

### Mandatory Semantics

| Token | Meaning | Can use in | Do not use in |
|---|---|---|---|
| `--primary-action` | primary action | primary button, link, focus, contextual active item | KPI, positive data |
| `--accent-data` | positive data / informational highlight | metrics, positive deltas, main series | primary action |
| `--accent-warning` | attention | at-risk targets, warning | navigation action |
| `--accent-danger` | error / risk | error, incident, decline | mild alerts |

> **Critical rule:** `--accent-data` is not an action color. Never use `--accent-data` on a button, link, or any element that triggers an operation.

---

## 4. Spacing Tokens

<!-- INSTRUCTION: Define the spacing scale in multiples of 4px or 8px. Use consistent naming (e.g., --space-1, --space-2). Describe the typical usage of each level. Arbitrary px values outside this scale are forbidden. -->

| Token | Typical Usage |
|---|---|
| `--space-1` | Micro — separation between icon and label, badge padding |
| `--space-2` | Small — gap between inline elements, tag padding |
| `--space-3` | Base — button padding, default gap between form fields |
| `--space-4` | Medium — card padding, spacing between nearby sections |
| `--space-6` | Large — margin between sections, container padding |
| `--space-8` | Extra large — spacing between distinct content blocks |

---

## 5. Typographic Scale

<!-- INSTRUCTION: Define text styles by purpose. Token should express the semantic usage, not the technical size. If the project adopts triple typography (display/body/mono), document each family before the token table: its name, semantic role, and the rules of where to use and where not to use. -->

<!-- OPTIONAL EXTENSION — Triple typography: projects with strong typographic identity (HUD, fintech, dashboard, technical B2B) may adopt three families with distinct roles:
     (1) Display/Structural UI — for titles, navigation, buttons, and interface labels. Technical or brand personality.
     (2) Body — for content, descriptions, and forms. Neutral, high readability.
     (3) Mono — for data, metrics, IDs, timestamps, and numeric columns. Precision and comparability.
     For each family: document the chosen name, semantic role, and usage rules (where to use / where not to use). Typical rules: Display never in paragraphs with more than 2 lines at small size; Mono mandatory with font-variant-numeric: tabular-nums on any comparable numeric data; weight contrast between Display title and Body content as a hierarchy resource. -->

| Token | Relative Size | Weight | Default Color | Usage |
|---|---|---|---|---|
| `--text-display` | Extra large | Bold | `--text-primary` | Main page titles, hero |
| `--text-heading` | Large | SemiBold | `--text-primary` | Section titles, card headers |
| `--text-subheading` | Medium-large | Medium | `--text-primary` | Subtitles, group labels |
| `--text-body-lg` | Medium | Regular | `--text-body` | Main body text, descriptions |
| `--text-body-sm` | Small | Regular | `--text-body` | Secondary text, metadata |
| `--text-label` | Small | Medium | `--text-primary` | Field labels, table headers |
| `--text-caption` | Extra small | Regular | `--text-muted` | Hints, footers, timestamps |
| `--text-code` | Mono | Regular | `--text-body` | Technical values, snippets |

---

## 6. Shadows and Borders

<!-- INSTRUCTION: Define elevation and visual separation tokens by purpose. -->

| Token | Usage Context |
|---|---|
| `--shadow-sm` | Base-level cards, focused form fields |
| `--shadow-md` | Dropdowns, tooltips, floating elements |
| `--shadow-lg` | Modals, side panels, drawers |
| `--border-subtle` | Separators, card borders in default state |
| `--border-interactive` | Input borders on focus, selected elements |
| `--border-error` | Validation error field borders |
| `--radius-sm` | Small buttons, badges, tags |
| `--radius-md` | Standard buttons, cards, inputs |
| `--radius-lg` | Modals, panels, large containers |

<!-- OPTIONAL EXTENSION — Depth tokens for visual effects: projects with glassmorphism or neon may add:
     --shadow-glass (colored shadow with accent-data at low opacity),
     --shadow-neon-border (multi-layer box-shadow for neon-glowing borders).
     Only makes sense to add if the project uses these effects systematically. -->

---

## 8. Semantic Usage Rules

<!-- INSTRUCTION: Constraints that agents must respect when specifying screens. The rules below are the minimum set — add project-specific rules as needed. -->

- `--accent-data` must never be used as an action color — it is exclusive to data visualization
- `--accent-warning` indicates attention/warning; `--accent-danger` indicates error/irreversible danger — do not interchange
- `--primary-action` should appear on at most 1 element per screen as the primary action
- Text on dark backgrounds must use `--text-primary` or `--text-body` — never highlight colors
- Interactive borders (`--border-interactive`) are exclusive to focus/selection states — do not use decoratively
- Spacing tokens must be used in multiples of the base scale — never arbitrary px values
- `style=""` / `style={{}}` inline is forbidden — except dynamic values with no equivalent in the style system
- Never use `transition: all` — specify animated properties explicitly
- Animations wrapped in `@media (prefers-reduced-motion: no-preference)`
