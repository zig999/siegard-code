# Variables Reference

Complete reference of all system variables and identifiers.

## System variables

| Variable | Source | Default | Description |
|----------|--------|---------|-------------|
| `CLAUDE.md` | Project root | -- | Project configuration file |
| `SPECS_DIR` | CLAUDE.md > Arg | -- | Specifications directory (mandatory) |
| `SESSIONS_DIR` | CLAUDE.md > Arg | -- | Sessions directory (mandatory) |
| `SESSION` | Last command argument | -- | Current session name |
| `{SESSIONS_DIR}/{SESSION}/` | Computed | -- | Current session working dir |
| `CODE_DIR` | Command argument | -- | Source code dir (reverse spec) |
| `domain:` | CLAUDE.md | -- | `frontend`, `backend`, or `fullstack` |
| `stack:` | CLAUDE.md | -- | Project technology stack |

## Directory variables

| Path | Description |
|------|-------------|
| `{SPECS_DIR}` | Approved specifications |
| `_temp/` | Archived temporary artifacts |
| `_global/` | Shared resources (conventions, error codes, glossary) |
| `_templates/` | Spec templates |
| `_meta/` | Metadata (origin markers, changelog) |
| `_validation/` | Persisted validation reports |

## Identifier prefixes

| Prefix | Meaning | Defined in | Used for |
|--------|---------|-----------|----------|
| UC-NN | Use Case | `.spec.md` | Central traceability anchor |
| BR-NN | Business Rule | `.back.md` | Backend implementation rules |
| ST-NN | State Machine state | `.back.md` | State transitions |
| EV-NN | Domain Event | `.back.md` | Async communication |
| UI-NN | UI State | `.screen.md` | Component states |
| FL-NN | Navigation Flow | `.flow.md` | Screen transitions |

## Frontend vs Backend differences

| Aspect | Frontend | Backend |
|--------|----------|---------|
| Pipeline | Planner -> UI Agent -> Developer -> QA | Planner -> Developer -> QA |
| UI Agent | Yes | No |
| Spec consumption | `.screen.md`, `.flow.md`, `front.md` | `.back.md`, `openapi.yaml` |
| Traceability | UI-NN | UC-NN, BR-NN |
| Dependency report | `us-XX-backend-pending-items.md` | `us-XX-infra-pending-items.md` |
| Context mounting | 7 protocol files (includes UI) | 6 protocol files |
| Epic integration | Navigation, state, layout | API contracts, migrations, data |
| Standards focus | Accessibility, visual regression | Data integrity, API contracts |
