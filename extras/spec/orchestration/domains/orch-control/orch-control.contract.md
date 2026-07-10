# orch-control — Technical Contract

> Stack: Python 3.10+ stdlib + Claude Code agents | Version: 0.1.0 | Status: draft | Layer: permanent
> Business spec: `orch-control.spec.md`

## 1. Stack and Patterns

| Aspect | Value | Note |
|--------|-------|------|
| Control | agent prompts (`orchestrator*.md`), Bash-driven | foreground required |
| Infra checks | `orch-infra` scripts | run at cycle start |
| Classification | `classify_run_status.py` | tolerant reduce (read-only) |
| Purity | `reduce_all` each cycle | no own state (INV-02) |

## 2. Data Model

### Escalation envelope (`escalation.data`)

`{ code, severity(info|warning|critical), reason, evidence[], suggested_actions[] }`.

### Human response (`human_response.data`)

`{ escalation_seq, action(approve|abort|reset_circuit_breaker|…), operator }`.

## 3. CLI Contracts

| Script | Purpose | stdout |
|--------|---------|--------|
| `preflight.py` | infra + `bash_available` + config sanity | `{...checks, "bash_available": bool}`; non-zero blocks cycle |
| `orch-infra/…/run_integrity.py` | hash-chain integrity (cached) | verdict; non-zero blocks |
| `orch-infra/…/run_circuit_check.py` | breaker window check | verdict; may trip breaker |
| `classify_run_status.py` | `[--project-dir <p>]` | `{ "status":"ok", "run_status": <ST-04>, "active_escalation": …, "reduce_violations": [...] }` |

## 4. Agent contract (meta step protocol)

The meta-orchestrator (`orchestrator.md`) runs, per cycle:
`Step 0` E_NO_BASH guard → `orch-infra` (preflight/integrity/circuit) → `reduce_all`
→ dispatch/transition via phase orchestrators → `orchestrator_heartbeat`. Phase
orchestrators run their own dispatch cycle (orch-dispatch UC-03) and exit checks
(orch-phases UC-03). All infra work is foreground/Bash (CLAUDE.md).

## 5. Out of Scope

- Exit-criteria scripts (orch-phases contract).
- Retry/stale/breaker library (orch-resilience contract).

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Escalation/human envelopes, infra CLI, meta step protocol | — |
