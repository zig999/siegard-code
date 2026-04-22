# Architecture

## 1. Overview

Siegard v2 solves three recurring problems in multi-step Claude Code workflows:

| Problem | Solution |
|---------|---------|
| Context loss between invocations | Append-only event log; all state reconstructed from it |
| Execution inconsistency | Orchestrator is a pure function of the log; same log → same decisions |
| Auditability deficit | Every decision, spawn, failure, and transition is an auditable event |

**Mental model**: a workflow engine (analogous to Temporal or Airflow) built natively for Claude Code. Workers are sub-agents; coordination is event-driven; retries are automatic; crashes are recoverable.

---

## 2. Architecture Invariants

Twelve non-negotiable principles enforced across every component:

| # | Invariant | Implication |
|---|-----------|------------|
| P1 | Log is the truth | All state derives from events. No mutable state outside the log. |
| P2 | Orchestrator is pure | Same log → same decisions. No memory between cycles. |
| P3 | Append-only | Never edit events. Corrections are new events. |
| P4 | Idempotency | `(task_id, attempt, event_type)` uniquely identifies an event; duplicate = no-op. |
| P5 | Deterministic ordering | Ties broken by `(priority desc, seq asc)`. No randomness in dispatch. |
| P6 | Least privilege | Each worker gets minimum tools needed. Code-reviewer cannot write. |
| P7 | Robustness via hooks | Critical guarantees (detecting silent workers) run in hooks, not LLM prompts. |
| P8 | Evidence mandatory | Every orchestrator event cites the log seqs that justify it. |
| P9 | One phase per task | Every task has exactly one `phase` field, declared at creation. |
| P10 | Phase transitions auditable | `phase_entered` and `phase_transitioned` are explicit events. |
| P11 | Exit criteria in code | Evaluated by `check_*.py` scripts, not prompts. Deterministic. |
| P12 | Current phase derived | Computed from `phase_entered`/`phase_transitioned` events; never stored outside log. |

---

## 3. System Components

```
dist2/.claude/
├── agents/
│   ├── orchestrator.md              # Meta-orchestrator (tier 1)
│   ├── orchestrators/
│   │   ├── orchestrator-sdd.md      # Phase orchestrator — Specification & Design
│   │   ├── orchestrator-dev.md      # Phase orchestrator — Implementation
│   │   ├── orchestrator-review.md   # Phase orchestrator — QA & Approval
│   │   └── orchestrator-test.md     # Phase orchestrator — Testing (pending)
│   └── workers/                     # Spec, dev, QA, and planning workers
├── skills/
│   ├── orch-log/                    # append.py, read.py, verify.py
│   ├── orch-state/                  # reduce.py, snapshot.py, current_phase.py, summary.py
│   ├── orch-report/                 # emit.py (worker → log interface, guard-railed)
│   ├── orch-infra/                  # shared infra utilities
│   ├── phase-sdd-rules/             # SDD worker routing + exit criteria scripts
│   ├── phase-dev-rules/             # Dev worker routing + exit criteria scripts
│   └── phase-review-rules/          # Review worker routing + exit criteria scripts
├── hooks/
│   ├── on_subagent_stop.py          # Synthesizes task_failed for silent workers
│   └── on_stop.py                   # Persists final snapshot + metrics
├── scripts/
│   ├── preflight.py                 # Pre-run environment checks
│   ├── circuit_breaker.py           # Inspect/reset circuit breaker
│   ├── dlq_triage.py                # DLQ categorization
│   └── gc_orphan_blobs.py           # Blob GC
└── lib/
    └── orch_core.py                 # Shared library; all logic; stdlib 3.10+ only
```

---

## 4. Two-Tier Orchestration Model

### Tier 1: Meta-Orchestrator (`orchestrator.md`)

**Zero domain logic.** Routes to the correct phase orchestrator and advances phases.

```
User invokes orchestrator
  │
  ▼
Derive current_phase from log
  │
  ├─ null ──────────────────► emit phase_declared + phase_entered(sdd)
  │                           spawn orchestrator-sdd
  │
  ├─ sdd (active) ──────────► spawn orchestrator-sdd (resume)
  │
  ├─ sdd (completed) ───────► emit phase_entered(dev)
  │                           spawn orchestrator-dev
  │
  ├─ dev (completed) ───────► emit phase_entered(review)
  │                           spawn orchestrator-review
  │
  └─ review (completed) ────► emit workflow completion event; stop
```

**Invariants (M1–M6)**:
- M1: Meta has zero domain logic — no spec, backlog, or QA knowledge
- M2: Only meta spawns phase orchestrators; phase orchestrators never spawn each other
- M3: Each phase orchestrator is sole emitter for its phase's domain events
- M4: Phase orchestrators are stateless across invocations (derive all state from log)
- M5: `phase_entered` is emitted by meta, never by phase orchestrators
- M6: `phase_transitioned` is emitted by the outgoing phase orchestrator before returning

### Tier 2: Phase Orchestrators

Domain-specific coordinators. Know the rules, workers, and exit criteria of their phase.
See [phases.md](phases.md) for per-phase details.

---

## 5. Parallel Dispatch

Originally sequential (one worker at a time). Redesigned to leverage Claude Code's ability to emit multiple `Agent` calls in a single response turn.

### Mechanism

```
Orchestrator response turn N:
  Agent(worker_A, prompt=...)     ← emitted together
  Agent(worker_B, prompt=...)     ← emitted together

Claude Code runs worker_A and worker_B concurrently.
Orchestrator resumes in response turn N+1 with both results.
```

### Dispatch loop (Step 6)

```
6.0 — Pre-loop checks
      Check circuit breaker status; evaluate stale tasks; cascade DLQ to blocked deps;
      re-queue scheduled tasks whose backoff has expired.

6.1 — Select batch
      Up to 2 ready tasks: priority desc, seq asc.

6.2 — Claim all (no spawning yet)
      For each task in batch: emit task_claimed(task_id, attempt, worker_id).
      All claims are serial (flock-serialized).

6.3 — Spawn all in parallel
      Emit one Agent() call per claimed task in this same response turn.
      Workers receive env vars via prompt (not shell inheritance).

6.4 — Verify terminal events
      After all workers return: re-read state.
      If status == running: worker exited silently → synthesize task_failed(retryable=true).

6.5 — Retry decisions
      For each failed task: apply should_retry policy.
      Emit task_scheduled_retry or task_dlq as appropriate.

6.6 — Exit criteria check
      Run phase check_*.py scripts.
      Emit phase_exit_criterion_met per satisfied criterion.
      If all met: emit phase_exit_approved → phase_transitioned; return.
```

### Why env vars are in the prompt, not the shell

Workers are sub-agents spawned via `Agent()` — they do not inherit the orchestrator's shell environment. The prompt is the communication channel. Workers receive `ORCH_TASK_ID`, `ORCH_ATTEMPT`, `ORCH_WORKER_ID`, `ORCH_PROJECT_DIR`, and `SPECS_DIR` as embedded text and set them as local bash env vars before calling `emit.py`.

---

## 6. Confirmation Gates (Human-in-the-Loop)

Phase orchestrators that require human confirmation (SDD and Review) use the escalation pattern:

```
1. Phase orchestrator emits escalation(code="E99", question="...", options=[...])
2. Meta-orchestrator detects escalated run_status; returns question to user
3. Human emits human_response (action="confirm_proceed" | "abort" | "return_to_dev")
4. Next orchestrator cycle reads human_response from log; resumes
```

Every human decision is an event — fully auditable. Orchestrators never block between response turns.

---

## 7. Key Architectural Decisions (ADRs)

### ADR-1: Two-Tier Orchestration

**Changed from**: Single orchestrator + dynamically loaded `phase-{name}-rules` skills.

**Changed to**: Meta-orchestrator (zero domain logic) + four phase orchestrators.

**Reason**: Each phase has a fundamentally different human interaction model (SDD = confirmation gates; Dev = autonomous; Review = approval gate; Test = fully autonomous). A single orchestrator accumulates phase-specific exceptions that violate the phase-agnostic principle.

---

### ADR-2: Parallel Dispatch via Multiple Agent Calls

**Changed from**: Sequential loop; one worker per turn.

**Changed to**: Multiple `Agent()` calls per response turn; Claude Code runs them concurrently.

**Reason**: Requirement F2 — "coordinate parallel execution respecting dependencies." Sequential dispatch means at most one worker active per cycle regardless of batch size.

**Side effect**: Shell `export ORCH_*` removed (confusing in parallel context; prompt is the real channel).

---

### ADR-3: Confirmation Gates via Escalation Events

**Changed from**: Blocking wait inside the orchestrator's response turn.

**Changed to**: Async `escalation` + `human_response` events (see §6).

**Reason**: Orchestrators are stateless; cannot hold state across invocations to wait for a human.

---

### ADR-4: Stack Detection via handoff-manifest.yaml

**Changed from**: `select_worker.py` hardcoded per project type.

**Changed to**: `orchestrator-dev` reads `handoff-manifest.yaml` from SDD output; passes `--stack <be|fe|fullstack>` to `select_worker.py`.

**Reason**: Same `phase-dev-rules/` serves all project types without reconfiguration.

---

### ADR-5: emit.py Guard-Rail is a Security Boundary

**Decision**: `emit.py` accepts only `task_progress`, `task_completed`, `task_failed`. All orchestrator-type events are rejected unconditionally, even if the calling prompt requests them.

**Reason**: Workers must never be able to emit `task_claimed`, `task_dlq`, `escalation`, etc. This constraint must be enforced outside the LLM, in code.

---

### ADR-6: Blob Paths Relative to ORCH_DIR

**Changed from**: CWD-relative paths (`.orch/blobs/evt_XYZ.json`).

**Changed to**: Paths relative to `ORCH_DIR` (`blobs/evt_XYZ.json`), resolved via `ORCH_DIR / ref`.

**Reason**: CWD-relative paths break when the project is moved or CI runs from a different directory.

---

### ADR-7: Snapshots Deferred Post-Pilot

**Decision**: Task 1.8 (periodic snapshots every 100 events) deferred. `reduce_all()` used everywhere.

**Reason**: No production performance data. `reduce_all()` latency is acceptable for current log sizes. Resume condition: `reduce.py` latency exceeds 2s in production.
