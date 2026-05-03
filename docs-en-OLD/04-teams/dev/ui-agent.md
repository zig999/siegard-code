# UI Agent

Frontend-only agent that transforms Task Contracts into detailed visual specifications before the Developer implements them.

## Responsibilities

- Generate `ui-epic-XX.md` from feature and flow specifications
- Define layout, component hierarchy, and states per screen
- Ensure design system compliance
- Specify responsiveness requirements
- Detail interaction behaviors

## Activation rule

- **Frontend pipeline only** -- Not used in backend pipeline
- Activated after the Planner and before the Developer
- Requires the design system reference to be available before producing specs

## §9 BDD Scenarios — acceptance contract

The BDD scenarios in §9 of `feature.spec.md` are the **acceptance contract** for UI specifications:
- The UI spec must make every §9 scenario visually realizable
- If a new UI state is needed beyond what §2 specifies, flag it with a Warning — do not invent states silently
- §9 scenarios are feature invariants; a Task Contract cannot be approved if any of them is broken

## Execution flow

1. Read assigned Task Contracts from backlog
2. Load relevant feature spec (`.feature.spec.md`) — all sections except §7 and §10; load `component.spec.md` (§2+§3+§5) for shared components referenced in §7
3. Reference the design system (`front/design-system/`)
4. Generate `ui-epic-XX.md` with visual specifications per Task Contract; verify each §9 scenario is visually realizable
5. For Epics with 3+ Task Contracts, deliver incrementally

## Feature specification template

Each screen in the UI spec includes:
- Layout structure and component hierarchy
- Component table (name, type, behavior)
- State table (loading, empty, error, success)
- Interaction descriptions
- UX principles and accessibility notes
- Design system token references

## Embedded skill

`u-fe-ui` -- Templates, naming conventions, and quality rules for UI specifications. Covers screen maps, component tables, state tables, interaction descriptions, and design system tokens.

## Output

`{SESSIONS_DIR}/{SESSION}/ui-epic-XX.md` -- Visual specification consumed by the Developer. Archived to `_temp/` after the Epic is complete.
