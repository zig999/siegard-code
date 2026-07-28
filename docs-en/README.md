# Siegard Code 2.0 — Documentation

> End-user documentation for the orchestration engine shipped in `dist/.claude/`.
> For implementation detail, reference the source artifacts under `dist/.claude/` directly.

---

## What this system is

Siegard Code is an **event-sourced orchestration engine for multi-phase workflows in Claude Code**. It coordinates parallel sub-agent execution, keeps auditable state in a single append-only log, and provides automatic retry, crash detection, and recovery — a native Temporal/Airflow for Claude workers.

The core is **domain-agnostic**: business logic (SDD, Dev, Review, Test) lives in pluggable phase-rule skills. The engine never changes; behavior changes through skills.

The model in one line: **the log is the truth — everything else is derived.**

---

## Core concepts

| Concept | Meaning |
|---|---|
| **Event log** | A single append-only, hash-chained `log.jsonl` per workflow. The only source of truth. |
| **Derived state** | Current phase, task status, retries — all computed by reducing the log on each read (P1, P2, P12). |
| **Phase** | A stage of the workflow with its own orchestrator, workers, and deterministic exit criteria. |
| **Meta-orchestrator** | The single entry point. Routes by phase, runs one phase per invocation. Zero domain logic. |
| **Phase orchestrator** | Owns one phase: dispatches workers, evaluates exit criteria, requests transitions. |
| **Worker** | A least-privilege sub-agent that performs one task type and returns a structured artifact. |
| **Exit criteria** | Testable Python scripts (not prompts) that gate every phase transition (P11). |

---

## Phases

```
sdd  →  dev  →  review  →  test
```

| Phase | Orchestrator | Purpose |
|---|---|---|
| **SDD** | `orchestrator-sdd` | Write, review, and validate specifications; produce the approved handoff manifest |
| **Dev** | `orchestrator-dev` | Plan the backlog and implement task contracts |
| **Review** | `orchestrator-review` | QA, architecture, and security review of deliveries |
| **Test** | `orchestrator-test` | Verification and final completion |

Canonical phase specification: [`../extras/phases.md`](../extras/phases.md).

---

## Documentation index

> **Status:** this index reflects the v2 architecture. The individual documents below will be authored in upcoming tasks. Until then, the source artifacts in `dist/.claude/` are authoritative.

| Document | Contents | Status |
|---|---|---|
| [`u-drift.md`](u-drift.md) | Spec ↔ code drift analysis — running `/u-drift`, reading the report, acting on findings | **Available** |
| [`upgrading.md`](upgrading.md) | Non-destructive upgrade of a target project: `verify_install.py` first, resolve every `modified` file, then copy | **Available** |
| `flow.md` | **Start here.** Phases, routing, gates, and the re-invocation loop end to end | Planned |
| `installation.md` | First-time manual copy into `<target>/.claude/` and project configuration (for upgrades see `upgrading.md`) | Planned |
| `commands.md` | Slash commands — `/u-orchestrator` and the rest | Planned |
| `agents.md` | Meta-orchestrator, the four phase orchestrators, and all workers | Planned |
| `workflow.md` | Engine internals: event sourcing, log reduction, dispatch loop, idempotency | Planned |
| `specs.md` | The SDD pipeline: spec writing, validation, handoff manifest | Planned |
| `artifacts.md` | Catalog of every artifact the system produces and its lifecycle | Planned |
| `resilience.md` | Failure modes, retry, circuit breaker, DLQ, crash recovery, escalation codes | Planned |
| `invariants.md` | The 12 architecture invariants (P1–P12) and how they are enforced | Planned |

---

## Commands

| Command | Purpose |
|---|---|
| `/u-orchestrator` | **Primary entry point** — start, resume, or advance a workflow from its event log |
| `/u-spec` | Create or evolve technical specifications (SDD phase entry) |
| `/u-dev` | Run an implementation session |
| `/u-improve` | Capture a structured improvement request |
| `/u-reverse-spec` | Generate specs from existing source code |
| `/u-drift` | Audit drift between approved specs and implemented code (read-only report) |
| `/u-fe-validate` | Frontend code audit against design-system rules |
| `/u-cleanup` | Garbage-collect orphaned blobs, worktrees, and stale sessions |
| `/u-doc-cleanup` | Documentation hygiene pass |

---

## The `dist/.claude/` layout

```
dist/.claude/
├── agents/
│   ├── orchestrator.md              # Meta-orchestrator (entry point, routes only)
│   ├── orchestrator-sdd.md          # Phase orchestrator — Spec & Design
│   ├── orchestrator-dev.md          # Phase orchestrator — Implementation
│   ├── orchestrator-review.md       # Phase orchestrator — QA & Approval
│   ├── orchestrator-test.md         # Phase orchestrator — Testing
│   ├── spec/                        # Spec phase workers
│   ├── dev/                         # Dev phase workers
│   └── reverse-spec/                # Reverse-engineering workers
├── commands/                        # Slash command entry points
├── hooks/                           # on_subagent_stop.py, on_stop.py, flow_guard.py (quality gates)
├── lib/                             # orch_core.py, sm_runner.py, minimal_yaml.py (stdlib only)
├── scripts/                         # preflight, circuit breaker, DLQ triage, GC, monitor, …
├── skills/                          # orch-* engine skills, phase-*-rules, u-* worker skills
├── settings.json                    # Claude Code settings for target projects
├── siegard-manifest.json            # Versioned inventory (SHA-256 per file)
└── ESCALATION_CODES.md              # Escalation code reference
```

Runtime state lives in the **target project** under `.orch/sessions/<workflow_id>/`, centered on the append-only `log.jsonl`.

### Flow guard (v2.34.0, exact mode v2.35.0)

`hooks/flow_guard.py` runs as a `PreToolUse` hook (wired in the shipped
`settings.json`). It deterministically blocks Write/Edit tool calls on
pipeline-owned artifacts — the specs tree (including `handoff-manifest.yaml`)
and `.orch/log.jsonl` — unless a registered pipeline worker is in flight, and
redirects the caller to the correct entry command (`/u-improve`, `/u-spec`).
This stops the host session from executing spec-flow steps inline instead of
routing through the pipeline (P7 — critical guarantees outside the LLM).
Operator kill-switch in `.orch/config.json`:
`{"guard": {"enforce": "hard" | "warn" | "off"}}` (default `hard`; `warn`
audits to `.orch/guard_warnings.jsonl` without blocking).

**Exact mode (v2.35.0, capability-gated):** on hosts whose `PreToolUse`
payload carries agent identity (`agent_id`/`agent_type` inside subagents —
present on Claude Code ≥ 2.1.220), the guard self-detects the capability
(`.orch/host_capabilities.json`) and then also blocks main-session writes
*while workers are in flight*, and writes from subagents whose type matches no
registered worker. Hosts that never provide the field stay in coarse mode —
a legitimate worker is never blocked by inference.

### Artifact provenance (v2.35.0)

Integrity gates prove the manifest matches the files; **PROV proves the files
came from the pipeline**. Three notarization sources feed the append-only log:
`emit.py` computes sha256 per declared worker artifact; the sdd phase records
a `spec_baseline_recorded` snapshot at entry (inherited state accepted — once
per workflow); `generate_handoff_manifest.py` notarizes the manifest it wrote.
`u-handoff-validator` then enforces PROV-010/020/030 at handoff, and
`orchestrator-dev` emits `handoff_receipt` on consumption and
`E25_unprovenanced_artifact` on failure (re-adoption route: `/u-improve`).
Workflows without a baseline (pre-2.35) degrade PROV to warnings. The
SubagentStop hook also gained exact correlation: it identifies the stopped
worker via its transcript (`ORCH_WORKER_ID` in the spawn prompt) and
synthesizes missing terminals immediately instead of waiting out the stale
threshold — older CLIs fall back to the liveness-gated path unchanged.

---

## Architecture invariants (P1–P12)

| # | Invariant |
|---|---|
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
