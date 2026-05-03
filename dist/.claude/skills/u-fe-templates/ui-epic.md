# Template: ui-epic-XX.md

Save to `$SESSION_DIR/ui-epic-$ORCH_TASK_ID.md` (e.g., EPIC-01 → `ui-epic-dev_epic_001.md`).

Producer: `u-fe-ui` agent.
Consumers: `u-fe-orchestrator-core` (UI spec completeness gate), `u-fe-developer` (screen extraction per Task Contract).

YAML gate first — Orchestrator reads to validate coverage without parsing markdown body. Then markdown body consumed by Developer per screen section.

> **Schema:** the YAML gate block must conform to `.claude/skills/u-shared-templates/ui-agent-output.schema.yaml`. If the UI Agent cannot produce a conforming gate (e.g., design system missing), it MUST emit a design system gate report following `.claude/skills/u-shared-templates/design-system-gate-report.schema.yaml` instead.

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
partial_release_notes: ""   # populated when status: partial for any task
```

# UI Spec — EPIC-XX: [Epic Name]

> layer: semi-permanent | created: YYYY-MM-DD | tasks: TC-XX, TC-YY, TC-ZZ
> feature specs: feature-name.feature.spec.md | flows: feature-name.flow.md

---

## Screen map

| Screen (route) | Task Contract(s) | Feature | UI states | FL-NN flows | Type |
|----------------|-----------------|---------|-----------|-------------|------|
| [Route/Page] | TC-XX | [feature] | UI-01, UI-02, UI-03 | FL-01, FL-02 | new \| modified |

---

## Screen specifications

### Screen: [Route / Page Name]

**Task Contract(s):** TC-XX
**Feature:** [feature-name] (from feature.spec.md)
**Persona:** [Persona as defined in CLAUDE.md or specs]
**User goal:** [what they must accomplish — domain language, no placeholders]
**UI states covered:** UI-01, UI-02, UI-03, UI-04 (from feature.spec.md §2)
**FL-NN flows handled:** FL-01 (happy path), FL-02 (error path)

---

#### Layout structure

```
+----------------------------------+
| HEADER: [logo] [nav] [user]      |
+----------------------------------+
| SIDEBAR        | CONTENT          |
| - item 1       | [title]          |
| - item 2       | [main area]      |
+----------------------------------+
```

---

#### Components

| Component | Type | Content | Default state |
|-----------|------|---------|---------------|
| [Name] | Button \| Input \| Card \| Table \| Modal | [what it displays] | active \| disabled \| loading |

> Reference component library components by exact name (e.g., `<Button variant="primary">`, `<DataTable>`).
> Components from §7 of feature.spec.md must use Props Contract from component.spec.md — do not invent props.

---

#### Visual hierarchy

| Priority | Element | Reason |
|----------|---------|--------|
| 1 — primary | [element] | [why most prominent] |
| 2 — secondary | [element] | [role] |
| 3 — supporting | [element] | [role] |

---

#### State specifications

| State ID | Name | Trigger (locked — §3) | Layout change | Key component | Visual note |
|----------|----- |-----------------------|---------------|---------------|-------------|
| UI-01 | [name from §2] | [trigger from §3] | [what changes] | `<ComponentName>` | `--token-name` |
| UI-02 | [name — loading] | request in progress | skeleton \| spinner | `<Skeleton>` | `--token-name` |
| UI-03 | [name — empty] | no data returned | empty state | `<EmptyState>` | [message from §9 or §6] |
| UI-04 | [name — error] | error.code = XXX (§6) | error banner | `<Alert variant="error">` | [exact text from §6] |
| UI-05 | [name — success] | [trigger] | toast \| banner \| redirect | `<Toast>` | [message] |

> All UI-NN states from §2 must appear. Missing a state blocks development.
> Error message text must match §6 exactly — do not paraphrase.

---

#### Messages and text

| Element | Text source | Text |
|---------|-------------|------|
| Screen title | domain terminology | "[text]" |
| Primary action | domain terminology | "[label]" |
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

| Scenario | Title | UI state(s) exercised | Coverage |
|----------|---------|-----------------------|----------|
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

## Visual guidelines — EPIC-XX

> All tokens sourced from `{SPECS_DIR}/front/design-system/`.

| Element | Semantic token | Epic-specific usage note |
|---------|---------------|--------------------------|
| [element] | `--token-name` | [context] |

---

## Open questions

| ID | Screen | Issue | Blocking |
|----|--------|-------|----------|
| WRN-01 | [Screen] | [issue description] | true \| false |

````
