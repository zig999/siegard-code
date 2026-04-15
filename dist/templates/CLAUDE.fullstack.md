# Project

domain: fullstack
stack:
  frontend: {framework} {version}, {language} {version}, {css-framework}, {state-management}, {data-fetching}, {test-runner}, {e2e-runner}
  backend: {runtime} {version}, {language} {version}, {framework} {version}, {database} {version}, {orm}, {test-runner}
specs_dir: docs/specs
sessions_dir: docs/sessions
runtime_dir: docs/runtime/logs

design_system:
  path: docs/specs/front/design-system/      # path to design-system/ directory — agents resolve tokens.md, components.md etc from here
  token_prefix: "--color-"                   # CSS custom property prefix for color tokens (Tailwind v4 @theme naming); e.g. --color-primary, --color-surface
  color_mode: dark-only | light-only | both  # default: both
  component_library: {shadcn | mui | tremor | antd | radix | none}  # default: none
  enforce_tokens: true                        # true = agents reject hardcoded values as BUG; false = warnings only. default: true
  motion_policy: strict | permissive          # strict = --duration-* and --ease-* required on all transitions; permissive = only bans transition:all. default: strict

# design_system block is optional. When absent, all agents apply the defaults listed above.
# Canonical defaults (single source of truth — do not redefine in agent files):
#   path:              {specs_dir}/front/design-system/
#   token_prefix:      "--color-"
#   color_mode:        both
#   component_library: none
#   enforce_tokens:    true
#   motion_policy:     strict

# Available validation skill:
#   /u-fe-validate [TARGET] [SPECS_DIR] — validates frontend code against design system tokens and rules

apps:
  frontend:
    path: frontend/
    dev: {dev-command}
    build: {build-command}
  backend:
    path: backend/
    dev: {dev-command}
    build: {build-command}

## Directory Structure

```
frontend/               # Frontend app root
  src/
  package.json

backend/                # Backend app root
  src/
  package.json

docs/                   # Shared documentation — lives at monorepo root
  specs/                    # Layer: permanent — versioned, reviewed, source of truth
    _global/                #   conventions.md, error-codes.md, glossary.md
    _validation/            #   validation-result.yaml + validation.md per domain
    domains/{domain}/       #   openapi.yaml, {domain}.spec.md, back/{domain}.back.md
    front/                  #   front.md, features/, components/, _flows/, design-system/
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

package.json            # Workspace root (pnpm workspaces / npm workspaces)
```

**.gitignore rule (add to project root):**
```
docs/runtime/
```

> Agents write session logs to `sessions_dir`. Runtime logs (ephemeral traces, debug output) go to `runtime_dir` and are never committed. The `handoff-manifest.yaml` and `decisions.md` live directly in `specs_dir` as semi-permanent artifacts.

---

## Architecture

### Frontend
- Rendering strategy: {SSR | SSG | SPA | hybrid}
- Routing: {strategy}
- Shared UI: `frontend/src/components/ui/`
- Data fetching: {library}
- Client state: {library}
- Authentication: {strategy}

### Backend
- Style: {monolith-modular | microservices | serverless}
- API: {REST | GraphQL | tRPC} — {documentation-strategy}
- Layering: {Controller → Service → Repository | other}
- Primary database: {database} via {ORM}
- Cache: {strategy | none}
- Background jobs: {strategy | none}

---

## Conventions

- Language: TypeScript strict mode (both layers)
- Frontend folder: `frontend/src/features/{feature}/` with `hooks/`, `types.ts`, `api/`
- Backend folder: `backend/src/modules/{domain}/` with `controller/`, `service/`, `repository/`, `dto/`, `entity/`
- All endpoints return standardized response shape: `{ data, meta, errors }`

---

## Stack — Frontend

### CSS framework
{framework} — design tokens in `{config-file}`

### Component library
{library}
> Canonical reference: `design_system.component_library` in the header above. Keep in sync.

### Icons
{library}

### Forms & validation
{form-library} + {validation-library}

### Animation
{library}

### HTTP client
{client} — base URL via `{ENV_VAR_NAME}`

---

## Stack — Backend

### Validation
{library} — DTOs use {decorator-strategy}

### Logging
{library} — structured JSON output

### Authentication
{strategy}

---

## Testing

### Frontend
- Unit: {runner}
- E2E: {runner} under `frontend/e2e/`
- API mocking: {strategy}

### Backend
- Unit: {runner}
- Integration: {runner} + {test-database-strategy} under `backend/test/integration/`

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
- Package manager: {pnpm | npm | yarn | bun} workspaces
- Linter: {config}
- Formatter: {config}
- CI: {platform}
- Container: {Docker | none}
