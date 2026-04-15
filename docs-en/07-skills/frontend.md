# Frontend Pipeline Skills

Skills used by agents in the frontend Dev team.

## u-fe-development

**Consumer**: Frontend Developer

Coding patterns and conventions for frontend implementation:
- Folder structure and naming conventions
- Component, page, and navigation patterns
- State management patterns (reads project's chosen library from CLAUDE.md)
- Error handling patterns (project's configured logger, structured errors)
- Commit conventions
- Backend dependency verification
- **Component spec gate** — before coding, verify `component.spec.md` for each component from `src/components/` consumed by the Task Contract; if it exists, §2 Props Contract is binding
- **Anti-patterns (state)** — prohibited: duplicating server state in Zustand, using Context for server cache
- **Anti-patterns (export)** — prohibited: default exports for components (blocks tree-shaking and automated refactoring); always named exports
- **Anti-patterns (component)** — prohibited: component with more than 1 responsibility without extraction, prop drilling beyond 2 levels without store/context

## u-fe-standards

**Consumers**: Frontend Developer, Frontend QA

Shared quality standards (single source of truth for both agents):
- Mandatory tests per Task Contract type
- Universal edge-case checklist
- Test quality criteria
- Accessibility requirements
- Styling approach enforcement (reads from project configuration)

## u-fe-qa-docs

**Consumer**: Frontend QA

Testing types, verification scope, and documentation:
- Test type matrix (unit, component, integration, E2E)
- Coverage requirements per Task Contract type
- **BDD Scenario verification** (§9 of `feature.spec.md`) — primary verification criterion; executed before Task Contract validation criteria
- **Component spec BDD** (§7 of `component.spec.md`) — verified when Task Contract creates or modifies a shared component
- Accessibility verification (keyboard, ARIA, focus)
- Visual regression testing
- Bug report template
- QA report format (`us-XX-qa.md`)
- **Spec-first mode checklist**: Step 1 — §9 BDD scenarios (primary gate); Step 2 — feature spec §2/§3/§5/§6 conformance; Step 3 — component spec conformance; Step 4 — Task Contract validation criteria and other checks

## u-fe-ui

**Consumer**: UI Agent

Templates and quality rules for visual specifications:
- Screen map templates
- Component table format
- State table format (loading, empty, error, success)
- Interaction description patterns
- Design system token reference format
- Responsiveness requirements
- §9 BDD Scenarios are the acceptance contract — UI spec must make each scenario visually realizable; new UI states not in §2 require a Warning flag

## u-fe-templates

**Consumers**: Frontend Developer, Frontend QA (on-demand)

On-demand templates for delivery and reporting:
- `delivery.md` — Task Contract delivery file template
- `backend-pending-items.md` — Backend dependency report template
- `qa-report.md` — QA report template
