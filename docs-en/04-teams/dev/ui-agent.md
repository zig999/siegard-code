# UI Agent

Frontend-only agent that transforms Stories into detailed visual specifications before the Developer implements them.

## Responsibilities

- Generate `ui-epic-XX.md` from screen and flow specifications
- Define layout, component hierarchy, and states per screen
- Ensure design system compliance
- Specify responsiveness requirements
- Detail interaction behaviors

## Activation rule

- **Frontend pipeline only** -- Not used in backend pipeline
- Activated after the Planner and before the Developer
- Requires the design system reference to be available before producing specs

## Execution flow

1. Read assigned Stories from backlog
2. Load relevant screen (`.screen.md`) and flow (`.flow.md`) specifications
3. Reference the design system (`front/design-system/`)
4. Generate `ui-epic-XX.md` with visual specifications per Story
5. For Epics with 3+ Stories, deliver incrementally

## Screen specification template

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
