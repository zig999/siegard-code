---
name: u-fe-ui
description: Templates, naming conventions, and quality rules for UI specifications. Covers screen maps, UI-NN state tables, BDD scenario coverage, FL-NN interaction behaviors, and design system tokens. Loaded by orchestrator-dev when activating the UI Agent.
user-invocable: false
---

# SKILL: UI Specification

## Purpose

This skill defines the templates, naming conventions, and quality checklist for the UI Agent to produce visual specifications that are traceable to feature.spec.md states (UI-NN), flow.md navigation (FL-NN), and §9 BDD scenarios.

> **u-ui-design vs u-fe-ui:** `u-fe-ui` (this skill) is the pipeline spec — it translates feature.spec.md states into layout, components, tokens, and accessibility for developer implementation. `u-ui-design` is a user-invocable design amplification tool — it applies `visual_personality` directional rules and audits anti-patterns on existing code. It is not part of the automated pipeline. Invoke it manually with `/u-ui-design [target]` when design quality improvement is needed on delivered code.

---

## File naming convention

```
{SESSIONS_DIR}/{SESSION}/ui-epic-XX.md
```

Where `XX` is the Epic number in lowercase with leading zero:
- EPIC-01 → `ui-epic-01.md`
- EPIC-02 → `ui-epic-02.md`

> Always use the Epic's numeric identifier, not its descriptive name, to ensure a stable reference.

---

## Customization via CLAUDE.md

Before producing any specification, extract from `CLAUDE.md`:

| What to look for | Used in |
|---|---|
| Component library (shadcn, MUI, Tremor, Ant Design...) | Referencing components by library name |
| Design system or pre-defined tokens | Palette, typography, spacing |
| Frontend framework (React, Vue, Next.js...) | Screen structure conventions |
| Domain terminology | Suggested text and labels — never use generic placeholders |

---

## Canonical screen template

```markdown
### Screen: [Route / Page Name]

**Task Contract(s):** TC-XX
**Feature:** [feature-name] (from feature.spec.md)
**Persona:** [Persona name as defined in CLAUDE.md or specs]
**User goal on this screen:** [What they need to accomplish — in domain language]
**UI states covered:** UI-01, UI-02, UI-03, UI-04 (from feature.spec.md §2)
**FL-NN flows handled:** FL-01 (happy path), FL-02 (error path) (from flow.md)

---

#### Layout structure

[Describe regions in ASCII or structured text]

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

| Component | Type | Content | Default State |
|-----------|------|---------|---------------|
| [Name] | Button / Input / Card / Table / Modal / ... | [what it displays] | Active / Disabled / Loading |

> Reference component library components by exact name (e.g., `<Button variant="primary">`, `<DataTable>`, `<Sheet>`).
> For components listed in §7 of feature.spec.md, use the Props Contract from component.spec.md — do not invent props.

---

#### Visual hierarchy

| Priority | Element | Reason |
|----------|---------|--------|
| 1 — primary | [element] | [why most prominent] |
| 2 — secondary | [element] | [role] |
| 3 — supporting | [element] | [role] |

---

#### State specifications

Each row maps a UI-NN state (from feature.spec.md §2) to its visual form.

| State ID | Name | Trigger (locked — §3) | Layout change | Key component | Visual note |
|----------|----- |-----------------------|---------------|---------------|-------------|
| UI-01 | [name from §2] | [trigger from §3] | [what changes] | `<ComponentName>` | [token or style note] |
| UI-02 | [name] | [trigger] | [skeleton / spinner — specify] | `<Skeleton>` | [token] |
| UI-03 | [name — empty] | [trigger] | [empty state] | `<EmptyState>` | [message from §9 or §6] |
| UI-04 | [name — error] | error.code = XXX (§6) | [error banner] | `<Alert variant="error">` | [message text from §6] |
| UI-05 | [name — success] | [trigger] | [toast / banner / redirect] | `<Toast>` | [message] |

> All UI-NN states from §2 must appear in this table. Missing a state blocks development.
> Error state message text must match §6 exactly — do not paraphrase.

---

#### Messages and text

| Element | Text source | Suggested text |
|---------|-------------|----------------|
| Screen title | domain terminology | "[text]" |
| Primary action | domain terminology | "[button label]" |
| Empty state (UI-0N) | §9 or domain | "[message]" |
| Generic error (UI-0N) | §6 exact | "[error message from §6]" |
| Success confirmation (UI-0N) | §9 or domain | "[message]" |

---

#### Interaction behaviors

| Action | FL-NN | System response | Visual feedback |
|--------|-------|-----------------|-----------------|
| [user action] | FL-XX | [what happens — from §3] | [animation / state change] |

Accessibility: [keyboard focus path, relevant aria-labels, ARIA roles for dynamic states]

---

#### §9 BDD scenario coverage

| Scenario | Scenario title | UI state(s) exercised | Coverage |
|----------|--------------  |-----------------------|----------|
| S-01 | [title] | UI-01, UI-03 | full |
| S-02 | [title] | UI-04 | full |

> Coverage: `full` = "Then" step observable in this spec | `partial` = partially covered — note gap | `missing` = state not in §2 — Warning for Spec Team

---

#### Token references

| Element | Token | Note |
|---------|-------|------|
| [element] | `--token-name` | [usage context for this screen] |

> Tokens must exist in `{SPECS_DIR}/front/design-system/tokens.md`. If a required token is missing:
> `Warning: token [name] not found — escalate to Spec Team before proceeding.`

---

#### UX principles reference

- [Project UX principle from CLAUDE.md]: how it applies to this screen
```

---

## Screen map template (required at the beginning of the document)

```markdown
## Screen map

| Screen (route) | Task Contract(s) | Feature | UI states | FL-NN flows | Type |
|----------------|-----------|---------|-----------|-------------|------|
| [Route/Page] | TC-XX | [feature] | UI-01…UI-04 | FL-01, FL-02 | New / Modified |
```

---

## Visual guidelines (per Epic)

Before specifying any visual detail, verify:

1. If `{SPECS_DIR}/front/design-system/` **exists**: reference the existing tokens. Never redefine palette, typography, or spacing in the `ui-epic-XX.md`.

2. If it **does not exist**: signal the Orchestrator-Dev to escalate to the Spec Team before proceeding. The UI Agent does not define tokens — it only references them.

In the `ui-epic-XX.md`, the visual guidelines section must follow this format:

```markdown
## Visual guidelines — EPIC-XX

> Tokens defined in `{SPECS_DIR}/front/design-system/`.

| Element | Semantic token | Usage note for this Epic |
|---------|---------------|--------------------------|
| [element] | `--token-name` | [specific usage context] |
```

> Defining palette, typography, spacing, or CSS values directly in `ui-epic-XX.md` is prohibited. If a required token does not exist in `design-system/tokens.md`, flag it with Warning for the Spec Team to add it there first.

---

## Final structure of `ui-epic-XX.md`

> Full template: `.claude/skills/u-fe-templates/ui-epic.md`

````markdown
```yaml
# ui-spec-gate
epic: EPIC-XX
layer: semi-permanent
produced_by: u-fe-ui
timestamp: <YYYY-MM-DDTHH:MM:SSZ>

tasks_covered:
  - id: TC-XX
    screens: ["ScreenName1", "ScreenName2"]
    status: complete | partial
  - id: TC-YY
    screens: ["ScreenName3"]
    status: complete | partial

ui_nn_covered:
  - feature: feature-name
    source: "{SPECS_DIR}/front/features/feature-name.feature.spec.md"
    states: [UI-01, UI-02, UI-03, UI-04]
    all_states_covered: true | false

bdd_scenarios_covered:
  - scenario_id: S-01
    screen: ScreenName
    states: [UI-01, UI-03]
    coverage: full | partial | missing
  - scenario_id: S-02
    screen: ScreenName
    states: [UI-04]
    coverage: full

design_system:
  source: "{SPECS_DIR}/front/design-system/"
  rules_applied: true | false

open_questions_count: <int>
ready_for_development: true | false
partial_release_notes: ""   # populated when status: partial for any story
```

# UI Spec — EPIC-XX: [Epic Name]

> layer: semi-permanent | created: YYYY-MM-DD | task_contracts: TC-XX, TC-YY, TC-ZZ
> feature specs: feature-name.feature.spec.md | flows: feature-name.flow.md

---

## Screen map
[screens × Task Contracts × UI-NN × FL-NN table]

---

## Screen specifications
[one section per screen using the canonical template]

---

## Visual guidelines — EPIC-XX
[token references for this Epic]

---

## Open questions
[items flagged with Warning that need answers before the Developer proceeds]
````

---

## Quality checklist before delivery

- [ ] File starts with `ui-spec-gate` YAML block — all fields populated
- [ ] `ui_nn_covered` lists every UI-NN state from `feature.spec.md §2` for all features in this Epic
- [ ] `ui_nn_covered[*].all_states_covered: true` for every feature (or open question explains the gap)
- [ ] `bdd_scenarios_covered` lists every §9 scenario — no `coverage: missing` without a Warning entry
- [ ] `ready_for_development: true` only when all task_contracts have `status: complete`, no `coverage: missing` in BDD, and `open_questions_count: 0` (or all open questions are non-blocking)
- [ ] `task_contracts_covered` lists every Task Contract in the Epic with its screen names
- [ ] All screens in the Epic are mapped (no Task Contract released without its screen specified)
- [ ] Each screen's "State specifications" table covers all UI-NN states from §2
- [ ] Error state messages match §6 exactly — not paraphrased
- [ ] Text and labels use domain terminology (no generic placeholders)
- [ ] Project component library components are referenced by exact name
- [ ] Components from §7 use Props Contract from component.spec.md — no invented props
- [ ] Visual hierarchy is defined for each screen
- [ ] Keyboard behaviors and aria-labels have been considered for dynamic states
- [ ] FL-NN flows are referenced in interaction behaviors
- [ ] Project UX principles are referenced in at least one screen
- [ ] Open questions are flagged with `Warning`
- [ ] File name follows the convention: `{SESSIONS_DIR}/{SESSION}/ui-epic-XX.md`
- [ ] Visual tokens referenced from `{SPECS_DIR}/front/design-system/` — never defined locally in the ui-epic
- [ ] Visual anti-patterns scan: no absolute-ban patterns (`side-tab`, `gradient-text`) and no slop-category patterns (`bounce-easing`, `border-accent-on-rounded`) specified for any component — thresholds in `u-ui-design/anti-patterns.md`

---

## Quality rules

| Rule | Action if violated |
|---|---|
| `ui-spec-gate` YAML block missing or incomplete | Do not deliver — Orchestrator cannot parse completeness gate |
| `ready_for_development: true` with any `status: partial` | Blocked — set `partial_release_notes` and keep `ready_for_development: false` — no Task Contract released with partially specified screen |
| `bdd_scenarios_covered` has `coverage: missing` | Blocked — flag Warning for Spec Team; do not release affected Task Contract |
| UI-NN state from §2 missing in spec | Flag as `Warning` and do not release to Developer |
| State added that does not exist in §2 | Remove it — escalate to Spec Team via Warning if the state seems necessary |
| Error message text paraphrased (not from §6) | Replace with exact §6 text before delivering |
| Text with "Lorem ipsum" or "Click here" | Replace with domain terminology |
| Library component not referenced by name | Fix before delivering |
| Token invented or hardcoded value used | Replace with token from `design-system/tokens.md` or flag Warning |
| Absolute-ban anti-pattern in spec (`side-tab`, `gradient-text`) | Remove before delivery — these are blocked by `u-ui-design/anti-patterns.md` regardless of design intent |
| Slop-category anti-pattern in spec (`border-accent-on-rounded`, `bounce-easing`) | Flag as Warning — must be addressed before delivery but do not constitute an absolute block |
| Large Epic (5+ Task Contracts) — partial delivery | Specify which Task Contracts can proceed; never release a Task Contract with a partially specified screen |
