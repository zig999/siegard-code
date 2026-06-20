---
name: u-spec-templates
description: Canonical TEMPLATE.* artifacts for SDD spec writers — domain spec, back spec, front spec, feature spec, flow, component spec, decisions, design-system rules and design-system bundle. Consumed by u-spec-writer, u-spec-back, and u-spec-front, which read templates by path. Resource bundle — no scripts. Not user-invocable.
user-invocable: false
---

# u-spec-templates

Resource bundle: canonical templates consumed by SDD spec agents. Templates are read by path (`.claude/skills/u-spec-templates/<file>`); the directory listing is authoritative.

## Index

| Template | Produces | Primary consumer |
|---|---|---|
| `TEMPLATE.spec.md` | `domains/{domain}/{domain}.spec.md` | u-spec-writer |
| `TEMPLATE.back.md` | `domains/{domain}/back/{domain}.back.md` | u-spec-back |
| `TEMPLATE.front.md` | `{SPECS_DIR}/front/front.md` (global frontend spec) | u-spec-front |
| `TEMPLATE.feature.spec.md` | `{SPECS_DIR}/front/features/*.feature.spec.md` | u-spec-front |
| `TEMPLATE.flow.md` | `{SPECS_DIR}/front/flow.md` | u-spec-front |
| `TEMPLATE.component.spec.md` | `design-system/components/*.spec.md` | u-fe-spec-writer |
| `TEMPLATE.decisions.md` | `{SPECS_DIR}/decisions.md` | u-spec-writer |
| `TEMPLATE.design-system-rules.md` | `front/design-system-rules.md` | u-spec-front |
| `TEMPLATE.design-system/` | `design-system/` bundle (`_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`) | u-spec-front |
| `FRONTEND-MANDATORY-ARTIFACTS.md` | single source of truth for the frontend design-system artifacts the front pipeline must produce and the validator blocks on (F-07) | u-spec-front (produces), u-spec-validator (gates) |

## Constraints

- Templates contain `<!-- INSTRUCTION: ... -->` placeholders — producers MUST resolve every placeholder; none may survive into generated artifacts
- Identifier prefixes used across templates follow the global pattern defined in `u-spec-globals/conventions.md` (UC, BR, ST, EV, UI, FL)
