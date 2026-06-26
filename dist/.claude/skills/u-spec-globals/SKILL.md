---
name: u-spec-globals
description: Project-wide specification globals — conventions.md (naming and identifier prefix rules UC/BR/ST/EV/UI/FL), error-codes.md (global error catalog cross-checked by u-spec-validator), glossary.md (controlled vocabulary). Read by all spec agents and validators by path. Resource bundle — no scripts. Not user-invocable.
user-invocable: false
---

# u-spec-globals

Resource bundle: globals shared by every specification artifact. Files are read by path (`.claude/skills/u-spec-globals/<file>`); the directory listing is authoritative.

## Index

| File | Content | Primary consumers |
|---|---|---|
| `conventions.md` | Naming rules and identifier prefixes (UC, BR, ST, EV, UI, FL) | all spec agents, u-spec-validator |
| `error-codes.md` | Global error catalog — single source for every `error.code` referenced in specs | u-spec-back, u-spec-front, u-spec-validator |
| `glossary.md` | Controlled vocabulary for domain terms | all spec agents |

## Constraints

- `error-codes.md` is the catalog the Spec Validator cross-references (every `error.code` in feature specs MUST exist here AND in the corresponding `openapi.yaml` error response)
- Updates to these files are spec changes — they require revalidation of dependent domains
