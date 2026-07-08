# CLAUDE.md — {PROJECT_NAME}

## Project

### Description

**{PROJECT_NAME}** is {ONE_LINE_DESCRIPTION}.

#### Problem solved

{PROBLEM_STATEMENT — 2 to 4 sentences explaining what is lost or broken without this tool}

#### Core concepts

- **{Concept1}** — {definition and role in the system}
- **{Concept2}** — {definition and role in the system}
- **{Concept3}** — {definition and role in the system}

#### Technical flow [REMOVE IF NOT APPLICABLE]

<!-- Only include if the inter-system communication sequence has direct implications
     for architecture decisions (e.g. multi-step auth affecting middleware layering). -->

1. {SYSTEM_STEP_1 — e.g. Client sends JWT to BFF → BFF validates via Supabase service key}
2. {SYSTEM_STEP_2}
3. {SYSTEM_STEP_3}

---

## Golden Rules

These rules apply to every task in this project unless explicitly overridden.
Bias: caution over speed on non-trivial work. Use judgment on trivial tasks.

**Rule 1 — Think Before Coding**
State assumptions explicitly. If uncertain, ask rather than guess.
Present multiple interpretations when ambiguity exists.
Push back when a simpler approach exists.
Stop when confused. Name what's unclear.

**Rule 2 — Simplicity First**
Minimum code that solves the problem. Nothing speculative.
No features beyond what was asked. No abstractions for single-use code.
Test: would a senior engineer say this is overcomplicated? If yes, simplify.

**Rule 3 — Surgical Changes**
Touch only what you must. Clean up only your own mess.
Don't "improve" adjacent code, comments, or formatting.
Don't refactor what isn't broken. Match existing style.

**Rule 4 — Goal-Driven Execution**
Define success criteria. Loop until verified.
Don't follow steps. Define success and iterate.
Strong success criteria let you loop independently.

**Rule 5 — Use the Model Only for Judgment Calls**
Use the model for: classification, drafting, summarization, extraction.
Do NOT use the model for: routing, retries, deterministic transforms.
If code can answer, code answers.

**Rule 6 — Token Budgets Are Not Advisory**
Per-task: 4,000 tokens. Per-session: 30,000 tokens.
If approaching budget, summarize and start fresh.
Surface the breach. Do not silently overrun.

**Rule 7 — Surface Conflicts, Don't Average Them**
If two patterns contradict, pick one (more recent / more tested).
Explain why. Flag the other for cleanup.
Don't blend conflicting patterns.

**Rule 8 — Read Before You Write**
Before adding code, read exports, immediate callers, shared utilities.
"Looks orthogonal" is dangerous. If unsure why code is structured a way, ask.

**Rule 9 — Tests Verify Intent, Not Just Behavior**
Tests must encode WHY behavior matters, not just WHAT it does.
A test that can't fail when business logic changes is wrong.

**Rule 10 — Checkpoint After Every Significant Step**
Summarize what was done, what's verified, what's left.
Don't continue from a state you can't describe back.
If you lose track, stop and restate.

**Rule 11 — Match the Codebase's Conventions, Even If You Disagree**
Conformance > taste inside the codebase.
If you genuinely think a convention is harmful, surface it. Don't fork silently.

**Rule 12 — Fail Loud**
"Completed" is wrong if anything was skipped silently.
"Tests pass" is wrong if any were skipped.
Default to surfacing uncertainty, not hiding it.

---

## Configuration

<!-- MACHINE-PARSED — read via regex by orchestrator-dev and u-spec/u-dev.
     These two fields are required. Do not rename or nest them. -->
domain: {frontend|backend|fullstack}
specs_dir: {e.g. docs/specs}

<!-- CONTEXT — read as LLM context by workers. Not parsed mechanically. -->

# --- Infrastructure ---
stack:
  frontend: {e.g. React 19, TypeScript 5, Tailwind CSS v4, Zustand v5, @tanstack/react-query v5, Vitest, Playwright}
  backend: {e.g. Node.js 20, TypeScript 5.7, Fastify, PostgreSQL 17, Vitest}
apps:
  frontend:
    path: {e.g. frontend}/
    dev: {e.g. npm run dev -w frontend}
    build: {e.g. npm run build -w frontend}
  backend:
    path: {e.g. backend}/
    dev: {e.g. npm run dev -w backend}
    build: {e.g. npm run build -w backend}
sessions_dir: {e.g. docs/sessions}
runtime_dir: {e.g. docs/runtime/logs}

# --- Review phase (orchestrator-review) ---
# test_command must emit JSON: vitest --reporter=json | jest --json | pytest --json-report (pytest-json-report plugin)
test_command: {e.g. npx vitest run --reporter=json}
build_command: {e.g. npm run build}   # empty string "" skips build step

# --- Backend config (u-be-developer, u-be-qa, u-be-standards) ---
# All fields are optional. Agents use stated defaults when absent.
di_strategy: {manual-factory|nestjs-ioc|inversify}       # default: manual-factory
validation_library: {zod|joi|class-validator}             # default: zod
folder_structure: {feature-based|modules}                 # default: feature-based
api_versioning_strategy: {none|url-prefix|header}         # default: none — informs u-spec-writing and u-be-developer
pagination:
  strategy: {offset|cursor}   # default: offset
  default_limit: {e.g. 20}
  max_limit: {e.g. 100}

# --- Orchestration concurrency (orchestrator-dev worker dispatch) ---
# Controls how many workers run in parallel per phase. Lower values reduce token burn.
# Missing = orchestrator decides (typically 2 for fullstack, 1 for single-domain).
# The effective runtime knob is `dispatch_policy.dev.max_concurrent` in .orch/config.json
# (default 2). Raise it ONLY after validating against your runtime's real subagent cap —
# the default is deliberately conservative and applies to every project (do not raise it
# globally in the framework without measurement).
max_parallel_workers: {e.g. 2}

# --- Frontend config (u-fe-developer, u-fe-qa) ---
i18n: {true|false}   # default: false — enables hardcoded-string checks in QA
accessibility: {none|wcag-2.1-aa|wcag-2.2-aa}   # default: none — recommended baseline: wcag-2.2-aa

# --- QA feature flags (BE and FE — activates extra checks in qa phase) ---
observability_required: {true|false}   # default: false
dependency_audit: {true|false}         # default: false

# --- Git conventions (used by agents creating branches and PRs) ---
git_conventions:
  branch_pattern: {e.g. feat/|fix/|chore/}
  commit_format: {conventional-commits|free-form}   # default: conventional-commits
  pr_target: {main|develop}                          # default: main

# --- Docs and changelog policy ---
changelog_required: {true|false}         # default: false
docs_update_policy: {on-pr|on-merge|manual}   # default: manual

# --- Compliance (u-spec-compliance — omit section if no regulatory requirements) ---
# Accepted values: gdpr, pci_dss, hipaa, sox, lgpd
compliance: []   # e.g. [gdpr, lgpd]

# --- Design system (u-ui-design) [REMOVE IF NOT APPLICABLE — non-Tailwind or back-end-only projects] ---
design_system:
  tailwind_integration: {theme}   # "theme" = CSS-first config via @theme in theme.css

---

## Environment

- Node: {e.g. v20 LTS}
- OS: {e.g. Windows + WSL | macOS | Linux}
- Package manager: {e.g. npm (workspaces) | pnpm | yarn}
- Linter: {e.g. ESLint + @typescript-eslint}
- Formatter: {e.g. Prettier + prettier-plugin-tailwindcss}
- CI: {e.g. GitHub Actions | none}
- Dev server: {e.g. tsx watch (backend) / vite (frontend)}
- Container: {none | Docker}

---

## Commands

| Task      | Command                                 |
|-----------|-----------------------------------------|
| dev (fe)  | {e.g. npm run dev -w frontend}           |
| dev (be)  | {e.g. npm run dev -w backend}            |
| build     | {e.g. npm run build}                    |
| test      | {e.g. npm run test}                     |
| lint      | {e.g. npm run lint}                     |
| typecheck | {e.g. npx tsc --noEmit}                 |
| migrate   | {e.g. npx supabase db push \| skip}     |

---

## Directory Structure

```
{specs_dir}/
  _global/                #   conventions.md, error-codes.md, glossary.md
  _validation/            #   validation-result.yaml + validation.md per domain
  domains/{domain}/       #   openapi.yaml, {domain}.spec.md, back/{domain}.back.md
  front/                  #   front.md, features/, components/, _flows/, design-system/
  handoff-manifest.yaml   # Delivery contract read by orchestrator-dev — see Handoff Manifest section
  decisions.md            # Active architectural decisions

{sessions_dir}/{session}/
  backlog.md              #   Epics and Task Contracts (written by u-planning)
  log-orchestrator-dev.md #   Dev orchestrator session log
  tc-XX-delivery.md       #   Developer delivery (includes delivery-gate YAML block)
  us-XX-qa.md             #   QA report (written by u-be-qa / u-fe-qa)
  session-decisions.md    #   Cross-session persistent decisions
  triage.json             #   Written by u-spec-triage; read by orchestrator-sdd for dispatch routing
  improve-scope.json      #   Written by /u-improve; read by orchestrator-dev for improve flow
  _temp/                  #   Consumed inputs moved here after processing (not deleted)

.orch/                    # Orchestration engine state — NOT committed (add to .gitignore)
  log.jsonl               #   Append-only event log — source of truth for all phase state
  config.json             #   Optional: retry policy and circuit breaker overrides (see Orchestration Engine)
  workflow.json           #   Optional: override default phase sequence
  workers/{id}.json       #   Worker registry entries (written by hooks, consumed by on_subagent_stop)
  metrics/current.json    #   Written by on_stop hook — diagnosis of last session

{runtime_dir}/
  *.yaml                  #   Ephemeral traces — NOT committed to repo
```

**.gitignore rules (add to project root):**
```
# Orchestration engine runtime state — never commit
.orch/

# Replace with the root dir of runtime_dir (e.g. docs/runtime/)
{runtime_dir_root}/
```

---

## Orchestration Engine

<!-- This section documents how the siegard orchestration engine behaves in this project.
     Modify .orch/config.json and .orch/workflow.json to tune behavior without touching CLAUDE.md. -->

### Entry points

| Command          | When to use                                                        |
|------------------|--------------------------------------------------------------------|
| `/u-spec`        | New feature or domain — runs full SDD → Dev → Review → Test         |
| `/u-dev`         | Skip spec phase — goes directly to Dev → Review → Test              |
| `/u-improve`     | Incremental change to an existing spec or behavior                 |
| `/u-reverse-spec`| Generate specs from existing code (reverse engineering)            |

**Utility commands (ad-hoc, not phase entry points):** `/u-fe-validate` (frontend spec-gate check), `/u-doc-cleanup` (strip historical noise from docs), `/u-cleanup` (runtime `.orch/` cleanup), `/u-orchestrator` (inspect derived phase/task state from the log).

### Retry policy (`.orch/config.json`)

The engine uses exponential backoff with per-tier defaults. Override when project needs differ:

```json
{
  "retry_policy": {
    "defaults_by_tier": {
      "critical": { "max_attempts": 5, "base_delay_s": 15, "cap_s": 600 },
      "standard": { "max_attempts": 3, "base_delay_s": 30, "cap_s": 600 },
      "bulk":     { "max_attempts": 1, "base_delay_s": 0,  "cap_s": 0   }
    },
    "overrides_by_task_type": {
      "{task_type}": { "max_attempts": 2, "base_delay_s": 10, "cap_s": 120 }
    }
  }
}
```

### Circuit breaker (`.orch/config.json`)

Trips when failure rate exceeds threshold within the rolling window. Defaults:

```json
{
  "circuit_breaker": {
    "enabled": true,
    "window_minutes": 10,
    "failure_threshold": 50,
    "scope": "workflow"
  }
}
```

> These four fields are the entire contract. The engine has **no cooldown or success-reset logic** — do NOT add `cooldown_minutes` or `reset_on_success_count`: they are not implemented (`evaluate_circuit_state`) and would be silently ignored. A tripped breaker is cleared by the rolling window elapsing or a manual reset (`scripts/circuit_breaker.py`).

### Phase override (`.orch/workflow.json`)

Override the default phase sequence before first `/u-spec` invocation. Once the log exists, phase sequence is derived from events — `workflow.json` is ignored.

The default workflow is `dev-cycle` — **four** phases (`sdd` → `dev` → `review` → `test`). Omitting `workflow.json` runs all four; the block below only needs to change if you want a different sequence.

```json
{
  "phases": ["sdd", "dev", "review", "test"]
}
```

### Worker recursion limit

Orchestrators refuse to spawn if `nesting_depth >= 3`. If this error appears, the call chain has a cycle — investigate the orchestrator that is re-spawning itself.

### Diagnosing a stuck session

1. Read `.orch/metrics/current.json` — written by `on_stop` hook after each session.
2. Check `.orch/last_error.json` — written when an orphaned phase or stuck improve workflow is detected.
3. Run `/u-orchestrator` to derive the current phase and pending task list from the log (or run `.claude/skills/orch-state/scripts/summary.py` directly). `orch-state` is an internal skill, not a slash command.

---

## Handoff Manifest

<!-- handoff-manifest.yaml is the delivery contract between the SDD phase and the Dev/Review/Test phases.
     Generated deterministically by orchestrator-sdd (generate_handoff_manifest.py) over validated specs,
     validated by u-handoff-validator (validate.py — 13 rules + sha256), and consumed by the Dev/Review/Test
     orchestrators (via parse_manifest_fields). It is a pure function of the on-disk specs — do not hand-edit. -->

**File location:** `{specs_dir}/handoff-manifest.yaml`

**Validation (the gate):**

```bash
python3 .claude/skills/u-handoff-validator/validate.py \
  --manifest {specs_dir}/handoff-manifest.yaml --specs-dir .
```

`status: valid` (exit 0) is the gate. **Approval is derived, not a field:** a schema-valid manifest that passes the validator IS the approval — there is no `approval_status` field. The SDD→Dev gate (`check_handoff_manifest_approved.py`) runs this validator and proceeds only on `status: valid`.

**Worker dispatch** is inferred from artifact presence, not from a `stack` field: `backend_package` present → BE workers; `frontend_package` present → FE workers; both → fullstack (parallel). Do not add a `stack` field — it is not in the canonical schema and the generator never emits it.

**Structure (canonical — `u-shared-templates/handoff-manifest.schema.yaml`):**

```yaml
handoff:
  id: HANDOFF-YYYYMMDD-HHMMSS
  delivered_by: u-spec-orchestrator                 # const — FLOW-030
  delivered_at: {ISO-8601 Z, e.g. 2026-06-04T12:00:00Z}
  layer: semi-permanent
  type: {new_domain|major_evolution|fast_track|reverse_eng}   # HDF-010

domains:                                            # ≥ 1 entry — FLOW-031
  - name: {domain}
    spec_version: {x.y.z}
    back_version: {x.y.z}
    openapi_version: {x.y.z}
    compliance_report: {path or "Validation passed. No blocking issues."}

backend_package:                                    # ≥ 1 entry — FLOW-032
  # For new_domain/major_evolution must include both openapi AND back-spec — FLOW-037
  - path: {specs path}
    artifact: {conventions|error-codes|openapi|spec|back-spec}
    sha256: {64-hex — verified against file contents, HDF-020}

# frontend_artifacts + frontend_package: present only when the handoff carries a front. Omit for back-only.
frontend_artifacts:                                 # when present, all 3 subfields required — HDF-040
  front_md_version: {x.y.z}
  features: [{name, path}, ...]
  flows: [{name, path}, ...]
frontend_package:
  - path: {specs path}
    artifact: {conventions|error-codes|openapi|spec|front|feature-spec|component-spec|flow}
    sha256: {64-hex — verified, HDF-021}

# change_summary: FORBIDDEN for new_domain (FLOW-033); REQUIRED for major_evolution/fast_track/reverse_eng (FLOW-034).
change_summary:
  type: {patch|minor|major}                         # must match handoff.type — FLOW-036
                                                    #   fast_track → patch|minor; major_evolution → major; reverse_eng → patch|minor|major
  cr: {CR-NN or none}
  changed_files: [{path}, ...]
  dev_impact: {no_action|reevaluate_task_contracts|stop_domain_task_contracts}   # FLOW-035
                                                    #   stop_domain_task_contracts → orchestrator halts affected domains (HDF-030)
```

> **Schema strictness:** the canonical schema is `additionalProperties: false` at every level — unknown or misnested keys (a top-level `stack`/`approval_status`, or `dev_impact`/`changed_files` placed under `handoff` instead of `change_summary`) are schema-invalid. `validate.py` checks only the 13 rules below and ignores extra keys, so do not rely on it to catch them — keep the manifest to the structure above.

**Blocking rules (`u-handoff-validator`):**

| Rule | Requirement |
|---|---|
| FLOW-030 | `handoff.delivered_by` == `u-spec-orchestrator` |
| HDF-010 | `handoff.type` in `{new_domain, major_evolution, fast_track, reverse_eng}` |
| FLOW-031 | `domains[]` ≥ 1 |
| FLOW-032 | `backend_package[]` ≥ 1 |
| FLOW-037 | `backend_package` includes `openapi` + `back-spec` (for new_domain/major_evolution) |
| HDF-020 / HDF-021 | every `backend_package` / `frontend_package` entry's `sha256` matches file contents |
| FLOW-033 | `new_domain` must NOT include `change_summary` |
| FLOW-034 | `major_evolution` / `fast_track` / `reverse_eng` MUST include `change_summary` |
| FLOW-035 | `change_summary.dev_impact` in `{no_action, reevaluate_task_contracts, stop_domain_task_contracts}` |
| FLOW-036 | `change_summary.type` matches `handoff.type` (fast_track→patch\|minor; major_evolution→major; reverse_eng→patch\|minor\|major) |
| HDF-030 | `dev_impact: stop_domain_task_contracts` raises a halt signal — caller halts affected domains |
| HDF-040 | `frontend_artifacts`, when present, includes `front_md_version`, `features`, `flows` |

**Failure modes:**

| Condition | Symptom | Recovery |
|---|---|---|
| Validator `status: invalid` | SDD→Dev gate stays blocked (fail-closed) | Read `errors[]`; fix the offending rule; re-run `/u-spec` |
| `change_summary` present on a `new_domain` handoff | FLOW-033 blocks | Remove `change_summary` — a new domain carries no diff |
| `change_summary` missing on evolution / fast_track / reverse_eng | FLOW-034 blocks | Add `change_summary` (`type`/`cr`/`changed_files`/`dev_impact`) |
| `sha256` stale (spec edited after generation) | HDF-020/021 mismatch | Regenerate the manifest — never hand-edit hashes |
| `frontend_artifacts` present but missing a subfield | HDF-040 blocks | Add `front_md_version` / `features` / `flows` |
| Declared fullstack/fe but no front specs on disk | Generator fails closed (`stack_mismatch_front_expected_but_missing`) | Produce the front specs or fix the triage stack |

---

## Architecture

### Frontend [REMOVE IF NOT APPLICABLE]

- Rendering strategy: {SPA | SSR | SSG | hybrid}
- Routing: {e.g. React Router DOM v7}
- Shared UI: `{e.g. frontend/src/components/ui/}`
- Data fetching: {e.g. @tanstack/react-query v5}
- Client state: {e.g. Zustand v5}
- Authentication: {e.g. Supabase Auth — login/signup via supabase-js, JWT sent to BFF}
- direct_{service}_access: {true|false} — {e.g. direct_db_access: false — all data access goes through BFF}

### Backend [REMOVE IF NOT APPLICABLE]

<!-- "Style" is read by orchestrator-sdd and u-spec-writing to determine domain boundaries.
     monolith-modular = single deployable, feature modules; microservices = per-service workers. -->
- Style: {monolith-modular | microservices | serverless}
- API: {REST | GraphQL | tRPC} — {tooling, e.g. OpenAPI via @fastify/swagger}
- Layering: {e.g. Controller → Service → Repository}
- Primary database: {e.g. PostgreSQL 17 via Supabase Cloud}
- Auth: {e.g. Supabase Auth — JWT validation in BFF middleware}
- direct_{service}_access: {true|false} — {e.g. direct_db_access: false — single entry point for all business logic}
- Cache: {none | Redis | in-memory}
- Background jobs: {none | e.g. pg-boss — queues: reminders, recurrence}

### Database [REMOVE IF NOT APPLICABLE]

- Platform: {e.g. Supabase Cloud | AWS RDS | PlanetScale}
- Database: {e.g. PostgreSQL 17}
- Migrations: {e.g. SQL nativo (`supabase/migrations/`)}
- Seeds: {e.g. `supabase/seed.sql` for development data}
- Business logic: {in application layer | in DB functions/procedures}
- Naming: {snake_case | camelCase} for tables and columns
- Audit timestamps: {all tables have `created_at` and `updated_at` | specify exceptions}

**Safety Rule — Database Changes Require Explicit Approval**

No database change may be executed without the user's explicit approval. This covers: migration files, schema-altering commands, seed files, tables/columns/indexes/functions/triggers/policies.

Required protocol:
1. Present the proposed SQL or migration to the user.
2. Explain the impact (which tables/columns are affected, whether it is reversible).
3. Wait for explicit confirmation before executing.

**Forbidden:** using `--force`, skipping confirmation, or executing in the background without prior notice.

### {External Service / Infrastructure} [REMOVE IF NOT APPLICABLE]

- role: {e.g. infrastructure-only — DB, auth, storage}
- rls: {enabled | disabled} — {justify: e.g. security centralized in BFF service layer}

### Repository Layer [REMOVE IF NOT APPLICABLE]

- interfaces: {e.g. IUserRepository, ISubjectRepository} — contracts defined in service layer
- adapters: {e.g. SupabaseUserRepository} — swappable implementations
- swap_cost: repository-layer-only — replacing the DB = replacing only the adapters

### MCP Server [REMOVE IF NOT APPLICABLE]

- role: {e.g. BFF client — consumes the same REST routes as the frontend}
- auth: {e.g. JWT in Authorization: Bearer header}
- contract: {e.g. tools generated from BFF openapi.yaml}
- direct_{service}_access: {true|false} — {e.g. direct_db_access: false — consumes BFF routes only}

---

## Stack — Frontend [REMOVE IF NOT APPLICABLE]

<!-- Fixed-stack profile: if this project uses Vite + React 19 + TypeScript (strict) + Tailwind v4
     + shadcn/ui + TanStack Query/Router/Table + React Hook Form + Zod, paste the contents of
     dist/claude-md-fragments/fe-stack-react-tailwind-tanstack.md below this line. That fragment
     fixes the data layer (TanStack Query), component contract (className/cn, CVA, ref-as-prop),
     forms (RHF+Zod), tables (TanStack Table + URL state), and responsive rules (named breakpoints
     + container queries). Omit the fragment for any other stack. -->

### {CSS Framework — e.g. Tailwind CSS v4}

- {Rule 1 — e.g. CSS-first config via @theme in theme.css. No tailwind.config.ts.}
- {Rule 2 — e.g. Never hardcode values — always reference a design token.}
- Breakpoints: {e.g. mobile-first — `sm:` ≥640px, `md:` ≥768px, `lg:` ≥1024px. Layout collapses to single column below sm.}

**Forbidden:**
- {Forbidden pattern 1 — e.g. arbitrary values: p-[13px], gap-[7px]}
- {Forbidden pattern 2}

### {Component Library — e.g. shadcn/ui (Radix UI)}

- {Rule 1 — e.g. Own generated files in components/ui/ — modify with intent, not via CLI overwrite.}
- {Rule 2 — e.g. Use cn() for className merging — never string concatenation.}

### {Forms Library — e.g. React Hook Form v7 + Zod v4}

- {Rule 1 — e.g. Always use zodResolver. Never write manual validate functions.}
- {Rule 2 — e.g. Wrap all controlled inputs with Controller.}

### {Animation — e.g. Framer Motion}

- {Rule 1}

### {Notifications — e.g. sonner}

- {Rule 1 — e.g. Single Toaster at app root. Never render multiple instances.}

### {Icons — e.g. lucide-react}

- {Rule 1 — e.g. Named imports only. Never default import.}

### {Build — e.g. Vite 6}

---

## Stack — Backend [REMOVE IF NOT APPLICABLE]

### Validation

{e.g. Zod v4 — DTOs validated at runtime in controllers}

### Logging

{e.g. pino — structured JSON output (native Fastify integration via pino-http)}

### Authentication

{e.g. Supabase Auth — JWT issued by Supabase, validated in BFF middleware via @supabase/supabase-js (service key)}

---

## Testing

### Frontend [REMOVE IF NOT APPLICABLE]

- Unit: {e.g. Vitest}
- E2E: {e.g. Playwright under `frontend/e2e/`}
- API mocking: {e.g. MSW (Mock Service Worker) — network-level intercepts, shared between Vitest and Playwright}

### Backend [REMOVE IF NOT APPLICABLE]

- Unit: {e.g. Vitest}
- Integration: {e.g. Vitest + real DB under `backend/test/integration/`}

---

## Performance Budgets [REMOVE IF NOT APPLICABLE]

<!-- Only include if the project has enforceable performance targets.
     Agents must flag violations during QA phase. -->

### Frontend

- LCP: {e.g. < 2.5s}
- FID / INP: {e.g. < 100ms}
- Bundle size (initial, gzipped): {e.g. < 300kb}
- Lighthouse score (CI gate): {e.g. ≥ 85 performance, ≥ 90 accessibility}

### Backend

- API response p50: {e.g. < 80ms}
- API response p95: {e.g. < 200ms}
- DB query p95: {e.g. < 50ms}

---

## Conventions

- Language: {e.g. TypeScript strict mode (both layers)}
- Frontend folder: `{e.g. frontend/src/features/{feature}/}` with `{subfolders, e.g. hooks/, types.ts, api/}`
- Backend folder: `{e.g. backend/src/modules/{domain}/}` with `{subfolders, e.g. controller/, service/, repository/, dto/, entity/}`
- All endpoints return standardized response shape: `{ data, meta, errors }`
- {NON-OBVIOUS RULE — e.g. Controllers never call Repository directly — always go through Service}
- {NON-OBVIOUS RULE — e.g. All DB queries must have an explicit LIMIT — never unbounded selects}
- {NON-OBVIOUS RULE — e.g. Never import from a sibling feature — only from shared/ or own feature}

---

## Anti-patterns

<!-- Structural and design patterns explicitly forbidden in this project.
     Add entries here (not scattered across sections) for discoverability.
     For tool/operational traps, use Known Gotchas instead. -->

### Architecture

- {e.g. Never call Repository directly from Controller — always go through Service}
- {e.g. Never import from a sibling feature — only from shared/ or own feature}
- {e.g. Never use `any` type — use `unknown` and narrow explicitly}

### Data

- {e.g. Never run unbounded queries — all DB selects must have an explicit LIMIT}
- {e.g. Never use string concatenation for SQL — parameterized queries only}

### Frontend

- {e.g. Never use inline styles — use Tailwind tokens only}
- {e.g. Never access localStorage directly — use the storage abstraction in lib/storage}

### Tooling

- {e.g. Never run `supabase db push` without a migration file — see Database Safety Rule}
- {e.g. Never run shadcn CLI to regenerate components/ui/ — files are owned}

---

## Known Gotchas

<!-- Operational traps specific to this project's tools and setup.
     Errors the agent tends to make without explicit guidance.
     Add entries as you discover recurring mistakes during development.
     For structural/design prohibitions, use Anti-patterns instead. -->

- {e.g. Never run `supabase db push` directly — use migration files only}
- {e.g. `components/ui/` is generated but owned — do not run shadcn CLI to regenerate it}
- {e.g. `runtime_dir/` must never be committed — verify .gitignore before first push}
- {e.g. `cn()` from `lib/utils` is the only approved className merge utility — never string concat}

---

## Security

<!-- Critical section — agents must enforce these rules without exception. -->

**Never commit:**
- `.env`, `*.pem`, `secrets.*`, `credentials.*`, `*.key`, `*.p12`

**Secrets management:** {e.g. doppler | AWS Secrets Manager | .env.local (gitignored, never committed)}

**Forbidden patterns:**
- Hardcoded API keys, tokens, or passwords in source code
- SQL string concatenation — use parameterized queries only
- Logging sensitive fields (passwords, tokens, PII) at any log level
- {project-specific forbidden pattern — e.g. direct Supabase service key usage outside BFF}

**Required before any secret-adjacent change:**
1. Confirm the change does not expose secrets in logs, responses, or committed files.
2. Verify `.gitignore` covers all generated secret-containing paths.

---

## Agent Behavior

<!-- Controls how agents interact with the user and each other across this project. -->

- confirmation_style: {ask-before-destructive|ask-always|autonomous}   # default: ask-before-destructive
- response_language: {pt-BR|en-US}                                     # default: en-US
- verbosity: {terse|normal|verbose}                                    # default: normal
- preferred_model: {claude-sonnet-4-6|claude-opus-4-7}                 # default: claude-sonnet-4-6

---

## Architectural Decisions (ADR inline)

### ADR-001: {TITLE}

**Decision:** {What was decided — one sentence.}
**Justification:** {Why — constraint, incident, or tradeoff that drove the decision.}
**Risk accepted:** {What could go wrong and under what conditions.}
**Revisit when:** {Specific trigger — e.g. before expanding to multi-tenant, when traffic exceeds X.}

### ADR-002: {TITLE}

**Decision:** {What was decided — one sentence.}
**Justification:** {Why — constraint, incident, or tradeoff that drove the decision.}
**Risk accepted:** {What could go wrong and under what conditions.}
**Revisit when:** {Specific trigger — e.g. before expanding to multi-tenant, when traffic exceeds X.}
