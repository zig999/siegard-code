# Spec Pipeline Skills

Skills used by agents in the Spec team.

## u-spec-globals

**Consumers**: All Spec agents

Shared resources used across the entire spec pipeline:
- `conventions.md` — Project-level conventions (identifier prefixes, versioning, naming)
- `error-codes.md` — Global error code catalog with standard format
- `glossary.md` — Domain-specific term definitions

## u-spec-writing

**Consumer**: Spec Writer

Capabilities and rules for specification authoring:
- OpenAPI 3.0 specification structure
- Domain modeling patterns
- Use Case (UC-NN) definition format
- Error code mapping to HTTP status codes
- Schema definition with examples
- **Feature Spec guidance** — granularity rule (1 feature = 1 URL), section-by-section writing instructions, BDD scenario format
- **Component Spec guidance** — when to create, Props Contract format, State/Event documentation
- **Decisions Log guidance** — when to write DEC-NN, what NOT to record, supersession rule

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
- Orphan spec detection (including FL referencing features without `.feature.spec.md`)
- Dependency validation
- BDD coverage check (§9 minimum: happy path + critical error)
- Component spec coverage check (2+ features using same component)

## u-spec-templates

**Consumers**: Spec Writer, Front Spec Agent

7 artifact templates defining the structure for each spec type:

1. **TEMPLATE.spec.md** — Vision, actors, use cases, business rules, state machines, error codes, out-of-scope, glossary
2. **TEMPLATE.back.md** — Tech stack, data model, business rules, states, events, integrations
3. **TEMPLATE.front.md** — Tech stack, global routing, state management, error handling, component architecture, permitted/prohibited libraries
4. **TEMPLATE.feature.spec.md** — §1 Endpoints, §2 States (with Entry condition), §3 Transitions (with Side Effect), §4 Cache, §5 Validations, §6 Error mapping, §7 Shared Components, §8 Accessibility, §9 BDD Scenarios, §10 Components to Create
5. **TEMPLATE.component.spec.md** — §1 Purpose, §2 Props Contract, §3 States, §4 Events, §5 Variants, §6 Do/Don't, §7 BDD, §8 Accessibility Contract
6. **TEMPLATE.flow.md** — Features involved, happy path, alternatives, navigation rules, deep links
7. **TEMPLATE.decisions.md** — DEC-NN format with Date, Status, Context, Decision, Alternatives, Rationale, Impact on specs

Additional design system templates:
- **TEMPLATE.design-system/** — 5 files: `_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`
- **TEMPLATE.design-system-rules.md** — Token and rule reference
