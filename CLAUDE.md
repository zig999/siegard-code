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
├── docs-en/           # End-user documentation (English) for downstream projects
├── docs/              # Internal project documentation (diagrams, flow maps)
├── extras/            # Drafts, analysis notes, experimental artifacts — NOT published
├── tests/             # Test suite that validates dist/ artifacts (9 layers)
├── install.sh         # Deployment script: syncs dist/ → <target>/.claude/
├── skills-lock.json   # Locks external skill versions (analogous to package-lock.json)
└── assets/            # Static assets (logo, images)
```

### Directory rules

| Path | Purpose | Write rule |
|------|----------|------------|
| `dist/` | Published artifacts consumed by target projects | Only complete, validated artifacts |
| `docs-en/` | Human-readable docs shipped with the system | Update when commands/flows change |
| `docs/` | Internal diagrams and flow maps | Freely editable |
| `extras/` | Scratchpad: drafts, changelogs, analysis | Never referenced by agents |
| `tests/` | Automated validation of `dist/` | Must pass before promoting to `dist/` |

### install.sh

Copies and replaces files from `dist/` into `<target-project>/.claude/`. Does not remove existing files in the destination.

```bash
./install.sh <path-to-target-project>
```

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

* Structured
* Traceable
* Auditable

Never use free-form logs.

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

### Checklist before publishing a skill

* [ ] Documentation in `README.md` is complete
* [ ] At least 3 test cases covered
* [ ] Edge case behavior validated
* [ ] Dependencies on other skills explicitly declared
* [ ] Output schema defined and validated

---

## Distribution Directory (`./dist`)

All production-ready artifacts are located in `./dist`. This is the **distribution root** of the project — the only directory consumed by external projects.

```
dist/
├── agents/        # Agent definitions (dev, spec, reverse-spec)
├── commands/      # Entry-point command files (/u-spec, /u-dev, /u-improve, etc.)
├── skills/        # Reusable skill definitions and shared templates/schemas
└── templates/     # CLAUDE.md base templates for downstream projects
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
6. **Export** — promote artifact to `./dist`

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
