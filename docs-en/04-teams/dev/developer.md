# Developer Agent

Implements code for User Stories. Exists in two variants:
- `u-be-developer.md` -- Backend implementation
- `u-fe-developer.md` -- Frontend implementation

## Responsibilities

- Implement one User Story at a time
- Follow project conventions from CLAUDE.md
- Handle bug corrections from QA rework cycles
- Generate delivery artifacts
- Report infrastructure dependencies or blockers

## Execution flow

1. **Discovery** -- Read Story and referenced spec artifacts
2. **Interpret Story** -- Understand acceptance criteria and traceability (UC-NN for BE, UI-NN for FE)
3. **Verify dependencies** -- Check infrastructure/backend prerequisites
4. **Plan** -- Define implementation approach
5. **Implement** -- Write code following project conventions
6. **Self-review** -- Pre-delivery checklist (tests, edge cases, spec compliance)

## Traceability

- **Backend**: Each implementation traces to UC-NN and BR-NN from specs
- **Frontend**: Each implementation traces to UI-NN from screen specs

## Pre-delivery checklist

Before generating the delivery file, the Developer verifies:
- All acceptance criteria met
- Tests written and passing
- Edge cases covered
- Spec compliance verified
- No hardcoded values or secrets

## Dependency reporting

When the Developer encounters a blocker:
- **Backend**: Generates `us-XX-infra-pending-items.md` (infrastructure dependencies)
- **Frontend**: Generates `us-XX-backend-pending-items.md` (backend API dependencies)

These files are permanent and not archived.

## Embedded skills

- **Development skill** (`u-be-development` / `u-fe-development`) -- Coding patterns, naming conventions, folder structure, error handling
- **Standards skill** (`u-be-standards` / `u-fe-standards`) -- Mandatory tests per Story type, edge-case checklist, quality criteria

## Output

- Implemented code (routes, services, components, pages, etc.)
- `{SESSIONS_DIR}/{SESSION}/us-XX-delivery.md` -- Delivery file (archived to `_temp/` after QA)
- `{SESSIONS_DIR}/{SESSION}/us-XX-pending-items.md` -- Blockers (permanent, if applicable)
