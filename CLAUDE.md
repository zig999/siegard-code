# CLAUDE.md — AI FIRST AGENT LAB (v2)

## Project Purpose

This project is a **Claude Code agent development lab**.
Its sole purpose is to design, build, and refine agent and skill structures that will be **reused in other projects**.

> **Important:** This repository is not a product. It is the agent infrastructure that powers other projects.

---

## Project Structure

```
siegard-code/
├── dist/              # Distribution root — production artifacts (see below)
│   └── .claude/       # Copied manually into <target>/.claude/ (see Installation)
├── docs-en/           # End-user documentation (English) for downstream projects
├── docs/              # Internal project documentation (diagrams, flow maps)
├── extras/            # Reference specs, architecture docs, event schemas — NOT published
├── tests/             # Test suite that validates dist/ artifacts
├── skills-lock.json   # Locks external skill versions (analogous to package-lock.json)
└── assets/            # Static assets (logo, images)
```

### Directory rules

| Path | Purpose | Write rule |
|------|----------|------------|
| `dist/` | Published artifacts consumed by target projects | Only complete, validated artifacts |
| `docs-en/` | Human-readable docs shipped with the system | Update when commands/flows change |
| `docs/` | Internal diagrams and flow maps | Freely editable |
| `extras/` | Reference specs and architecture docs | Read-only during implementation — edit only when architecture changes |
| `tests/` | Automated validation of `dist/` | Must pass before promoting to `dist/` |

### Installation (manual copy)

There is no install script. Installation is a manual copy of the contents of `dist/.claude/` into `<target-project>/.claude/`. Consequence for every artifact in `dist/`: it must be **self-describing** — provenance, version, and usage context must travel inside the copied files themselves, because no tooling runs at install time.

Provenance mechanism: `dist/.claude/siegard-manifest.json` (versioned inventory, SHA-256 per file) + `dist/.claude/scripts/verify_install.py` (integrity check runnable inside the target). Both travel with the copy.

### Release flow (versioned distribution)

1. Change artifacts in `dist/` and pass the test suite
2. `python3 gen_manifest.py` — regenerates the manifest (use `--version X.Y.Z` to bump)
3. Suite green again (`tests/test_manifest_integrity.py` fails on a stale manifest) → commit → tag `vX.Y.Z`

> Any commit that touches `dist/` MUST regenerate the manifest — the suite enforces this.

### skills-lock.json

Locks the version (hash) of externally sourced skills. Update when pulling a new version of an external skill. Format mirrors a package-lock — one entry per skill with `source`, `sourceType`, and `computedHash`.

---

## 🧠 AI FIRST PRINCIPLE

This project operates under an **AI FIRST paradigm**.

> All artifacts must be designed to be consumed by agents first, and humans second.

This means:

* Prefer **structure over narrative**
* Prefer **contracts over interpretation**
* Prefer **determinism over flexibility**

---

## ⚙️ CORE RULE

> **Every agent output must be directly consumable by another agent without interpretation.**

If a human needs to interpret the output, it is incorrect.

---

## Agent Principles

Agents developed here must be:

* **Autonomous** — capable of completing tasks with minimal human intervention
* **Modular** — each skill must be independent and reusable
* **Portable** — easily importable into other Claude Code projects
* **Testable** — all behavior must be verifiable in isolation
* **Deterministic** — outputs must be predictable and schema-compliant

---

## 🧩 AI FIRST WRITING RULES

### DO

* Use **structured formats**: YAML, JSON, or strict Markdown
* Always define:

  * objective
  * input
  * constraints
  * output format
  * validation criteria
* Use **one intention per instruction**
* Use **explicit and objective language**
* Define **limits and boundaries**
* Use **controlled vocabulary**
* Return **structured failure states when needed**

Example:

```yaml
status: blocked
reason: missing_input
missing:
  - api_contract
```

---

### DON'T

* Do not write free-form text for agent communication
* Do not mix multiple intentions in a single instruction
* Do not use vague terms:

  * better
  * appropriate
  * fast
* Do not assume missing context
* Do not produce outputs outside defined schema
* Do not use conversational language:

  * please
  * if possible
* Do not make implicit decisions

---

## 📐 SPEC VS EXECUTION

### Specification Layer (Persistent)

* Defines system behavior
* Human-readable, but structured
* Includes:

  * business rules
  * domain context
  * constraints

### Execution Layer (AI Operational)

* Driven by:

  * task contracts
  * schemas
  * protocols

> Specifications are not prompts.
> They are structured context used to generate execution.

---

## 🔁 TASK MODEL (MANDATORY)

User Stories are not valid execution units for agents.

All work must be broken into **structured Tasks**:

```yaml
task:
  id: <id>
  type: <type>
  objective: <single objective>

input:
  context: <required data>

constraints:
  - <explicit rules>

output:
  format: <format>
  schema: <structure>

validation:
  criteria:
    - <objective rule>
```

---

## 🔗 AGENT COMMUNICATION

All agent-to-agent communication must:

* Use structured envelopes
* Follow predefined schemas
* Contain no free text
* Be validated before consumption

---

## 🧾 LOGGING

Logs must be:

* Structured (append-only JSONL with SHA-256 hash chain)
* Traceable
* Auditable

Never use free-form logs.

---

## Orchestration Engine

This project builds and ships an **event-driven orchestration engine** for Claude Code workflows. The engine manages tasks, workers, retries, failures, and phase-based state — without encoding business logic from downstream projects.

> Canonical reference: `extras/phases.md`

### Architecture

```
User → orchestrator → [task_created × N] → specialized workers
                    ↑                              ↓
                 log.jsonl  ←←←← task_completed / task_failed
```

Skills (`u-spec`, `u-dev`, etc.) operate as worker internals under orchestrator coordination. Manual prompt chaining is replaced by event-driven dispatch with automatic retry, full traceability, and crash recovery.

### Delivery Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| Phase 1 — Orchestration Engine | Event-sourced log, dispatcher, worker lifecycle, retry, circuit breaker — phase-agnostic | Complete |
| Phase 2 — Phase Rules | `phase-{name}-rules/` skills and phase-specific workers; engine unchanged | Complete |
| Phase 3 — Merge with siegard | Legacy skills become worker internals; event-driven coordination replaces manual chaining | Current |

### Architecture Invariants

These invariants are enforced across all artifacts in this project:

| # | Invariant |
|---|-----------|
| P1 | Log is the truth. All state is derived. |
| P2 | Orchestrator is a pure function of the log. No own state. |
| P3 | Append-only. Corrections via new events. |
| P4 | Idempotency by key `(task_id, attempt, event_type)`. |
| P5 | Deterministic ordering. Ties resolved by `(priority, seq)`. |
| P6 | Least privilege. Workers have only the tools they need. |
| P7 | Robustness via hooks. Critical guarantees outside the LLM. |
| P8 | Evidence mandatory. Every decision cites the events that justify it. |
| P9 | Every task belongs to exactly one phase. |
| P10 | Phase transition is an auditable event. |
| P11 | Exit criteria in testable code, not in prompts. |
| P12 | Current phase is derived from the log, not stored outside it. |

### Constraints

- Zero external Python dependencies — stdlib 3.10+ only
- Do not deviate from `extras/phases.md` without explicit instruction
- Do not implement business logic from downstream projects
- **Orchestrators require foreground.** The meta-orchestrator and every phase orchestrator depend on the Bash tool for all infra checks, log appends, and worker dispatch. A subagent spawned in background runs in a reduced-permission sandbox without Bash and stalls silently. Only read-only leaf workers may run in background. The meta-orchestrator fails fast with `E_NO_BASH` (Step 0) and `preflight.py`'s `bash_available` check enforces this deterministically.

---

## Claude Code Settings

### Model

Always use `claude-sonnet-4-6` unless explicitly instructed otherwise.

### Search rules

* For any textual search, use `/ccc` before Glob/Grep (when available)

### Default behavior

* Always respond in **Brazilian Portuguese (PT-BR)** unless context requires otherwise
* Prefer objective and direct responses
* Do not restate the task before executing it
* When creating files, always check if they already exist before overwriting

### Tool usage

* Prefer native Claude Code tools before creating custom scripts
* When creating a new tool, document it immediately in `docs/tools.md`
* Tools must have explicit error handling

---

## Skill Development

Each skill must follow this standard:

### Frontmatter standard (MANDATORY)

Every directory under `dist/.claude/skills/` MUST contain a `SKILL.md` that begins with valid YAML frontmatter. This applies to ALL skill types — executable skills, phase-rules skills, and resource bundles (template/schema directories). No exceptions.

```yaml
---
name: <skill-name>            # MUST equal the directory name exactly
description: <see rules>      # routing signal — written for the dispatcher, not for humans
user-invocable: true|false    # explicit boolean, never omitted
allowed-tools: <tool list>    # MANDATORY when the skill executes tools (P6 — least privilege)
---
```

Rules:

* `description` MUST state: what the skill does, who consumes it, and `Not user-invocable` when applicable. In English, single paragraph, trigger-oriented — skill routing is driven by this field
* `name` MUST equal the directory name — divergence breaks discovery and cross-references
* `allowed-tools` lives in frontmatter ONLY — never as a `## allowed-tools` prose section in the body (frontmatter is the single source; prose is not enforced)
* Resource bundles (templates, schemas, globals) ship a `SKILL.md` index: frontmatter + table of files with producer/consumer per file
* Enforcement: `tests/test_layer1_skill_frontmatter.py` validates all of the above — it MUST pass before promoting any skill to `dist/`

### Checklist before publishing a skill

* [ ] `SKILL.md` frontmatter valid per the Frontmatter standard (`name` == directory, `description`, `user-invocable`, `allowed-tools` when applicable)
* [ ] Documentation in `README.md` is complete
* [ ] At least 3 test cases covered
* [ ] Edge case behavior validated
* [ ] Dependencies on other skills explicitly declared
* [ ] Output schema defined and validated

---

## Distribution Directory (`./dist`)

All production-ready artifacts are located in `./dist`. Its contents are deployed by manually copying `dist/.claude/` into `<target>/.claude/` — no install tooling runs, so every artifact must carry its own provenance and context.

```
dist/
└── .claude/
    ├── agents/        # orchestrator.md + phase orchestrators (orchestrator-sdd.md, etc.)
    ├── commands/      # Entry-point commands (/u-spec, /u-dev, /u-improve, etc.)
    ├── hooks/         # on_subagent_stop.py, on_stop.py
    ├── lib/           # orch_core.py (shared library, no external deps)
    ├── scripts/       # preflight.py, circuit_breaker.py, dlq_triage.py, gc_orphan_blobs.py
    ├── settings.json  # Claude Code settings for target projects
    └── skills/        # orch-log, orch-state, orch-report, phase-*-rules, u-* skills
```

### Rules for `./dist`

* All content in `./dist` must be written in **English**
* Every artifact placed in `./dist` is considered **published** — it must be complete and schema-compliant
* Do not place work-in-progress artifacts in `./dist`
* Skills, agents, and commands outside `./dist` are considered **draft** until explicitly promoted

---

## Workflow

1. **Design** — define structure, contracts, and schemas
2. **Develop** — implement agent or skill
3. **Test** — validate behavior in isolation
4. **Validate** — ensure schema and protocol compliance
5. **Document** — update `docs/`
6. **Export** — promote artifact to `./dist/.claude/`

---

## 🚫 What NOT to do here

* Do not implement business logic from external projects
* Do not connect to production APIs
* Do not store credentials or sensitive data
* Do not create circular dependencies between skills
* Do not generate non-structured outputs
* Do not bypass validation rules

---

## 🧪 QUALITY SYSTEM

All agents must operate under:

* Input validation
* Output validation
* Schema enforcement
* Hook-based quality gates

---

## Environment

* All developed projects run on Windows operating system

---

## 📌 FINAL STATEMENT

**This repository does not build software.
It builds the structured intelligence that allows agents to build software.**
