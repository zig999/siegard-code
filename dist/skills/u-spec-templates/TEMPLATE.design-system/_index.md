# Design System — {Project Name}

> Path: `{SPECS_DIR}/front/design-system/`
> Implementation: `{path to the project's global CSS file}`
> Version: 1.0.0

<!-- SINGLE SOURCE OF TRUTH for visual tokens, typography, spacing, composition and components.
     All other files (front.md, *.screen.md, ui-epic-XX.md, CLAUDE.md) REFERENCE this directory — never duplicate its content.
     Actual hex and px values live in the project's global CSS file. This directory documents semantic intent and implementation rules.

     DIRECTORY STRUCTURE:
     design-system/
       _index.md           — this file: principles, visual context and summary
       tokens.md           — colors, spacing, typography, shadows and borders
       composition.md      — visual effects, hierarchy, layout, density
       components.md       — component catalog (slots x states, do/dont)
       implementation.md   — accessibility, animations, QA checklist, guidelines

     SELECTIVE READING RULE:
     Agents MUST NOT read all files by default. The context-mounting protocol
     defines which files to load per task type. When in doubt, reading _index.md
     + tokens.md is sufficient for most implementations. -->

---

## 1. System principles

<!-- INSTRUCTION: Document the principles that guide this project's visual decisions before any tokens. Answer: what is the primary focus of the interface? which information hierarchy matters most? what are the highlight constraints? Write as named principles with a 1-2 line description. -->

| Principle | Description |
|---|---|
| {name} | {1-2 line description} |

---

## 2. Visual context

<!-- INSTRUCTION: Define the project's visual scope. Color mode: dark-only | light-only | both with toggle. Personality: describe the visual tone in 1 sentence. Constraints: what this project definitively does not do visually. This section is used by the UI Agent to make visual decisions without needing to ask for each spec. -->

- **Color mode:** {dark-only | light-only | both}
- **Visual personality:** {description}
- **Aesthetic constraints:** {list of constraints}

---

## 3. File summary

| File | Content | When to load |
|---|---|---|
| `tokens.md` | Colors, spacing, typography, shadows and borders | Whenever implementing visual styles |
| `composition.md` | Visual effects (glass, neon, spotlight), hierarchy, layout, density | Screens with effects, dashboards, complex layout |
| `components.md` | Component catalog: slots x states, do/dont | Implementing or specifying visual components |
| `implementation.md` | Accessibility, animations, QA checklist, team guidelines | Visual QA, PR review, accessibility adjustments |

---

## Changelog

<!-- INSTRUCTION: Mandatory. Never remove previous entries. Unified changelog for the entire design-system/ directory. -->
| Version | Date | Author | Type | Description | CR |
|---|---|---|---|---|---|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
