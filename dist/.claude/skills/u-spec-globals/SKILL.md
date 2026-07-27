---
name: u-spec-globals
description: Project-wide specification globals — conventions.md (naming and identifier prefix rules UC/BR/ST/EV/UI/FL), error-codes.md (FRAMEWORK BASE error catalog — project codes live in {SPECS_DIR}/_global/error-codes.md; validators read the union), glossary.md (controlled vocabulary). Read by all spec agents and validators by path. Resource bundle — no scripts. Not user-invocable.
user-invocable: false
---

# u-spec-globals

Resource bundle: globals shared by every specification artifact. Files are read by path (`.claude/skills/u-spec-globals/<file>`); the directory listing is authoritative.

## Index

| File | Content | Primary consumers |
|---|---|---|
| `conventions.md` | Naming rules and identifier prefixes (UC, BR, ST, EV, UI, FL) | all spec agents, u-spec-validator |
| `error-codes.md` | **Framework base** error catalog. Project codes belong in `{SPECS_DIR}/_global/error-codes.md` — this file is overwritten on upgrade and is not what the `error_codes_synced` gate reads | u-spec-back, u-spec-front, u-spec-validator |
| `glossary.md` | Controlled vocabulary for domain terms | all spec agents |

## Constraints

- The catalog the Spec Validator cross-references is the **union** of this file (framework base) and `{SPECS_DIR}/_global/error-codes.md` (project). Every `error.code` in feature specs MUST exist in one of them AND in the corresponding `openapi.yaml` error response. New project codes go in the project file — never here (see its header)
- Updates to these files are spec changes — they require revalidation of dependent domains
