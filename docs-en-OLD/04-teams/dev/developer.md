# Developer Agent

Implements code for Task Contracts. Exists in two variants:
- `u-be-developer.md` -- Backend implementation
- `u-fe-developer.md` -- Frontend implementation

## Responsibilities

- Implement one Task Contract at a time
- Follow project conventions from CLAUDE.md
- Consume the `execution_contract` YAML block from the Task Contract
- Handle bug corrections from QA rework cycles
- Generate delivery artifacts
- Report infrastructure dependencies or blockers

## Execution flow

1. **Discovery** -- Read Task Contract and all files listed in `execution_contract.input.references`
2. **Interpret TC** -- Parse `execution_contract`: `objective`, `constraints`, `validation.criteria`, `input.known_context`
3. **Verify dependencies** -- Check infrastructure/backend prerequisites; if missing → return `blocked-report.yaml`
4. **Plan** -- Define implementation approach
5. **Implement** -- Write code following project conventions
6. **Self-review** -- Pre-delivery checklist (tests, edge cases, spec compliance)

## Traceability

- **Backend**: Each implementation traces to UC-NN and BR-NN from specs (via `execution_contract.input.references`)
- **Frontend**: Each implementation traces to UI-NN from feature specs (via `execution_contract.input.references`)

## Pre-delivery checklist

Before generating the delivery file, the Developer verifies:
- All acceptance criteria met
- Tests written and passing
- Edge cases covered
- Spec compliance verified
- No hardcoded values or secrets

## Dependency reporting

When the Developer encounters a blocker it returns `blocked-report.yaml` (schema-validated) and generates a pending items file:
- **Backend**: `us-XX-infra-pending-items.md` (infrastructure dependencies)
- **Frontend**: `us-XX-backend-pending-items.md` (backend API dependencies)

These files are permanent and not archived. The `us-XX` prefix is kept for historical compatibility — the XX matches the Task Contract sequence number.

## Embedded skills

- **Development skill** (`u-be-development` / `u-fe-development`) -- Coding patterns, naming conventions, folder structure, error handling
- **Standards skill** (`u-be-standards` / `u-fe-standards`) -- Mandatory tests per Task Contract type, edge-case checklist, quality criteria

## Output

- Implemented code (routes, services, components, pages, etc.)
- `{SESSIONS_DIR}/{SESSION}/us-XX-delivery.md` -- Delivery file (archived to `_temp/` after QA)
- `{SESSIONS_DIR}/{SESSION}/us-XX-pending-items.md` -- Blockers (permanent, if applicable)
