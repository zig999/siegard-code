# Project

domain: frontend
stack: {framework} {version}, {language} {version}, {css-framework}, {state-management}, {data-fetching}, {test-runner}, {e2e-runner}
specs_dir: docs/specs
sessions_dir: docs/sessions
runtime_dir: docs/runtime/logs

design_system:
  path: docs/specs/front/design-system/      # path to design-system/ directory — agents resolve tokens.md, components.md etc from here
  token_prefix: "--color-"                   # CSS custom property prefix for color tokens (Tailwind v4 @theme naming); e.g. --color-primary, --color-surface
  color_mode: dark-only | light-only | both  # default: both
  component_library: {shadcn | mui | tremor | antd | radix | none}  # default: none
  enforce_tokens: true                        # true = agents reject hardcoded values as BUG; false = warnings only. default: true
  motion_policy: strict | permissive          # strict = duration-* and ease-* Tailwind classes required on all transitions; permissive = only bans transition:all. default: strict
  tailwind_integration: theme                 # theme = Tailwind v4 @theme {} in global.css, no tailwind.config.ts (default and required for v4 projects)

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

## Directory Structure

```
docs/
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
```

**.gitignore rule (add to project root):**
```
docs/runtime/
```

> Agents write session logs to `sessions_dir`. Runtime logs (ephemeral traces, debug output) go to `runtime_dir` and are never committed. The `handoff-manifest.yaml` and `decisions.md` live directly in `specs_dir` as semi-permanent artifacts.

---

## Architecture

- Rendering strategy: {SSR | SSG | SPA | hybrid}
- Routing: {strategy}
- Shared UI: `src/components/ui/`
- Data fetching: {library}
- Client state: {library}
- Authentication: {strategy}

---

## Conventions

- Language: TypeScript strict mode
- Folder structure: `src/features/{feature}/` with `hooks/`, `types.ts`, `api/`

---

## Stack

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

## Testing

- Unit: {runner}
- E2E: {runner} under `e2e/`
- API mocking: {strategy}

---

## Personas

- {Role}: {description}

---

## Environment

- Node: {version}
- Package manager: {pnpm | npm | yarn | bun}
- Linter: {config}
- Formatter: {config}
- CI: {platform}
- Dev server: {command}
