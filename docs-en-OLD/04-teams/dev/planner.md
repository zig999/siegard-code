# Planner Agent

Transforms requirements into a structured backlog with Epics and Task Contracts. Exists in two variants (frontend and backend) that share the core `u-planning` skill.

## Responsibilities

- Determine operating mode (spec-first, improve, bug)
- Understand the domain context
- Define Epics as coherent feature increments
- Break Epics into Task Contracts (TC-XX)
- Populate `execution_contract` YAML block for each Task Contract
- Map dependencies between Task Contracts
- **[Spec-first FE] Run Component Spec Gate** before finalizing the backlog
- Generate the complete backlog

## Operating modes

| Mode | Input | TC anchoring |
|------|-------|--------------|
| **Spec-first (BE)** | Approved backend specs | Each Task Contract anchored to UC-NN |
| **Spec-first (FE)** | Approved feature specs | Backend TCs to UC-NN; frontend TCs reference FEAT-NN and §9 BDD Scenarios via `bdd_ref` (never duplicated inline) |
| **Improve** | `improve##.md` files | Task Contracts from improvement requests |
| **Bug** | `bug##.md` files | P0/P1 bug fix Task Contracts with origin tracing |

## Execution flow

1. Determine mode from available artifacts
2. Read `decisions.md` if it exists — active decisions may affect Task Contract scope
3. Understand domain (read CLAUDE.md, specs, or improve/bug files)
4. Define Epics (group related functionality)
5. Break into Task Contracts (granularity rules: S or M estimate, never L)
6. Populate `execution_contract` YAML for each Task Contract
7. Map dependencies (blocked-by relationships)
8. **[Spec-first FE] Component Spec Gate** (Step 4B — see below)
9. Validate completeness

### Frontend-specific additions
- Track features and navigation flows alongside Epics/Task Contracts
- Inventory existing components and patterns
- Identify regression risks

### Existing project handling
- Inventory existing code structure before planning
- Consider migration and backward compatibility

## Component Spec Gate (Step 4B — Spec-first FE only)

After generating Task Contracts, the Planner checks whether all required component specs exist:

1. For each Task Contract with UI work, read **§10 of the corresponding `feature.spec.md`**
2. For each component listed with Action = "create", check if `{SPECS_DIR}/front/components/{name}.component.spec.md` exists
3. If it does not exist:
   - **P0 Task Contract**: create a Spec TC (type: "Spec") with the same priority, block the dependent Task Contracts on it, and flag to human before proceeding
   - **P1/P2 Task Contract**: log a warning in the backlog; the Developer will flag it during implementation
4. BDD scenarios from §9 of `feature.spec.md` are referenced in Task Contract `bdd_ref` as "FEAT-NN §9" — not duplicated inline

## Embedded skill

`u-planning` — Provides canonical Epic/Task Contract templates, granularity rules, P0/P1/P2 priority system, dependency map format, and journey map structure.

## Fullstack-specific behavior

When activated in a `domain: fullstack` session, the Planner generates a unified backlog where each Task Contract includes a `scope:` field (`backend`, `frontend`, or `both`). Task Contracts with `scope: both` are split into linked pairs — one backend and one frontend — with an explicit dependency (FE depends on BE). Backend Task Contracts are ordered before frontend Task Contracts that depend on them.

## Task Contract Types

| Type | When to use |
|------|------------|
| `Feature` | New functionality anchored to UC-NN or FEAT-NN |
| `Improve` | Incremental improvement from `improve##.md` |
| `Bugfix` | Fix for a reported or regression bug |
| `Refactoring` | Internal restructuring with no observable behavior change |
| `Spec` | Writing a missing `component.spec.md` — auto-created by Step 4B Component Spec Gate |
| `Tech Debt` | Addressing documented technical debt without feature scope |

## execution_contract fields

Each Task Contract contains an `execution_contract` YAML block populated by the Planner:

| Field | Description |
|-------|-------------|
| `exec_type` | Mapped from Task Contract type |
| `objective` | Single objective for the Developer |
| `input.references` | Exact file paths + sections the Developer must read |
| `input.known_context` | Pre-resolved context to reduce token usage |
| `input.assumptions_allowed` | Whether the Developer may infer missing details |
| `constraints` | Shared components or rules that constrain implementation |
| `validation.criteria` | Objective acceptance criteria |
| `fallback.on_missing_input` | Always `blocked` — returns `blocked-report.yaml` |

## Output

`{SESSIONS_DIR}/{SESSION}/backlog.md` containing:
- Personas
- Epics with descriptions
- Task Contract overview table (ID, title, type, Epic, priority, scope, status, dependencies)
- Dependency map
- Journey maps
- Component spec gap warnings (if any, from Step 4B)
- Open questions (if any)
