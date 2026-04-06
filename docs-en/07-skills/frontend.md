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

## u-fe-standards

**Consumers**: Frontend Developer, Frontend QA

Shared quality standards (single source of truth for both agents):
- Mandatory tests per Story type
- Universal edge-case checklist
- Test quality criteria
- Accessibility requirements
- Styling approach enforcement (reads from project configuration)

## u-fe-qa-docs

**Consumer**: Frontend QA

Testing types, verification scope, and documentation:
- Test type matrix (unit, component, integration, E2E)
- Coverage requirements per Story type
- Accessibility verification (keyboard, ARIA, focus)
- Visual regression testing
- Bug report template
- QA report format (`us-XX-qa.md`)

## u-fe-ui

**Consumer**: UI Agent

Templates and quality rules for visual specifications:
- Screen map templates
- Component table format
- State table format (loading, empty, error, success)
- Interaction description patterns
- Design system token reference format
- Responsiveness requirements

## u-fe-templates

**Consumers**: Frontend Developer, Frontend QA (on-demand)

On-demand templates for delivery and reporting:
- `delivery.md` -- Story delivery file template
- `backend-pending-items.md` -- Backend dependency report template
- `qa-report.md` -- QA report template
