# Design System — Components

> Part of: `{SPECS_DIR}/front/design-system/` | Layer: permanent
> Index: [`_index.md`](./_index.md)

---

## Catalog Membership — DS Primitive vs Feature-Local

> Decide before creating any component. This catalog lists **DS primitives only**.
> Adding a component here is a design-system spec change (new `component.spec.md` + a Changelog CR entry in `_index.md`). The Developer never adds a primitive to the catalog ad hoc — it flags the need so the `component-spec-gate` routes it to `u-fe-spec-writer`.

| Trait | DS primitive (`components/ui/`) | Feature-local (`features/<feature>/components/`) |
|---|---|---|
| Domain knowledge | None — purely presentational | Encodes domain / business rules |
| Reuse | Used (or reusable) by ≥ 2 features | Bound to a single feature |
| Data | No fetch/mutation — data arrives via props | May own its feature's data/flow |
| Composition | Is composed FROM | Composes primitives |
| Spec artifact | Has `component.spec.md` + a row in this catalog | No catalog entry required |

**Promotion trigger:** a feature-local component needed by a 2nd feature → promote it to `components/ui/` via CR (`component.spec.md` + catalog row + Changelog entry). Until promoted, never copy it across features.

**Forbidden:**
- Cataloging a component that carries domain / business logic (it is feature-local)
- Duplicating a feature-local component into a second feature instead of promoting it
- Adding a primitive to `components/ui/` without a `component.spec.md`

---

## 12. Component Catalog

<!-- INSTRUCTION: For each component, document which tokens are used in each visual slot, for each relevant state. Add components as they appear in specified screens. Typical slots: bg (background), border, text, icon, shadow. After the token table, add Do/Don't pairs for the most critical components. -->

| Component | Slot | Tailwind Class | default | hover | focus | error | disabled |
|---|---|---|---|---|---|---|---|
| Button (primary) | bg | `bg-action` | V | — | — | — | opacity 50% |
| Button (primary) | bg | `bg-action-hover` | — | V | — | — | — |
| Button (primary) | text | `text-white` / `font-medium` | V | V | V | — | V |
| Input | bg | `bg-surface` | V | V | V | V | V |
| Input | border | `border-border` | V | — | — | — | V |
| Input | border | `border-border-focus` | — | — | V | — | — |
| Input | border | `border-border-error` | — | — | — | V | — |
| Card | bg | `bg-surface` | V | `bg-elevated` | — | — | — |
| Card | shadow | `shadow-sm` | V | `shadow-md` | — | — | — |

### Do/Don't per Component

| Component | Do | Don't |
|---|---|---|
| Primary Button | One per screen; `bg-action`; `font-medium`; `h-10` default / `h-12` large CTA | Use `bg-data`; look like a badge; place 2 Primary buttons in the same context |
| Input | `h-10` desktop / `h-11` mobile; error always with inline helper text | Show error via border color alone; use popup for field errors |
| Card | Apply padding from the card size scale (`p-2` → `p-8`) per card size | Use the same padding on cards of very different sizes |
| {component} | {correct usage} | {incorrect usage} |

<!-- OPTIONAL EXTENSION — Domain-specific components: projects with dashboard, analytics, or B2B may add components beyond the base ones. Examples:
     MetricCard: slots for main-value (Mono / data-lg), delta (semantic color), label (Display / heading), goal/period (Mono muted uppercase), accent-line (bottom border 2px in the card's semantic color).
     DataGrid: rules per column type — textual (Body, left-aligned, text-body), numeric (Mono, right-aligned, text-content, tabular-nums required), header/th (Mono 11px 500 uppercase tracking 0.2em text-muted), actions (icon text-muted on default, text-action on row hover).
     ChartWidget: series semantics — main series (text-data), comparison/previous period (text-action), goal/target (text-warning), historical/baseline (text-muted). Tooltip with glass required.
     Sidebar: default/hover/active states with border-left in semantic color, subtle neon on the active item. -->

---

## 12.1 Form Internal Spacing

> **Mandatory.** Apply to all form layouts. These gaps are the only allowed values between form elements.

| Relationship | Context | Tailwind | Value |
|---|---|---|---|
| Label → input | Between a field label and its input | `gap-1.5` | 6px |
| Input → helper/error text | Between input and the helper or error text below it | `gap-1` | 4px |
| Field → field (same group) | Between consecutive fields in the same group | `gap-4` | 16px |
| Group → group / section | Between distinct field groups or form sections | `gap-8` | 32px |
| Last field → submit button | Between the last field and the form's submit button | `gap-6` | 24px |

**Forbidden:**
- Any gap value outside this table for form elements
- Helper or error text placed inside the input — always below it, `gap-1` from the input border

---

## 12.2 Card Internal Spacing

> **Mandatory.** Select the variant matching the card's visual role. Proportion rule: padding should be 1/4 to 1/6 of the card width — larger card = larger padding.

| Variant | Use case | Tailwind | Value |
|---|---|---|---|
| Compact | Chip, badge, tag | `p-2` | 8px |
| Small | Auxiliary component, tooltip card | `p-3` | 12px |
| Medium | Standard content card | `p-4` | 16px |
| Large | Panel, form container | `p-6` | 24px |
| Extra-large | Modal, main container, drawer | `p-8` | 32px |

**Forbidden:** using the same padding on cards of very different sizes (e.g., `p-4` on both a chip and a modal in the same interface).

---

## 12.3 Touch Targets and Component Heights

> **Mandatory.** Every clickable element must meet the minimum height for its context. Violation is a blocking anti-pattern (`clickable-below-32px`).

| Element | Desktop height | Mobile height | Tailwind |
|---|---|---|---|
| Small button (tables and lists — desktop only) | `h-8` (32px) | — | `h-8` |
| Default button | `h-10` (40px) | `h-11` (44px) | `h-10` / `h-11` |
| Large button / primary CTA | `h-12` (48px) | `h-12` (48px) | `h-12` |
| Default text input | `h-10` (40px) | `h-11` (44px) | `h-10` / `h-11` |
| List item, menu item | min 40px | min 44px | `min-h-10` / `min-h-11` |

**Minimum horizontal padding on buttons:**
- Small button: `px-4` (16px)
- Large button / CTA: `px-6` (24px)

**Forbidden:** any clickable element with height below 32px in any context.

---

## 12.4 Border Radius — One Style Per Project

> **Mandatory.** Choose ONE style at project setup and apply it everywhere. Mixing levels within the same project is a blocking anti-pattern (`mixed-border-radius`).

| Style | Cards | Inputs and buttons | Typical use |
|---|---|---|---|
| Rounded | `rounded-xl` (12px) | `rounded-lg` (8px) | Consumer apps, marketing |
| Neutral | `rounded-lg` (8px) | `rounded-md` (6px) | General-purpose apps |
| Sharp | `rounded-md` (6px) | `rounded` (4px) | Data-dense tools, B2B |

**Rules:**
- Input and button border radius **must** equal or be one level below the card border radius
- Once a style is chosen, every component in the project uses it — no exceptions

**Forbidden:**
- Mixing styles from different rows (e.g., `rounded-xl` cards + `rounded` buttons in the same project)
- Rounded corners on single-side borders (`border-left`, `border-top`) — use `border-radius: 0`

---

## 12.5 Button Hierarchy

> **Mandatory.** Never place two Primary buttons in the same context. Pattern: one Primary + one Secondary or Ghost.

| Type | Background | Border | Text | When to use |
|---|---|---|---|---|
| Primary | `bg-action` | none | `text-white`, `font-medium` | Single main action per context |
| Secondary | transparent | `border-action` 1px | `text-action`, `font-medium` | Supporting action alongside Primary |
| Ghost | none | none | `text-action` | Tertiary or cancel action; hover adds `bg-surface` subtle fill |
| Danger | `bg-danger` or `border-danger` 1px | — | `text-white` or `text-danger` | Irreversible destructive actions only |

**Minimum horizontal padding:** `px-4` (16px) small; `px-6` (24px) large.

**Forbidden:**
- Two Primary buttons in the same form, dialog, or screen section
- Danger button as the default form submission action
- Ghost button without any visible hover state

---

## 12.6 Component States — 5 Mandatory

> **Mandatory.** Every interactive element (button, input, link, toggle, checkbox, select) must implement all 5 states. `focus-ring-missing` is an absolute-ban anti-pattern.

| State | Visual specification | Transition |
|---|---|---|
| **Default** | Standard border (`border-border`), no additional fill | — |
| **Hover** | `bg-surface` tint + border at increased opacity | `transition-colors duration-100 ease-in-out` |
| **Focus** | 3px ring in accent at 20% opacity (`box-shadow: 0 0 0 3px {color-action-20%}`) + `border-border-focus` | `transition-shadow duration-100 ease-in-out` |
| **Active** | `scale-[0.98]` + `bg-action-active` (primary) or slightly darker bg for others | `transition duration-100 ease-in` |
| **Disabled** | `opacity-50` + `cursor-not-allowed` + `pointer-events-none` | — |

**Forbidden:**
- Communicating state through color alone — always combine color with shape or text
- Invisible focus ring — accessibility violation, absolute block
- Disabled state without `pointer-events-none`

---

## 12.7 Input Validation States

> **Mandatory.** All three validation states must be defined for every text input. `error-border-only` is an absolute-ban anti-pattern.

| State | Border | Background | Helper text |
|---|---|---|---|
| Neutral | 0.5px `border-border` | `bg-surface` | None |
| Error | 1px `border-border-error` | red-tinted `bg-surface` | `text-xs text-danger`, `gap-1` (4px) below input |
| Success | 1px `border-success` (green) | green-tinted `bg-surface` | `text-xs text-success`, `gap-1` (4px) below input |

**Helper text rules:**
- Font size: `text-xs` (12px)
- Position: always below the input, never inside it
- Gap: `gap-1` (4px) between input bottom border and helper text

**Forbidden:**
- Showing validation state via border color alone — always include explanatory text
- Using an alert or popup for field-level validation errors — always inline
- Placing error text inside the input placeholder

---

## 12.8 Table Density — 3 Fixed Variants

> **Mandatory.** Choose one density variant per table. Never mix variants in the same table or screen.

| Variant | Row padding | Use case | Tailwind |
|---|---|---|---|
| Compact | `py-2` (8px per side) | Dashboards, dense data tables | `py-2` |
| Default | `py-3` (12px per side) | General use | `py-3` |
| Relaxed | `py-4` (16px per side) | Lists with avatars or multi-line text | `py-4` |

**Table header — all variants:**
- Font size: `text-xs` (12px)
- Weight: `font-medium` (500)
- Case: `uppercase`
- Letter spacing: `tracking-[0.06em]`
- Color: `text-muted` (tertiary)

**Forbidden:**
- Two density variants in the same table
- Row padding outside `py-2`, `py-3`, or `py-4`

---

## 12.9 Icon Sizes — 4 Fixed Values

> **Mandatory.** Always set explicit `width` and `height`. Never let icons inherit size from the container `font-size`.

| Size | Use case | Gap to adjacent text |
|---|---|---|
| 14px | Inline with 12px text, badge labels | `gap-1.5` (6px) |
| 16px | **Default** — inline with 14–16px text (80% of cases) | `gap-2` (8px) |
| 20px | Emphasis, large buttons, primary navigation | `gap-2` (8px) |
| 24px | Decorative, empty states, UI illustrations | `gap-2` (8px) |

**Tailwind size classes:** `w-3.5 h-3.5` (14px) · `w-4 h-4` (16px) · `w-5 h-5` (20px) · `w-6 h-6` (24px)

**Forbidden:**
- Icon sizes outside this scale (e.g. 12px, 18px, 22px)
- Inheriting size from container — always explicit `w-* h-*`
- Icons above 24px in functional contexts (illustrative and empty-state use only)

---

## 12.10 Avatar Sizes — Fixed Scale

> **Mandatory.** Avatars must use only the sizes from this scale. Sizes outside it are a slop anti-pattern (`avatar-off-scale`).

| Size | Context | Tailwind |
|---|---|---|
| 24px | Compact list, inline mention, avatar stack | `w-6 h-6` |
| 32px | Navigation, header, comment area | `w-8 h-8` |
| 40px | **Default** — cards, tables, forms | `w-10 h-10` |
| 48px | Profile card, sidebar, main list | `w-12 h-12` |
| 64px | Profile page, user section header | `w-16 h-16` |
| 80px | Hero, primary user page | `w-20 h-20` |

**Rules:**
- Always 1:1 aspect ratio
- Circular avatar: `rounded-full`
- Square avatar with border: `rounded-lg` (matching the project's border radius style)

**Forbidden:** sizes outside this scale (e.g. 36px, 44px, 56px, 72px).
