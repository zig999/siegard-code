# CLAUDE.md — new_flow (Orchestration Engine)

> Subproject of `siegard-code`.
> Working directory: `new_flow/`
> Distribution target: `new_flow/dist2/`
> Canonical reference: `new_flow/extras/architecture.md`

---

## Purpose

Build the **orchestration engine** for Claude Code workflows: event infrastructure, dispatcher, and worker management. Phase-specific logic (SDD, Dev, QA) is out of scope for this subproject and will be incorporated later.

This subproject produces a deployable `.claude/` structure that enables:
- Event-sourced state via append-only JSONL log with SHA-256 hash chain
- Orchestrator/worker sub-agent coordination (dispatcher)
- Deterministic retry, circuit breaking, and crash recovery
- Phase-agnostic task and worker lifecycle management

The output (`dist2/`) is consumed by downstream projects via `install.sh`.

---

## Scope Boundaries

### In scope — build now

| Component | Description |
|---|---|
| `lib/orch_core.py` | Event sourcing engine: schema, I/O, hash chain, reducer, locking, retry, circuit breaker |
| `skills/orch-log` | Append, read, verify — the log itself |
| `skills/orch-state` | Reduce, snapshot, current_phase — derived state |
| `skills/orch-report` | Emit with guard-rail — worker→log interface |
| `agents/orchestrator.md` | Dispatcher: reads log, decides, spawns workers, emits events |
| `agents/workers` | Generic worker base structure (no phase logic) |
| `hooks/on_subagent_stop.py` | Detects workers that stopped without terminal event |
| `hooks/on_stop.py` | Persists final snapshot and metrics |
| `scripts/` | Operational scripts: preflight, circuit_breaker, dlq_triage, gc_orphan_blobs |

### Out of scope — incorporated later

- `phase-sdd-rules/`, `phase-dev-rules/`, `phase-review-rules/`, `phase-test-rules/`
- Phase-specific workers (sdd-analyst, sdd-decomposer, etc.)
- Phase transition logic and exit criteria
- Feature decomposition

---

## Delivery Sequence and Final Goal

### Phase 1 — new_flow (this subproject)

Build the orchestration engine, phase-agnostic:

```
orch_core.py → orch-log → orch-state → orch-report → hooks → orchestrator → workers
```

Outcome: a system that manages tasks, workers, retries, failures, and state — without knowing what the tasks do.

### Phase 2 — Phase rules (future, still in new_flow)

Add `phase-{name}-rules/` skills and phase-specific workers. The engine from Phase 1 is unchanged.

### Phase 3 — Merge with siegard

Today siegard works like this:

```
User → /u-spec → /u-dev → /u-improve   (manual skill chaining via prompt)
```

After the merge:

```
User → orchestrator → [task_created × N] → specialized workers
                    ↑                              ↓
                 log.jsonl  ←←←← task_completed / task_failed
```

The existing siegard skills (`u-spec`, `u-dev`, etc.) become the internal logic of workers. What today is manual prompt chaining becomes **event-driven coordination** by the orchestrator — with automatic retry, full traceability, and crash recovery.

---

## Reference Documents

All specs live in `new_flow/extras/`. The implementation plan references them — use the paths below (not the `specs/` prefix used inside the plan, which is incorrect):

| Document | Use for |
|---|---|
| `extras/architecture.md` | System design, invariants, component behavior |
| `extras/orch_core_api.md` | API contracts, function signatures, exceptions |
| `extras/event-schema.md` | JSON schemas for all 21 event types |
| `extras/TEST_SCENARIOS.md` | Test cases referenced per task in the plan |
| `extras/IMPLEMENTATION_PLAN.md` | Task decomposition, acceptance criteria, build order |

---

## Constraints

- All content in `dist2/` must be written in **English**
- Zero external Python dependencies — stdlib 3.10+ only
- Every artifact must be complete and schema-compliant before landing in `dist2/`
- Do not deviate from the architecture in `extras/architecture.md` without explicit instruction
- Do not implement business logic from downstream projects

---

## Directory Layout

```
new_flow/
├── CLAUDE.md              ← this file
├── extras/
│   ├── architecture.md        ← canonical architecture reference (read-only)
│   ├── orch_core_api.md       ← orch_core.py full API spec (read-only)
│   ├── event-schema.md        ← JSON schemas for all 21 event types (read-only)
│   ├── TEST_SCENARIOS.md      ← test scenarios referenced by implementation plan (read-only)
│   └── IMPLEMENTATION_PLAN.md ← 45-task implementation plan (read-only)
└── dist2/                 ← distribution root (target for all built artifacts)
    └── .claude/
        ├── agents/        ← orchestrator + generic worker sub-agents
        ├── skills/        ← orch-log, orch-state, orch-report  (phase-* added later)
        ├── hooks/         ← on_subagent_stop.py, on_stop.py
        ├── scripts/       ← preflight.py, circuit_breaker.py, dlq_triage.py, gc_orphan_blobs.py
        └── lib/           ← orch_core.py (shared library)
```

---

## Build Order (Phase 1)

Dependencies flow strictly downward. Do not build a layer before its dependency is complete and validated.

```
1. lib/orch_core.py              ← foundation; everything depends on this
2. skills/orch-log/              ← append, read, verify
3. skills/orch-state/            ← reduce, snapshot, summary, current_phase
4. skills/orch-report/           ← emit (with guard-rail: blocks orchestrator events)
5. hooks/on_subagent_stop.py     ← depends on orch-report emit contract
6. hooks/on_stop.py              ← depends on orch-state reduce
7. agents/orchestrator.md        ← depends on all skills above
8. agents/workers (generic)      ← base worker structure, no phase logic
9. scripts/ (operational)        ← preflight, circuit_breaker, dlq_triage, gc_orphan_blobs
```

---

## Architecture Invariants

These principles from `extras/architecture.md` must be enforced in every artifact:

| # | Invariant |
|---|---|
| P1 | Log is the truth. All state is derived. |
| P2 | Orchestrator is a pure function of the log. No own state. |
| P3 | Append-only. Corrections via new events. |
| P4 | Idempotency by key `(task_id, attempt, event_type)`. |
| P5 | Deterministic ordering. Ties resolved by (priority, seq). |
| P6 | Least privilege. Workers have only the tools they need. |
| P7 | Robustness via hooks. Critical guarantees outside the LLM. |
| P8 | Evidence mandatory. Every decision cites the events that justify it. |
| P9 | Every task belongs to exactly one phase. |
| P10 | Phase transition is an auditable event. |
| P11 | Exit criteria in testable code, not in prompts. |
| P12 | Current phase is derived from the log, not stored outside it. |

---

## Critical Implementation Notes

### `orch_core.py`
- The single shared library imported by all scripts
- Must be self-contained; no imports outside Python 3.10+ stdlib
- Modules: Schema, I/O, Integrity (hash chain), Blobs, Reducer, Snapshots, Locking (`fcntl.flock`), Retry, Circuit breaker

### `emit.py` (orch-report skill)
- **Guard-rail is non-negotiable**: must reject any event type that belongs to the orchestrator, even if the caller prompt requests it
- This is a security boundary, not a soft constraint

### `on_subagent_stop.py`
- Reads env vars `ORCH_TASK_ID`, `ORCH_ATTEMPT`, `ORCH_WORKER_ID`
- If absent: no-op (not an orchestrated worker context)
- If present and last task event is not terminal: synthesizes `task_failed(retryable=true)`

### `orchestrator.md`
- Model: `opus`
- Loads skills statically: `orch-log`, `orch-state`
- Loads dynamically: `phase-{current}-rules` based on active phase
- Never executes concrete work; only coordinates

### Workers
- Each emits exactly **one** terminal event (`task_completed` or `task_failed`)
- Must load `orch-report` skill
- Cannot emit orchestrator-type events (enforced by `emit.py`)

---

## Inherited Rules (from siegard-code)

- AI FIRST: every artifact must be consumable by agents first, humans second
- Prefer structure over narrative; contracts over interpretation
- All agent-to-agent communication uses structured envelopes, no free text
- Every task must have: `objective`, `input`, `constraints`, `output.format`, `output.schema`, `validation.criteria`
- Do not place work-in-progress artifacts in `dist2/`
