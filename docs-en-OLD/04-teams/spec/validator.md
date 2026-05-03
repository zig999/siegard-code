# Spec Validator

Final quality gate in the spec pipeline. Performs cross-reference validation across all specification artifacts.

## Responsibilities

- Cross-validate consistency between UC, BR, UI, and error codes
- Detect orphan specs (referenced but not defined, or defined but not referenced)
- Validate design system completeness
- Validate BDD scenario coverage in feature specs
- Validate component spec coverage for qualifying components
- Generate coverage reports
- Persist validation reports for triage mode

## Validation modes

| Mode | Trigger | Scope |
|------|---------|-------|
| **Incremental** | After each `.back.md` completion | Single domain cross-validation |
| **Final** | After all artifacts complete (including frontend) | Full cross-reference validation |

## Cross-validation checks

- **UC <-> BR consistency** — Every UC has at least one BR, every BR references a UC
- **UC <-> OpenAPI consistency** — Every UC has a corresponding endpoint
- **Error codes** — All codes used in specs are in the global catalog
- **State machines** — All states have at least one transition, no dead-end states
- **Orphan specs** — No dangling references
- **Dependencies** — All cross-domain references are valid
- **Versioning** — Spec versions follow semantic versioning rules

## Frontend-specific checks (final phase)

- **Feature <-> domain consistency** — Every endpoint in §1 of a feature spec exists in the corresponding `openapi.yaml`
- **Error mapping coverage** — Every error.code in §6 of a feature spec exists in the global catalog
- **Minimum states** — Each feature spec (§2) covers at least: loading, success, error, empty
- **BDD coverage** — Each feature spec has at least 2 BDD scenarios in §9 (happy path + critical error) — missing scenarios are **warning-level**
- **Component spec coverage** — Shared components used in 2+ features that lack a `component.spec.md` — **warning-level**
- **Flow references** — Every feature referenced in flows has a corresponding `.feature.spec.md`
- **front.md stack** — Consistent with project's CLAUDE.md

## Design system validation

Checks that all 5 required files exist in `front/design-system/`:
- `_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`
- Changelog is populated
- All referenced tokens are cataloged
- `design-system-rules.md` is synchronized with `tokens.md`

## Persisted reports

Validation reports are saved to `{SPECS_DIR}/_validation/{domain}-validation.md` for use by the triage command (`/u-spec-triage`).

## Coverage report

When validation passes (VALID), the Validator generates a compliance report (`{SPECS_DIR}/compliance-report.md`) with:

| Metric | Total | Covered | Percentage |
|--------|-------|---------|------------|
| Use Cases (UC) | {N} | {N} | {N}% |
| Endpoints (OpenAPI) | {N} | {N} | {N}% |
| Business Rules (BR) | {N} | {N} | {N}% |
| Feature States (UI) | {N} | {N} | {N}% |
| BDD Scenarios (§9) | {N} | {N} | {N}% |
| Navigation Flows (FL) | {N} | {N} | {N}% |
| Error Codes | {N} | {N} | {N}% |

## Limits

- Never approve specs with blocking inconsistencies
- Missing BDD scenarios and missing component specs are **warnings**, not blockers
- Always generate a coverage map
- Max **2 invalidation cycles** per agent before escalation to human
