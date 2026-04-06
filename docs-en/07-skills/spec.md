# Spec Pipeline Skills

Skills used by agents in the Spec team.

## u-spec-globals

**Consumers**: All Spec agents

Shared resources used across the entire spec pipeline:
- `conventions.md` -- Project-level conventions
- `error-codes.md` -- Global error code catalog with standard format
- `glossary.md` -- Domain-specific term definitions

## u-spec-writing

**Consumer**: Spec Writer

Capabilities and rules for specification authoring:
- OpenAPI 3.0 specification structure
- Domain modeling patterns
- Use Case (UC-NN) definition format
- Error code mapping to HTTP status codes
- Schema definition with examples

## u-spec-review

**Consumer**: Spec Reviewer

Quality checklists and approval criteria:
- OpenAPI compliance checklist
- Error coverage verification
- UC <-> OpenAPI consistency checks
- Ambiguity detection rules
- Severity classification (blocking, major, minor)

## u-spec-validation

**Consumer**: Spec Validator

Cross-reference validation rules:
- UC <-> BR <-> OpenAPI consistency
- Error code completeness
- State machine coverage
- Orphan spec detection
- Dependency validation

## u-spec-templates

**Consumers**: Spec Writer, Front Spec Agent

5 artifact templates defining the structure for each spec type:

1. **TEMPLATE.spec.md** -- Vision, actors, use cases, business rules, state machines, error codes, out-of-scope, glossary
2. **TEMPLATE.back.md** -- Tech stack, data model, business rules, states, events, integrations
3. **TEMPLATE.front.md** -- Tech stack, state management, data fetching, error handling, components
4. **TEMPLATE.screen.md** -- Domains consumed, UI states, behaviors, requests, validations, error mapping
5. **TEMPLATE.flow.md** -- Screens involved, happy path, alternatives, navigation rules

Additional design system templates:
- **TEMPLATE.design-system/** -- 5 files: `_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`
- **TEMPLATE.design-system-rules.md** -- Token and rule reference
