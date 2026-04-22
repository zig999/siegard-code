# Siegard v2 — Documentation Index

Siegard v2 is a multi-phase orchestration engine for Claude Code workflows. It replaces manual prompt chaining with event-driven coordination, automatic retry, full traceability, and crash recovery.

## Documents

| File | Contents |
|------|----------|
| [architecture.md](architecture.md) | System overview, 12 invariants, two-tier orchestration model, parallel dispatch, ADRs |
| [event-system.md](event-system.md) | Append-only JSONL log, hash chain, all 21 event types with payload schemas |
| [phases.md](phases.md) | SDD, Dev, Review, Test — worker routing, execution flow, exit criteria |
| [worker-contract.md](worker-contract.md) | Worker lifecycle, environment variables, emission protocol, artifact schemas |
| [reliability.md](reliability.md) | Retry policy, circuit breaker, DLQ triage, crash recovery |
| [api-reference.md](api-reference.md) | `orch_core.py` — all public functions, dataclasses, enums, exceptions |

## Quick reference

```
User → meta-orchestrator → phase orchestrator → workers
                                ↓
                        .orch/log.jsonl   ←   task_completed / task_failed
```

### Log location

```
.orch/
├── log.jsonl           # append-only JSONL; single source of truth
├── log.jsonl.lock      # POSIX flock lock file
├── blobs/              # externalized payloads > 3500 bytes
├── dlq/                # dead-letter queue entries
├── state/              # snapshots (every 100 events)
└── metrics/            # operational metrics
```

### Key scripts

| Script | Purpose |
|--------|---------|
| `scripts/preflight.py` | Environment readiness checks before first run |
| `scripts/circuit_breaker.py` | Inspect or reset the circuit breaker |
| `scripts/dlq_triage.py` | Triage DLQ tasks into categories |
| `scripts/gc_orphan_blobs.py` | Remove orphaned blob files |
| `skills/orch-log/scripts/verify.py` | Verify hash chain integrity |
| `skills/orch-state/scripts/reduce.py` | Rebuild state from log |
| `skills/orch-state/scripts/current_phase.py` | Current phase status |

### Install

```bash
./install.sh <path-to-target-project>
```

Copies `dist2/` → `<target>/.claude/`. Requires Python 3.10+.
