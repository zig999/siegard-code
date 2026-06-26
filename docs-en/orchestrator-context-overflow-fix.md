# Orchestrator — Context Overflow Fix

## Problem

When the meta-orchestrator was dispatched after the dev phase completed, the Agent tool call
returned "Tool result missing due to internal error" instead of a valid JSON envelope.

### Root cause

The meta-orchestrator was designed to loop through consecutive phase transitions in a single
invocation (up to 20 cycles, guarded by invariant I5). After a phase orchestrator returned
`phase_complete`, the meta-orchestrator re-read state, entered the next phase, and immediately
spawned the next phase orchestrator — all within the same context window.

In the failing scenario (dev complete → enter review → dispatch QA worker), the execution chain
was:

```
main agent
  └─ orchestrator (meta)              ← context accumulates across all iterations
       └─ orchestrator-dev            ← exit criteria evaluation
            → phase_transitioned(dev→review)
            → returns phase_complete
       ↩ meta-orchestrator loops
       → emits phase_entered(review)
       └─ orchestrator-review
            └─ u-be-qa-docs           ← 4th nesting level; context overflow here
```

Each loop iteration caused the meta-orchestrator to:
1. Re-read state (`reduce.py` outputs a growing JSON blob)
2. Receive subagent results (orchestrator-dev + orchestrator-review outputs)

After processing a dev phase with a large test suite (444 tests), the accumulated context
caused the meta-orchestrator to crash before returning its final envelope.
The main agent received "internal error" with no way to recover from that side.

### Cascade risk

If the circuit breaker check (`run_circuit_check.py`) itself returned non-JSON or errored
during the error-handling path in Step 7, the meta-orchestrator had no fallback — it would
silently fail instead of outputting a graceful `{"status": "error", ...}`.

---

## Fixes applied

### Fix 1 — Break the phase_complete loop (orchestrator.md)

**Files changed:** `agents/orchestrator.md`

**Invariant I5** was changed from "max 20 phase transitions per invocation" to:

> One phase orchestrator per invocation. When a phase orchestrator returns `phase_complete`
> and the workflow is not yet `completed`, output `phase_advanced` and stop.

**Step 7** `phase_complete` handler was changed from:

> Re-read state. Increment cycle counter. Loop back to Step 3 — do not stop.

To:

> Re-read state. Increment cycle counter. If `run_status == "completed"`: loop to Step 3
> (completion report). Otherwise: output `phase_advanced` report and stop.

**New output status `phase_advanced`** was added to the valid status table:

```json
{
  "status": "phase_advanced",
  "completed_phase": "<phase>",
  "next_phase": "<phase>",
  "workflow_id": "<id>",
  "last_seq": <n>
}
```

**Cycle counter safety limit** was lowered from 20 to 2. Under normal operation the counter
never exceeds 1 (I5 stops after the first `phase_complete`). Counter ≥ 2 indicates a logic bug.

**Effect:** Each meta-orchestrator invocation now handles exactly one phase orchestrator run.
Context is bounded per invocation regardless of workflow length or log size.

---

### Fix 2 — Graceful circuit check failure (orchestrator.md)

**Files changed:** `agents/orchestrator.md`

In the Step 7 error-handling path, before reading `status == "blocked"` from the circuit
breaker output, a guard was added:

> If `run_circuit_check.py` exits with an unexpected error or the output is not valid JSON:
> output `{"status": "error", "reason": "circuit_check_failed", ...}` and stop.

**Effect:** Prevents silent crash when the circuit breaker script itself fails during error
handling of a phase orchestrator failure.

---

### Fix 3 — Re-invocation loop in /u-dev (u-dev.md)

**Files changed:** `commands/u-dev.md`

The meta-orchestrator now stops after each `phase_advanced`. The `/u-dev` command was updated
to handle this by looping re-invocations until a terminal or human-interaction status is
reached:

| Status | Action |
|--------|--------|
| `phase_advanced` | Show one-line status update; re-invoke orchestrator immediately |
| `escalated` | Surface to human; stop |
| `completed` | Show completion report; stop |
| `blocked` | Surface to human; stop |
| `error` | Surface to human; stop |

Safety limit: max 10 re-invocations per `/u-dev` call.

**Effect:** The workflow still advances automatically between phases without human intervention,
but each phase runs in a fresh, bounded context. The caller accumulates only small JSON
envelopes (one per phase), not the full transcript of all phases combined.

---

## Nesting depth after fix

Before the fix:

```
main agent (0)
  └─ orchestrator (1)
       └─ orchestrator-dev (2)     [loops back]
       └─ orchestrator-review (2)
            └─ u-be-qa-docs (3)
```

All within a single orchestrator invocation — depth 3 from orchestrator, context grew across
all levels.

After the fix:

```
Invocation 1:
  main agent (0)
    └─ orchestrator (1)
         └─ orchestrator-dev (2)   → returns phase_complete → orchestrator stops

Invocation 2:
  main agent (0)
    └─ orchestrator (1)
         └─ orchestrator-review (2)
              └─ u-be-qa-docs (3)  → QA done → escalated → orchestrator stops
```

Each invocation is bounded. Maximum nesting depth is 3 (unchanged), but context resets
between invocations.

---

## Recovery protocol for existing stuck workflows

If the log already contains a `phase_transitioned(dev→review)` event but the main agent saw
"internal error":

```bash
# Check what events were actually written
python3 .claude/skills/orch-state/scripts/reduce.py
python3 .claude/skills/orch-state/scripts/current_phase.py
```

If `current_phase` is `null` (between dev and review): re-invoke the orchestrator. It will
emit `phase_entered(review)` and run `orchestrator-review` cleanly.

If `current_phase` is `review` (already entered): re-invoke the orchestrator. It will resume
the review dispatch from where it left off (idempotent via log-derived state).
