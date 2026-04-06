---
name: u-fe-ui
description: Templates, naming conventions, and quality rules for UI specifications. Covers screen maps, component tables, state tables, interaction descriptions, and design system tokens. Loaded by orchestrator-dev when activating the UI Agent.
user-invocable: false
---

# SKILL: UI Specification

## Purpose
This skill defines the templates, naming conventions, and quality checklist for the UI Agent to produce consistent, complete visual specifications ready for the Developer Agent.

---

## File naming convention

```
{SESSIONS_DIR}/{SESSION}/ui-epic-XX.md
```

Where `XX` is the Epic number in lowercase with leading zero:
- EPIC-01 -> `ui-epic-01.md`
- EPIC-02 -> `ui-epic-02.md`

> Always use the Epic’s numeric identifier, not its descriptive name, to ensure a stable reference.

---

## Customization via CLAUDE.md

Before producing any specification, extract from `CLAUDE.md`:

| What to look for | Used in |
|---|---|
| Component library (shadcn, MUI, Tremor, Ant Design...) | Reference components by the library’s name |
| Design system or tokens already defined | Palette, typography, spacing |
| Frontend framework (React, Vue, Next.js...) | Screen structure conventions |
| Domain terminology | Suggested texts and labels — never use generic placeholders |

---

## Canonical screen template

```markdown
### Screen: [Name]

**Story(ies):** US-XX
**Persona:** [Persona name as defined in CLAUDE.md or specs]
**User goal on this screen:** [What they need to accomplish here — in domain language]

---

#### Layout structure

[Describe the regions in ASCII or structured text]

+----------------------------------+
| HEADER: [logo] [navigation] [user]|
+----------------------------------+
| SIDEBAR        | CONTENT          |
| - item 1       | [title]          |
| - item 2       | [main area]      |
+----------------------------------+
| FOOTER: [secondary info]         |
+----------------------------------+

---

#### Components

| Component | Type | Content | Default state |
|-----------|------|---------|---------------|
| [Name] | Button / Input / Card / Table / Modal / ... | [what it displays] | Active / Disabled / Loading |

> If the project uses a component library, reference the exact name (e.g., `<Button variant="primary">`, `<DataTable>`, `<Sheet>`).

---

#### Visual hierarchy

1. **Most prominent element:** [which and why — usually the primary action]
2. **Secondary element:** [which]
3. **Supporting elements:** [which]

---

#### Mandatory screen states

| State | Trigger | What changes visually |
|-------|---------|----------------------|
| Default | Screen loaded with data | [description] |
| Loading | Request in progress | [skeleton / spinner — specify which] |
| Empty | No data to display | [empty state — message + suggested action] |
| Error | Request failure | [error message + recovery action] |
| Success | Action completed | [visual feedback — toast / banner / redirect] |

> A screen without an error state and an empty state is **incomplete** — the Developer cannot start without them.

---

#### Messages and texts

| Element | Suggested text |
|---------|---------------|
| Screen title | "[text — use domain terminology]" |
| Primary action | "[button label]" |
| Empty state | "[message]" |
| Generic error | "[message]" |
| Success confirmation | "[message]" |

---

#### Interaction behaviors

- [User action -> system response: hover, click, drag, submit, etc.]
- [Responsive behaviors if relevant to the Epic]
- [Accessibility: expected keyboard focus, relevant aria-labels]

---

#### Reference to UX principles

- [Project UX principle]: how it applies to this screen
```

---

## Screen map template (required at the beginning of the document)

```markdown
## Screen map

| Screen | Story(ies) | Primary persona | Type |
|--------|-----------|-----------------|------|
| [Name] | US-XX, US-YY | [Persona] | New screen / Modified existing screen |
```

---

## Visual guidelines (per Epic)

Before specifying any visual detail, check:

1. If `{SPECS_DIR}/front/design-system/` **exists**: reference the existing tokens. Never redefine palette, typography, or spacing in `ui-epic-XX.md`.

2. If it **does not exist**: flag to the Front Spec Agent to create it using `TEMPLATE.design-system/` before proceeding. The UI Agent does not define tokens — it only references them.

In `ui-epic-XX.md`, the visual guidelines section must follow this format:

```markdown
## Visual guidelines — EPIC-XX

> Tokens defined in `{SPECS_DIR}/front/design-system/`.

| Element | Semantic token | Usage note for this Epic |
|---------|----------------|--------------------------|
| [element] | `--token-name` | [specific usage context] |
```

> Defining palette, typography, spacing, or CSS values directly in `ui-epic-XX.md` is forbidden. If a needed token does not exist in `design-system/tokens.md`, flag it with a Warning for the Front Spec Agent to add there first.

---

## Final structure of `ui-epic-XX.md`

```markdown
# UI Spec — EPIC-XX: [Epic Name]

_Created on: YYYY-MM-DD_
_Reference: specs and CLAUDE.md_
_Stories covered: US-XX, US-YY, US-ZZ_

---

## Screen map
[screens x stories table]

---

## Screen specifications
[one section per screen using the canonical template]

---

## Visual guidelines
[palette, typography, spacing, components]

---

## Open questions
[items marked with Warning that need answers before the Developer can start]
```

---

## Quality checklist before delivery

- [ ] All screens in the Epic are mapped (no released Story without its screen specified)
- [ ] Each screen has the 5 mandatory states: Default, Loading, Empty, Error, Success
- [ ] Texts and labels use domain terminology (no generic placeholders)
- [ ] Project component library components are referenced by exact name
- [ ] Visual hierarchy is defined for each screen
- [ ] Keyboard behaviors and aria-labels have been considered
- [ ] Project UX principles are referenced in at least one screen
- [ ] Open questions are marked with `Warning`
- [ ] File name follows the convention: `{SESSIONS_DIR}/{SESSION}/ui-epic-XX.md`
- [ ] Visual tokens referenced from `{SPECS_DIR}/front/design-system/` — never defined locally in the ui-epic

---

## Quality rules

| Rule | Action if violated |
|---|---|
| Screen without error state | Mark as `Warning` and do not release to Developer |
| Screen without empty state | Mark as `Warning` and do not release to Developer |
| Text with "Lorem ipsum" or "Click here" | Replace with domain terminology |
| Library component not referenced by name | Fix before delivery |
| Large Epic (5+ Stories) — partial delivery | Specify which Stories can proceed; never release a Story with a partially specified screen |
