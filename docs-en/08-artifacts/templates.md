# Spec Templates

Specification templates stored in `{SPECS_DIR}/_templates/`. Used by the Spec Writer and Front Spec Agent.

## 1. TEMPLATE.spec.md

Domain specification template:
- Vision and scope
- Actors/personas
- Use Cases (UC-NN) with pre/post conditions
- Business Rules summary
- State machine overview
- Error codes
- Out-of-scope
- Glossary

## 2. TEMPLATE.back.md

Backend technical specification template:
- Technology stack reference (from CLAUDE.md)
- Data model (entities, relationships, indexes)
- Business Rules (BR-NN) with implementation detail
- State Machines (ST-NN) with transitions
- Domain Events (EV-NN) with payloads
- Integration points
- Technical constraints

## 3. TEMPLATE.front.md

Global frontend specification template (one per project):
- Technology stack reference (from CLAUDE.md)
- Global routing conventions
- State management strategy (includes optional **HTTP Adapter** sub-section for global response transforms)
- Component architecture patterns
- Global error handling
- Global accessibility requirements
- **Permitted and prohibited libraries** (project-specific)
- Changelog

## 4. TEMPLATE.feature.spec.md

Feature specification template (one per URL/route):
- **§1 Consumed Endpoints** — Domain | operationId | Purpose only. Method+Path and Auth are in `openapi.yaml` — not duplicated here.
- **§2 Feature States (UI-NN)** — with explicit Entry condition; minimum: idle, loading, success, error, empty
- **§3 State Transition Table** — From | Trigger | To | Side Effect (cache invalidation, redirects, analytics)
- **§4 Requests, Order and Cache** — parallel/sequential, priority, TTL, revalidation. Optional sub-sections: **Response transforms** (field rename, cast, derive — omit if not needed) and **Composed models** (multi-endpoint merge — omit if not needed)
- **§5 Input Validations** — User message and When to validate only. Technical constraints (required, minLength, pattern, enum) stay in `openapi.yaml` requestBody schema — not duplicated here.
- **§6 API Error → UI Mapping** — error.code to display, message, and action
- **§7 Shared Components Used** — only `src/components/` global components. Optional sub-section: **Component adapters** (API response → Props Contract mapping — omit if shapes match directly)
- **§8 Feature Accessibility** — feature-specific checklist
- **§9 BDD Scenarios** — feature invariants (not Task Contract validation criteria); minimum: happy path + critical error
- **§10 Components to Create/Update** — Component Name | Action | Feature | Rationale
- Changelog

> **Note:** replaced `TEMPLATE.screen.md` (deleted). Granularity: 1 feature = 1 URL. openapi.yaml is the authoritative API contract — feature.spec.md references it, never duplicates it.

## 5. TEMPLATE.component.spec.md

Shared component contract template (conditional — created only when component qualifies):
- **§1 Purpose and Responsibilities** — what it does + what it deliberately does NOT do
- **§2 Props Contract** — binding: Prop Name | Type | Required | Default | Description
- **§3 Component States** — internally managed states only
- **§4 Events Emitted** — Event Name | Payload Type | When emitted | Consumer action
- **§5 Variants and Compositions** — Variant | Props combination | Usage context
- **§6 Do / Don't** — correct vs incorrect usage
- **§7 BDD Scenarios** — minimum 3: default render + error state + keyboard navigation
- **§8 Accessibility Contract** — aria strategy, keyboard interaction, focus management
- Changelog (Props Contract changes require a version entry)

> **Creation criterion:** used in 2+ features OR has complex internal logic.

## 6. TEMPLATE.flow.md

Navigation flow template:
- Features involved (with route and `.feature.spec.md` reference)
- Happy path (step-by-step)
- Alternative paths
- Navigation rules and guards (FL-NN)
- Deep links
- Data persisted between features

## 7. TEMPLATE.decisions.md

Architecture decision log template:
- One DEC-NN entry per decision
- Fields: Date, Status, Context, Decision, Alternatives considered, Rationale, Impact on specs
- Superseded decisions are never edited — a new entry is created

## Design system templates

Additional templates for the design system reference:
- **TEMPLATE.design-system/**: `_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`
- **TEMPLATE.design-system-rules.md**: Token and rule quick reference

---

# Dev Pipeline Templates

Operational templates used by Dev team agents. Located in `.claude/skills/u-shared-templates/`, `.claude/skills/u-fe-templates/`, and `.claude/skills/u-bug-report/`.

## 1. task_contract.yaml

**Produced by**: Planner Agent | **Consumed by**: Orchestrator, Developer
**Schema**: `task_contract.schema.yaml` | **Layer**: semi-permanent

The canonical planning unit that replaces User Story. Fields:

| Field | Type | Rules |
|-------|------|-------|
| `id` | `TC-NN` | Sequential, project-scoped |
| `epic` | `EPIC-NN` | References parent Epic |
| `origin` | enum | `UC-NN \| improve-NN \| bug-NN \| component-spec-gate \| direct` |
| `type` | enum | `feature \| bugfix \| refactoring \| spec \| tech_debt` |
| `priority` | enum | `P0 \| P1 \| P2` |
| `scope` | enum | `frontend \| backend` — **never** `both` (split into two TCs) |
| `estimate` | enum | `S \| M` — **never** `L` (split into two TCs) |
| `dependencies` | array | TC-NN ids or `[]` |
| `persona_coverage` | array | Actors from spec.md §2 |
| `bdd_ref` | string | `FEAT-NN §9` or `null` |
| `execution_contract` | object | See below |

`execution_contract` sub-fields: `exec_type`, `objective`, `input.references`, `input.known_context`, `input.assumptions_allowed`, `constraints`, `output`, `validation.criteria`, `fallback`.

`fallback.on_missing_input` is always `blocked` — never partial execution.

## 2. blocked-report.yaml

**Produced by**: any agent that cannot execute | **Consumed by**: calling Orchestrator
**Schema**: `blocked-report.schema.yaml` | **Layer**: ephemeral — never committed

Returned directly to the Orchestrator when preconditions are unmet. Fields:

| Field | Description |
|-------|-------------|
| `blocked.id` | `BLK-YYYYMMDD-HHMMSS` |
| `status` | `blocked \| failed` |
| `reason` | Single objective sentence |
| `missing_inputs` | Array: `field`, `expected`, `source` |
| `conflicts` | Array: `id`, `description`, `location` |
| `resolution` | `required_action`, `escalate_to` (orchestrator or human) |

`missing_inputs` and `conflicts` are mutually exclusive — only one applies per report.

## 3. cr-template.yaml (Change Request)

**Produced by**: Developer or QA when a spec issue is found | **Consumed by**: Orchestrator → Spec Team
**Schema**: `cr.schema.yaml` | **Layer**: semi-permanent

Raised when implementation reveals a spec problem. Fields:

| Field | Values | Description |
|-------|--------|-------------|
| `id` | `CR-NN` | Sequential, project-scoped |
| `type` | `spec_gap \| spec_error \| infeasibility \| design_conflict` | Nature of the issue |
| `artifact.path` | file path | Spec file with the problem |
| `artifact.section` | e.g. `§3 Business Rules` | Exact section |
| `impact.dev_blocked` | bool | Whether Developer cannot proceed |
| `impact.stories_affected` | array | Other TCs impacted |
| `impact.scope` | `low \| medium \| high` | Blast radius |
| `resolution.status` | `open \| accepted \| rejected \| deferred` | Set by Orchestrator |

## 4. delivery-gate.md

**Produced by**: Developer (embedded at top of `us-XX-delivery.md`) | **Consumed by**: QA Agent (pre-test gate)
**Layer**: semi-permanent

YAML block placed at the very top of every delivery file. QA reads it before running any tests.

Key fields:

| Field | Description |
|-------|-------------|
| `status` | `implemented \| implemented_with_caveats` |
| `tests.last_local_run` | `passed \| failed` — QA re-runs and verifies |
| `acceptance_criteria.uncovered` | List of unimplemented criteria — each logged as HIGH bug |
| `spec_divergences.items` | Required when `count > 0`; typed as `necessary \| accidental` |
| `qa_ready` | `false` only when QA structurally cannot proceed (broken test command, missing environment) |

QA behavior: `qa_ready: false` → blocked report immediately, no test run. Missing gate → treated as `qa_ready: false`.

## 5. handoff-manifest.yaml

**Produced by**: Spec Orchestrator (after Validator returns VALID) | **Consumed by**: Dev Orchestrators (session start)
**Schema**: `handoff-manifest.schema.yaml` | **Layer**: semi-permanent — stored at `{SPECS_DIR}/handoff-manifest.yaml`

Formal artifact transfer from Spec team to Dev team. Fields:

| Field | Description |
|-------|-------------|
| `handoff.type` | `new_domain \| major_evolution \| fast_track \| reverse_eng` |
| `domains` | Array: name, spec/back/openapi versions, compliance report path |
| `frontend_artifacts` | front.md version, feature specs, flows (omitted for BE-only handoffs) |
| `backend_package` / `frontend_package` | Artifact paths with type classification |
| `change_summary.dev_impact` | `no_action \| reevaluate_stories \| stop_domain_stories` |

## 6. validation-result.yaml

**Produced by**: Spec Validator | **Consumed by**: Spec Orchestrator (handoff gate)
**Schema**: `validation-result.schema.yaml` | **Layer**: permanent — stored at `{SPECS_DIR}/_validation/{domain}-validation-result.yaml`

Generated after every validation run (incremental and final); overwrites previous result.

| Field | Description |
|-------|-------------|
| `status` | `VALID \| INVALID` |
| `handoff_allowed` | `true` only when `status: VALID` and `blocking_count: 0` |
| `blocking_issues` | Array: `id`, `type`, `source`, `description`, `responsible`, `suggested_fix` |
| `warnings` | Array: `id`, `type`, `source`, `description` |

`responsible` field on each issue routes corrections to the exact agent (`u-spec-back`, `u-spec-front`, `u-spec-writer`).

## 7. session-decisions.md

**Produced by**: Orchestrator (append-only) | **Consumed by**: Orchestrator (session start — last 20 entries)
**Layer**: semi-permanent — versioned in repo, never ephemeral
**Path**: `{SESSIONS_DIR}/{SESSION}/session-decisions.md`

Cross-session persistent log that prevents repeated mistakes. Orchestrator writes on: escalation to human, architectural decisions, confirmed spec gaps, triage resolutions, QA root-cause findings. Rotate to `_archive/` after 300 entries.

| Column | Values |
|--------|--------|
| `Type` | `escalation \| arch-decision \| spec-gap \| triage-resolution \| qa-root-cause` |
| `Status` | `active \| superseded \| reverted` |

Developer agents are **read-only** on this file.

## 8. ui-epic.md

**Produced by**: UI Agent | **Consumed by**: Frontend Developer (per Task Contract)
**Layer**: semi-permanent — archived to `_temp/` after Epic completes
**Path**: `{SESSIONS_DIR}/{SESSION}/ui-epic-XX.md`

YAML gate block at the top (read by Orchestrator for coverage check) + Markdown body (read by Developer per screen). Gate fields: `tasks_covered`, `ui_nn_covered`, `bdd_scenarios_covered`, `ready_for_development`.

Body sections per screen: layout structure, components table, state specifications (one row per UI-NN), messages/text (exact text from §6), interaction behaviors, §9 BDD scenario coverage, token references.

## 9. bug.template.md

**Produced by**: `/u-bug-report` command | **Consumed by**: Planner (Bug mode)
**Layer**: semi-permanent — archived after Planner consumes
**Path**: `{SESSIONS_DIR}/{SESSION}/bug##.md`

Structured bug report generated via guided questionnaire. Fields: where, type (visual/UI tweak | incorrect behavior | integration error | not sure), reproduction steps, expected behavior, actual behavior, error message, open questions. The `type` field determines which pipeline the Planner uses (lean vs. full).
