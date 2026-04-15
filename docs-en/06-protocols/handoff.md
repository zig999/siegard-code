# Handoff Protocol

Formal artifact transfer from the Spec team to the Dev team.

## When triggered

- Spec Validator produces a VALID final report
- Auto-detected when `{SPECS_DIR}` with approved status is present in the directory

## What is packaged

The handoff bundles all artifacts the Dev team needs:

### Backend package

- `_global/conventions.md`
- `_global/error-codes.md`
- `openapi.yaml` per domain
- `{domain}.spec.md` per domain
- `{domain}.back.md` per domain
- Validator's compliance report
- Pinned spec version

### Frontend package

- `_global/conventions.md`
- `_global/error-codes.md`
- `openapi.yaml` per domain consumed by features
- `{domain}.spec.md` per domain
- `front.md`
- `front/features/{feature}.feature.spec.md` per feature
- `front/components/{name}.component.spec.md` per qualifying shared component
- `front/_flows/{flow}.flow.md` per flow
- `decisions.md` (if exists — Orchestrator reads at session start)
- Validator's compliance report
- Pinned spec version

> **Note:** a feature may consume endpoints from multiple domains. The Dev team must load the `openapi.yaml` from ALL domains referenced in §1 of each feature spec.

### Fullstack projects

For `domain: fullstack`, the handoff delivers **both** backend and frontend artifact packages. The Fullstack Meta-Orchestrator distributes them:
- Backend artifacts are passed to the BE orchestrator during Phase 1
- Frontend artifacts are passed to the FE orchestrator during Phase 2
- After Phase 1 completes, a `handoff-be-to-fe.md` is generated with implemented endpoint details and any deviations from the spec

## Spec version pinning

The handoff includes the exact spec version used. If specs change after the handoff (e.g., during development), the system generates a `spec-changelog-notify.md` to inform the Dev team of changes.

## Artifact mapping Spec → Dev

| Spec Artifact | Identifiers | Consumed by Dev as |
|---------------|-------------|---------------------|
| UC-NN (`.spec.md`) | UC-01, UC-02... | Reference in Task Contracts (`origin` field) |
| BR-NN (`.back.md`) | BR-01, BR-02... | Reference in tests ("describe BR-01") |
| UI-NN (`.feature.spec.md §2`) | UI-01, UI-02... | Reference in feature tests and QA checklist |
| BDD scenarios (`.feature.spec.md §9`) | scenarios | Feature invariants — QA primary verification criterion |
| FL-NN (`.flow.md`) | FL-01, FL-02... | Reference in navigation tests |
| DEC-NN (`decisions.md`) | DEC-01, DEC-02... | Orchestrator reads at session start; active decisions override SKILL defaults |
| error.code (`error-codes.md`) | BUSINESS_*, etc. | Direct use in code (error handlers) |
| Glossary (`glossary.md`) | terms | Use in Task Contract names, variables, messages |

## Post-handoff spec changes

If specs are modified after delivery to the Dev team:
1. System detects the change
2. Generates `spec-changelog-notify.md` with the delta
3. Dev orchestrator presents the change notification
4. Human decides whether to continue, adjust, or restart affected Task Contracts
