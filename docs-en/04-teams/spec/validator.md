# Spec Validator

Final quality gate in the spec pipeline. Performs cross-reference validation across all specification artifacts.

## Responsibilities

- Cross-validate consistency between UC, BR, UI, and error codes
- Detect orphan specs (referenced but not defined, or defined but not referenced)
- Validate design system completeness
- Generate coverage reports
- Persist validation reports for triage mode

## Validation modes

| Mode | Trigger | Scope |
|------|---------|-------|
| **Incremental** | After each `.back.md` completion | Single domain cross-validation |
| **Final** | After all artifacts complete (including frontend) | Full cross-reference validation |

## Cross-validation checks

- **UC <-> BR consistency** -- Every UC has at least one BR, every BR references a UC
- **UC <-> OpenAPI consistency** -- Every UC has a corresponding endpoint
- **Error codes** -- All codes used in specs are in the global catalog
- **State machines** -- All states have at least one transition, no dead-end states
- **Orphan specs** -- No dangling references
- **Dependencies** -- All cross-domain references are valid
- **Versioning** -- Spec versions follow semantic versioning rules

## Design system validation

Checks that all 5 required files exist in `front/design-system/`:
- `_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`
- Changelog is populated
- All referenced tokens are cataloged

## Persisted reports

Validation reports are saved to `{SPECS_DIR}/_validation/{domain}-validation.md` for use by the triage command (`/u-spec-triage`).

## Coverage report

When validation passes (VALID), the Validator generates a compliance report with coverage metrics per domain and globally.

## Limits

- Never approve specs with blocking inconsistencies
- Always generate a coverage map
- Max **2 invalidation cycles** per agent before escalation to human
