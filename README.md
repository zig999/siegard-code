<p align="center">
  <img src="assets/siegard_256.png" alt="Siegard Code" width="120" />
</p>

<h1 align="center">Siegard Code</h1>

<p align="center">
  <strong>Autonomous agent infrastructure for Claude Code that ships features — from spec to delivery.</strong>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/version-1.1.0-blue?style=flat-square" alt="Version" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square" alt="License" /></a>
  <a href="https://docs.anthropic.com/en/docs/claude-code"><img src="https://img.shields.io/badge/works%20with-Claude%20Code-7C3AED?style=flat-square" alt="Works with Claude Code" /></a>
  <a href="#"><img src="https://img.shields.io/badge/agents-18-orange?style=flat-square" alt="18 Agents" /></a>
  <a href="#"><img src="https://img.shields.io/badge/skills-24+-yellow?style=flat-square" alt="24+ Skills" /></a>
</p>

<p align="center">
  <em>18 specialized agents. 3 coordinated teams. One command to orchestrate them all.</em>
</p>

---

Most AI coding tools help you write code. **Siegard Code** manages the entire development lifecycle — it writes specifications, plans backlogs, implements features, runs QA, and delivers tested code. All autonomously, all traceable, all through Claude Code.

You describe what you want. Siegard's agents handle the rest: the Spec team writes and validates technical specifications, the Dev team plans and implements Task Contracts with automated QA, and the Reverse Spec team can even document existing codebases. Every step produces artifacts. Every decision is logged. Every quality gate has teeth.

> **This is not a product.** It is the agent infrastructure you install into your own projects.

---

## Why Siegard Code?

| Pain point | How Siegard solves it |
|---|---|
| "AI writes code but ignores the spec" | Specs are the **single source of truth** — agents trace every line back to a Task Contract |
| "No one documents anything" | Documentation is a **byproduct**, not a chore — specs, backlogs, QA reports generated automatically |
| "Context gets lost between sessions" | **Session resume protocol** reconstructs state from disk artifacts — pick up where you left off |
| "AI makes changes I didn't ask for" | **Human confirmation required** at every major gate — nothing ships without your approval |
| "Testing is always an afterthought" | **QA is built into the pipeline** — every Task Contract passes through automated gate validation before delivery |
| "Design tokens drift across components" | **25 hard design system rules** (R1–R25) + Tailwind v4 token naming enforced by `/u-fe-validate` |

---

## Architecture

Three agent teams work in sequence, connected by formal handoff protocols:

```mermaid
graph TB
    subgraph INPUT["Input"]
        REQ[Requirement / Existing code]
    end

    subgraph RSPEC["Reverse Spec Team · 3 agents"]
        RSORC[Orchestrator]
        RSANA[Analyzer]
        RSWRT[Writer]
        RSORC --> RSANA --> RSWRT
    end

    subgraph SPEC["Spec Team · 6 agents"]
        SPORC[Orchestrator]
        SPWRT[Spec Writer]
        SPREV[Spec Reviewer]
        SPBCK[Back Spec Agent]
        SPFRT[Front Spec Agent]
        SPVAL[Spec Validator]
        SPORC --> SPWRT --> SPREV
        SPREV -->|APPROVED| SPBCK
        SPREV -->|REJECTED| SPWRT
        SPBCK --> SPVAL
        SPVAL -->|all back.md valid| SPFRT
        SPFRT --> SPVAL
        SPVAL -->|INVALID| SPBCK
        SPVAL -->|INVALID front| SPFRT
    end

    subgraph DEV["Dev Team · 9 agents"]
        DVORC[Orchestrator-Dev]
        PLAN[Planner]
        UIAG[UI Agent]
        DEVAG[Developer]
        QAAG[QA & Docs]
        DVORC --> PLAN --> UIAG --> DEVAG --> QAAG
        QAAG -->|REJECTED| DEVAG
    end

    REQ --> RSORC
    REQ --> SPORC
    RSWRT -->|specs · draft| SPORC
    SPVAL -->|VALID| DVORC
    QAAG -->|APPROVED| FIN[Delivery]
```

| Team | Agents | What it does |
|---|---|---|
| **Spec** | Orchestrator, Writer, Reviewer, Back Spec, Front Spec, Validator | Writes, reviews, and validates technical specifications |
| **Dev** | Orchestrator, Planner, UI Agent, Developer, QA & Docs (×2 FE/BE) | Plans backlogs, implements code, runs QA |
| **Reverse Spec** | Orchestrator, Analyzer, Writer | Reverse-engineers specs from existing code |

---

## Quick Start

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and configured

### Install into your project

Copy the contents of `dist/.claude/` into your project's `.claude/` directory:

```bash
cp -r dist/.claude/. /path/to/your-project/.claude/
```

The copy adds and replaces Siegard-managed files; it does not touch unmanaged files already in your project's `.claude/` directory.

Then check installation integrity (from your project root):

```bash
python3 .claude/scripts/verify_install.py
```

It compares every installed file against `.claude/siegard-manifest.json` and reports drift (modified, missing, or leftover files) as a JSON envelope — exit code `0` means the installation is intact.

### Configure your project

Add these fields to your project's `CLAUDE.md`:

```markdown
domain: backend           # or "frontend" — determines which pipeline runs
stack: Node.js, Express   # your tech stack (agents adapt, not hardcode)
specs_dir: docs/specs     # where specifications live

design_system:            # frontend projects only
  path: docs/design-system
  token_prefix: color     # Tailwind v4 @theme token prefix
```

### Run your first command

```bash
# Create a specification from requirements
/u-spec docs/specs

# Implement from approved specs
/u-dev docs/specs my-feature
```

That's it. The orchestrator detects the mode, activates the right agents, and guides you through every step.

---

## Commands

Slash commands cover the entire development lifecycle:

| Command | Purpose | Output |
|---|---|---|
| `/u-spec` | Create or evolve technical specifications | Approved specs in `{SPECS_DIR}` |
| `/u-dev` | Run a development session (plan → implement → QA) | Tested, delivered code |
| `/u-reverse-spec` | Generate specs from existing source code | Draft specs for review |
| `/u-spec-triage` | Fix spec validation errors incrementally | Corrected specs |
| `/u-improve` | Capture an improvement request | `improve_scope` YAML block |
| `/u-bug-report` | Capture a structured bug report | `bug##.md` |
| `/u-fe-validate` | Frontend code audit against design system rules | `fe-validate-{run_id}.yaml` |
| `/u-fe-review` | Ad-hoc frontend review with optional `--fix` mode | Structured findings |
| `/u-ui-design` | Design amplification and anti-pattern detection | Validated UI spec |

### Workflows

```
Feature (full):       /u-spec  →  /u-dev  →  /u-fe-validate
Quick improvement:    /u-improve  →  /u-dev
Bug fix:              /u-bug-report  →  /u-dev
Reverse + evolve:     /u-reverse-spec  →  /u-spec  →  /u-dev
Frontend audit:       /u-fe-validate  (standalone, any codebase)
```

---

## Key Features

### Task Contract Model
Every feature starts with a **Task Contract** — a formally structured execution unit that defines `task_contract` metadata (id, type, scope, dependencies) and an `execution_contract` (exec_type, input references, constraints, output schema, validation criteria). User Stories are not valid execution units. All agent-to-agent communication uses structured YAML envelopes validated against 13 YAML schemas.

### Spec-First Development
Specifications are the single source of truth — `openapi.yaml`, use cases, business rules, state machines, `feature.spec.md` (§1–§9 prescriptive structure), and `component.spec.md` (formal props contracts). No code is written without an approved spec.

### Automatic Mode Detection
The orchestrator reads your project state and selects the right mode: **Spec-first**, **Improve**, **Bug**, **Resume**, or **Reverse-eng review**. No flags, no configuration — it just works.

### Frontend & Backend Pipelines
One command, two pipelines. The `domain:` field in your `CLAUDE.md` routes to the correct agents. Frontend gets a UI Agent that gates on `ui-spec-gate { ready_for_development: true }` before developer proceeds; backend gets DI / DTO / pagination pattern validation.

### Design System Enforcement (R1–R25)
25 hard constraints cover spacing, typography, color usage (60-30-10 rule), border radius, touch targets, animations, z-index, and empty states. All tokens use Tailwind v4 `@theme` naming — inline `var(--token)` styles are a code quality violation. The `/u-fe-validate` skill checks 72 rules and produces a structured verdict (`approved` / `approved_with_caveats` / `rejected`).

### Quality Gates with Escalation
- **Spec Reviewer**: Max 3 rejection cycles before human escalation
- **Spec Validator**: Cross-reference validation with coverage reports
- **Developer Agent**: Emits `blocked-report.yaml` if execution_contract is missing; opens CR (`type: spec_gap`) on spec gaps
- **QA Agent**: Runs `/u-fe-validate`; test-gate with max 3 rework rounds
- Nothing passes silently — every gate produces artifacts

### Token-Efficient Context Management
- **Context mounting**: Each agent receives only what it needs
- **Short mode**: Reactivations use ~2K tokens instead of ~15K
- **Triage mode**: Process 5–10 errors per session, not 20+ at once

### Session Resilience
Interrupted? Run the same command again. The orchestrator reads its log file, reconstructs state from disk artifacts, and resumes from the exact stopping point.

---

## Project Structure

```
your-project/
├── .claude/
│   ├── agents/
│   │   ├── dev/                  # Dev team (FE + BE agents + protocols)
│   │   ├── spec/                 # Spec team (6 agents + protocols)
│   │   └── reverse-spec/         # Reverse Spec team (3 agents + protocols)
│   ├── commands/                 # Slash commands
│   └── skills/                   # 24+ reusable skill libraries
│       └── u-shared-templates/   # 13 YAML schemas + examples
├── CLAUDE.md                     # Your project configuration
├── {SPECS_DIR}/
│   ├── _global/                  # Shared: conventions, error codes, glossary
│   ├── domains/{domain}/         # Backend: openapi.yaml + spec.md + back.md
│   └── front/
│       ├── feature.spec.md       # §1–§9 prescriptive feature spec
│       ├── component.spec.md     # Props contract + states + events
│       ├── decisions.md          # Session-scoped architectural trade-offs
│       └── design-system/        # Tailwind v4 tokens, R1–R25 rules
└── {SESSIONS_DIR}/
    └── {SESSION}/                # Current session working directory
        ├── backlog.md            # Planned Task Contracts
        ├── TC-XX-delivery.md     # Delivery artifacts
        ├── TC-XX-qa.md           # QA reports (fe-validate-{run_id}.yaml)
        └── log-orchestrator-dev.md
```

---

## Action Guide

| I want to... | Commands |
|---|---|
| Build a complete feature | `/u-spec` → `/u-dev` → `/u-fe-validate` |
| Implement from existing specs | `/u-dev` |
| Fix a bug | `/u-bug-report` → `/u-dev` |
| Apply a quick improvement | `/u-improve` → `/u-dev` |
| Document existing code | `/u-reverse-spec` → `/u-spec` |
| Fix spec validation errors | `/u-spec-triage` |
| Report a spec problem from dev | `/u-spec` (reverse feedback mode) |
| Audit frontend code quality | `/u-fe-validate` |
| Review and fix frontend issues | `/u-fe-review --fix` |
| Validate visual design decisions | `/u-ui-design` |

---

## Documentation

| Section | Description |
|---|---|
| [Overview](docs-en/01-overview/README.md) | Architecture, concepts, glossary |
| [Installation](docs-en/02-installation/README.md) | Setup and project configuration |
| [Commands](docs-en/03-commands/README.md) | All commands in detail |
| [Agent Teams](docs-en/04-teams/README.md) | Spec, Dev, and Reverse Spec teams |
| [Execution Flows](docs-en/05-flows/README.md) | Step-by-step workflows |
| [Protocols](docs-en/06-protocols/README.md) | On-demand behavioral protocols |
| [Skills](docs-en/07-skills/README.md) | 24+ reusable skill libraries |
| [Artifacts](docs-en/08-artifacts/README.md) | Generated files and lifecycle |
| [Estimates](docs-en/09-estimates/README.md) | Token and time budgets |
| [Resilience](docs-en/10-resilience/README.md) | Failure scenarios and recovery |
| [Reference](docs-en/11-reference/README.md) | Cheat sheet and action guide |

---

## Estimates

| Mode | Tokens | Time | Scope |
|---|---|---|---|
| New spec (full pipeline) | ~19K | 7–12 min | Per domain |
| Fast-track spec change | ~11K | 4–7 min | Per change |
| Development (spec-first) | ~14K | 10–18 min | Per Task Contract |
| Development (improve) | ~10K | 8–13 min | Per Task Contract |
| Frontend validation (`/u-fe-validate`) | ~4K | 2–4 min | Per file glob |
| Triage | ~3K | 1–2 min | Per item |

## What's in v1.1

| Category | v1.0 | v1.1 | Delta |
|---|---|---|---|
| Skills | 18 | 24 | +6 |
| SDD Templates | 8 | 13 | +5 |
| YAML Schemas | 0 | 13 | +13 |
| Design system rules | ~40 informal | 150+ (R1–R25 hard) | +110 |
| Content lines | ~80k | ~118k | +47% |

---

## License

This project is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for attribution details.

---

<p align="center">
  <strong>Siegard Code</strong> — Because shipping features shouldn't mean losing control.
</p>
