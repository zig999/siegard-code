---
name: u-spec-globals-conventions
description: Global spec conventions - prefixes, versioning, naming, and writing format applicable to all agents in the spec group.
user-invocable: false
---

# Global Spec Conventions

## Identifier Prefixes

| Prefix | File | Meaning |
|--------|------|---------|
| `UC-NN` | `{domain}.spec.md` | Use Case |
| `BR-NN` | `{domain}.back.md` | Business Rule |
| `ST-NN` | `{domain}.back.md` | State (state machine) |
| `EV-NN` | `{domain}.back.md` | Event (domain event) |
| `FEAT-NN` | `{feature}.feature.spec.md` | Feature (frontend route spec) |
| `UI-NN` | `{feature}.feature.spec.md §2` | UI State (within a feature) |
| `FL-NN` | `{flow}.flow.md` | Flow (navigation rule) |
| `FLOW-NN` | `{flow}.flow.md` | Flow document ID — unique identifier of a flow.md |
| `COMP-NN` | `{name}.component.spec.md` | Component spec ID — unique identifier of a component.spec.md |
| `DEC-NN` | `decisions.md` | Architecture Decision |
| `CR-NN` | `change-request` | Change Request |

## Spec Versioning

### Increment Rules
- **Patch (0.0.x):** Text corrections, typos, clarifications with no functional impact
- **Minor (0.x.0):** Addition of new UC, BR, endpoints, or optional fields
- **Major (x.0.0):** Breaking changes — field removal, contract changes, existing flow modifications

### Document Status
| Status | Meaning | Who can edit | Minimum determinism required |
|--------|---------|-------------|------------------------------|
| `draft` | In progress | Spec Writer | None — gaps marked with `TODO` |
| `review` | Awaiting review | Spec Reviewer (minor corrections only) | Structure complete; content may have `TODO` |
| `approved` | Approved for agent consumption | No one (only via CR) | Zero `TODO`; zero vague terms; all formulas, tokens, and rules explicit |
| `deprecated` | Replaced by a newer version | No one | — |

**Prohibited in `approved` specs:** any `<!-- TODO -->`, any implicit value ("highlight color", "adaptive font", "appropriate error message"), any cross-reference without a verifiable anchor.

### Mandatory Changelog
Every spec file must have a `## Changelog` section at the end:

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | {agent} | initial | Initial version | -- |

## Naming

### Files
- Domains: `kebab-case` (e.g., `user-management/`)
- Specs: `{domain}.spec.md`, `{domain}.back.md`
- Features: `{feature}.feature.spec.md`
- Flows: `{flow}.flow.md`
- OpenAPI: `openapi.yaml`

### OpenAPI Root
- File: `{SPECS_DIR}/openapi.root.yaml`
- Aggregates all domains via `$ref`
- Format:
```yaml
openapi: "3.0.3"
info:
  title: "{Project Name} — Consolidated API"
  version: "{project version}"
paths:
  # Each domain adds its paths via $ref
  /api/v1/{domain}/{resource}:
    $ref: "./domains/{domain}/openapi.yaml#/paths/~1api~1v1~1{domain}~1{resource}"
```
- Updated by the Spec Writer when creating a new domain
- Not manually edited — always generated from `$ref`
- Used by external tools (Swagger UI, Postman, SDK generation)

### Identifiers within documents
- Global sequence per type within the domain: UC-01, UC-02...
- Never reuse a number even after removal (mark as deprecated)
- Cross-references between files: `[UC-01](../auth/auth.spec.md#uc-01)`

## Artifact Classification

Every artifact produced by any agent belongs to exactly one layer:

| Layer | Examples | Rule |
|-------|----------|------|
| `permanent` | `openapi.yaml`, `{domain}.spec.md`, `{domain}.back.md`, `feature.spec.md` | Versioned, reviewed, source of truth — never discard |
| `semi-permanent` | `backlog.md`, `delivery.md`, `qa-report.md`, `session-decisions.md`, `decisions.md` | Versioned in repo — discard only when explicitly obsolete |
| `ephemeral` | Runtime logs, raw CI output, `docs/runtime/logs/` | Never commit — discard after consumption |

The layer is declared in the artifact header (e.g., `**Layer:** semi-permanent`). When in doubt: if it defines behavior → permanent; if it explains execution → semi-permanent; if it records a run → ephemeral.

## Writing Format
- Short, objective sentences
- Tables whenever there are 3+ comparable items
- ASCII diagrams for state machines
- Concrete JSON examples for payloads
- No internal jargon — use the glossary when needed
- Prohibited terms: "may", "generally", "adequate", "etc.", "similar to", "coming soon"
