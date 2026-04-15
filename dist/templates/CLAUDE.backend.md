# Project

domain: backend
stack: {runtime} {version}, {language} {version}, {framework} {version}, {database} {version}, {orm}, {test-runner}
specs_dir: docs/specs
sessions_dir: docs/sessions
runtime_dir: docs/runtime/logs

## Directory Structure

```
docs/
  specs/                    # Layer: permanent — versioned, reviewed, source of truth
    _global/                #   conventions.md, error-codes.md, glossary.md
    _validation/            #   validation-result.yaml + validation.md per domain
    domains/{domain}/       #   openapi.yaml, {domain}.spec.md, back/{domain}.back.md
    handoff-manifest.yaml   # Layer: semi-permanent — last spec-to-dev delivery record
    decisions.md            # Layer: semi-permanent — active architectural decisions

  sessions/{session}/       # Layer: semi-permanent — versioned, traceability
    backlog.md              #   Epics and Task Contracts
    log-orchestrator-dev.md #   Dev orchestrator session log
    tc-XX-delivery.md       #   Developer delivery (includes delivery-gate YAML block)
    us-XX-qa.md             #   QA report
    session-decisions.md    #   Cross-session persistent decisions
    _temp/                  #   Consumed inputs moved here after processing (not deleted)

  runtime/logs/             # Layer: ephemeral — NOT committed to repo
    *.yaml                  #   Interaction logs, agent run traces, debug output
```

**.gitignore rule (add to project root):**
```
docs/runtime/
```

> Agents write session logs to `sessions_dir`. Runtime logs (ephemeral traces, debug output) go to `runtime_dir` and are never committed. The `handoff-manifest.yaml` and `decisions.md` live directly in `specs_dir` as semi-permanent artifacts.

---

## Architecture

- Style: {monolith-modular | microservices | serverless}
- API: {REST | GraphQL | tRPC} — {documentation-strategy}
- Layering: {Controller → Service → Repository | other}
- Primary database: {database} via {ORM}
- Cache: {strategy | none}
- Background jobs: {strategy | none}

---

## Conventions

- Language: TypeScript strict mode
- Folder structure: `src/modules/{domain}/` with `controller/`, `service/`, `repository/`, `dto/`, `entity/`
- All endpoints return standardized response shape: `{ data, meta, errors }`

---

## Stack

### Dependency Injection
di_strategy: {manual-factory | nestjs-ioc | inversify}

### Validation / DTOs
validation_library: {zod | joi | class-validator}

### Logging
{library} — structured JSON output

### Authentication
{strategy}

---

## Pagination

strategy: {offset | cursor}   # default: offset
default_limit: 20
max_limit: 100

---

## Testing

- Unit: {runner}
- Integration: {runner} + {test-database-strategy} under `test/integration/`

---

## Personas

- {Role}: {description}

---

## Database

- Migrations: {tool} (`{migrations-path}`)
- Seeds: `{seed-file}` for development data
- Soft delete: {enabled | disabled}

---

## Environment

- Node: {version}
- Package manager: {pnpm | npm | yarn | bun}
- Linter: {config}
- Formatter: {config}
- CI: {platform}
- Container: {Docker | none}
