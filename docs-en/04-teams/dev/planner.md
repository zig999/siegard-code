# Planner Agent

Transforms requirements into a structured backlog with Epics and User Stories. Exists in two variants (frontend and backend) that share the core `u-planning` skill.

## Responsibilities

- Determine operating mode (spec-first, improve, bug)
- Understand the domain context
- Define Epics as coherent feature increments
- Break Epics into INVEST-compliant Stories
- Map dependencies between Stories
- Generate the complete backlog

## Operating modes

| Mode | Input | Story anchoring |
|------|-------|-----------------|
| **Spec-first** | Approved specs | Each Story anchored to UC-NN |
| **Improve** | `improve##.md` files | Stories from improvement requests |
| **Bug** | `bug##.md` files | P0/P1 bug fix Stories with origin tracing |

## Execution flow

1. Determine mode from available artifacts
2. Understand domain (read CLAUDE.md, specs, or improve/bug files)
3. Define Epics (group related functionality)
4. Break into Stories (INVEST criteria, granularity rules)
5. Map dependencies (blocked-by relationships)
6. Validate completeness

### Frontend-specific additions
- Track screens and navigation flows alongside Epics/Stories
- Inventory existing components and patterns
- Identify regression risks

### Existing project handling
- Inventory existing code structure before planning
- Consider migration and backward compatibility

## Embedded skill

`u-planning` -- Provides canonical Epic/Story templates, INVEST framework checklist, granularity rules, P0/P1/P2 priority system, dependency map format, and journey map structure.

## Fullstack-specific behavior

When activated in a `domain: fullstack` session, the Planner generates a unified backlog where each Story includes a `scope:` field (`backend`, `frontend`, or `both`). Stories with `scope: both` are split into linked pairs -- one backend and one frontend -- with an explicit dependency (FE depends on BE). Backend stories are ordered before frontend stories that depend on them.

## Output

`{SESSIONS_DIR}/{SESSION}/backlog.md` containing:
- Personas
- Epics with descriptions
- Story overview table (ID, title, Epic, priority, scope, status, dependencies)
- Dependency map
- Journey maps
- Open questions (if any)
