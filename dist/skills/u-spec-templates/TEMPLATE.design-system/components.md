# Design System — Components

> Part of: `{SPECS_DIR}/front/design-system/`
> Index: [`_index.md`](./_index.md)

---

## 12. Component Catalog

<!-- INSTRUCTION: For each component, document which tokens are used in each visual slot, for each relevant state. Add components as they appear in specified screens. Typical slots: bg (background), border, text, icon, shadow. After the token table, add Do/Don't pairs for the most critical components. -->

| Component | Slot | Token | default | hover | focus | error | disabled |
|---|---|---|---|---|---|---|---|
| Button (primary) | bg | `--primary-action` | V | — | — | — | opacity 50% |
| Button (primary) | bg | `--primary-action-hover` | — | V | — | — | — |
| Button (primary) | text | `--text-primary` | V | V | V | — | V |
| Input | bg | `--bg-surface` | V | V | V | V | V |
| Input | border | `--border-subtle` | V | — | — | — | V |
| Input | border | `--border-interactive` | — | — | V | — | — |
| Input | border | `--border-error` | — | — | — | V | — |
| Card | bg | `--bg-surface` | V | `--bg-elevated` | — | — | — |
| Card | shadow | `--shadow-sm` | V | `--shadow-md` | — | — | — |

### Do/Don't per Component

<!-- INSTRUCTION: For the most critical components, document examples of correct and incorrect usage. Focus on frequent mistakes: mixing action token with data token, duplicating primary action, using highlight decoratively. -->

| Component | Do | Don't |
|---|---|---|
| Primary Button | One per screen; color `--primary-action`; Display uppercase | Use `--accent-data`; look like a badge; 2 primary buttons on the same screen |
| {component} | {correct usage} | {incorrect usage} |

<!-- OPTIONAL EXTENSION — Domain-specific components: projects with dashboard, analytics, or B2B may add components beyond the base ones. Examples:
     MetricCard: slots for main-value (Mono / data-lg), delta (semantic color), label (Display / heading), goal/period (Mono muted uppercase), accent-line (bottom border 2px in the card's semantic color).
     DataGrid: rules per column type — textual (Body, left-aligned, --text-body), numeric (Mono, right-aligned, --text-primary, tabular-nums required), header/th (Mono 11px 500 uppercase tracking 0.2em --text-muted), actions (icon --text-muted on default, --primary-action on row hover).
     ChartWidget: series semantics — main series (--accent-data), comparison/previous period (--primary-action), goal/target (--accent-warning), historical/baseline (--text-muted). Tooltip with glass required.
     Sidebar: default/hover/active states with border-left in semantic color, subtle neon on the active item. -->
