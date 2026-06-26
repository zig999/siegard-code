---
name: orch-infra
description: Shared infrastructure checks run at the start of every orchestrator cycle — run_preflight.py, run_integrity.py, run_circuit_check.py. Any non-zero exit blocks the cycle with status blocked. Loaded by all orchestrators. Not user-invocable — orchestrators run the scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *)
---

# orch-infra

Shared infrastructure skill: run preflight, integrity, and circuit-breaker checks at the start of every orchestrator cycle.

## Usage contract

Every orchestrator loads this skill and calls all three scripts at the start of each cycle:

```bash
python3 .claude/skills/orch-infra/scripts/run_preflight.py
python3 .claude/skills/orch-infra/scripts/run_integrity.py
python3 .claude/skills/orch-infra/scripts/run_circuit_check.py
```

On any non-zero exit: stop and return `{"status": "blocked"}` to the meta-orchestrator.

## Output envelope (all scripts)

Every script emits exactly one JSON object to stdout:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `"ok"` \| `"blocked"` | Pass/fail verdict |
| `check` | string | `"preflight"` \| `"integrity"` \| `"circuit"` |
| `timestamp` | string | ISO 8601 UTC timestamp |
| `reason` | string | Present only on `"blocked"` — machine-readable failure code |
| `detail` | object | Present only on `"blocked"` — additional context |

## scripts/run_preflight.py

Runs `preflight.py --quick` (local runtime checks only). Returns blocked if any check fails.

```bash
python3 .claude/skills/orch-infra/scripts/run_preflight.py
```

Exit codes: `0` = all checks passed, `1` = at least one check failed or exec error.

Example output (ok):
```json
{"status": "ok", "check": "preflight", "timestamp": "...", "passed": 5, "total": 5, "failed_count": 0}
```

Example output (blocked):
```json
{
  "status": "blocked",
  "check": "preflight",
  "timestamp": "...",
  "reason": "preflight_failed",
  "passed": 4,
  "total": 5,
  "failed_count": 1,
  "failed_checks": [{"check": "flock_works", "reason": "fcntl not available"}]
}
```

## scripts/run_integrity.py

Verifies the hash chain of the orchestration log in strict mode. Returns ok if no log exists (first run).

```bash
python3 .claude/skills/orch-infra/scripts/run_integrity.py
```

Exit codes: `0` = chain intact (or no log), `1` = chain invalid or error.

Example output (ok):
```json
{"status": "ok", "check": "integrity", "timestamp": "...", "events_verified": 42}
```

Example output (blocked):
```json
{
  "status": "blocked",
  "check": "integrity",
  "timestamp": "...",
  "reason": "chain_invalid",
  "events_verified": 41,
  "first_error_seq": 42,
  "truncation_candidate": 42
}
```

## scripts/run_circuit_check.py

Evaluates circuit breaker state. Returns blocked if the circuit is tripped or should trip.
Returns ok if no log exists (first run).

```bash
python3 .claude/skills/orch-infra/scripts/run_circuit_check.py
```

Exit codes: `0` = circuit open (healthy), `1` = circuit tripped or evaluation error.

Example output (ok):
```json
{"status": "ok", "check": "circuit", "timestamp": "...", "tripped": false, "failure_count": 2, "threshold": 50}
```

Example output (blocked):
```json
{
  "status": "blocked",
  "check": "circuit",
  "timestamp": "...",
  "reason": "circuit_tripped",
  "tripped": true,
  "failure_count": 52,
  "threshold": 50
}
```

## What orch-infra does NOT do

- Does not know about phases or domains
- Does not read spec files or delivery artifacts
- Does not interact with humans
- Does not emit events to the log
