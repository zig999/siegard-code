# FLOW-06 — Supervised auto-resume

> Flow ID: FLOW-06 | Status: draft | Layer: permanent
> Objective: a stalled phase orchestrator is re-invoked automatically — bounded and
> non-destructively — without a human, while a persistently stuck workflow still escalates
> to a human instead of looping forever. Automates FLOW-04 node K (act on the
> stale-orchestrator diagnostic) under a resume budget.
> Domains involved: orch-control (UC-08 supervised resume), orch-resilience (UC-08 detect,
> BR-08 bounded resume).

## 1. Involved use cases

| # | Domain | UC |
|---|--------|----|
| 1 | orch-control | UC-08 supervised auto-resume, UC-06 enforce foreground/Bash, UC-03 escalate |
| 2 | orch-resilience | UC-08 detect stalled orchestrator, BR-08 bounded auto-resume |

## 2. Happy path

```mermaid
flowchart TD
  A[/u-supervise tick (via /loop or /schedule)/] --> B{Step 0: Bash available?}
  B -->|no| Z[[E_NO_BASH → blocked, stop]]:::error
  B -->|yes| C[[supervisor_tick.py: reduce + detect_stale_orchestrator]]
  C --> D{active phase stalled?<br/>no heartbeat AND no task activity}
  D -->|no| N([no action — tick again later])
  D -->|yes| E{resume budget remaining?}
  E -->|no| F[[append escalation E23_resume_budget_exhausted]]:::error
  F --> G([run halts — awaiting human])
  E -->|yes| H{cooldown / in-flight guard clear?}
  H -->|no| N
  H -->|yes| I[[append orchestrator_resume_requested]]
  I --> J[[/u-supervise: re-check stale]]
  J -->|recovered| N
  J -->|still stalled| K[[re-invoke meta-orchestrator — FOREGROUND, non-destructive]]
  K --> L[[append orchestrator_resumed]]
  L --> M([dispatch resumes; state re-derives from intact log])
  classDef error fill:#f88
```

## 3. Alternative flows

| # | Condition | From | To | Behavior |
|---|-----------|------|----|----------|
| A1 | worker still emitting `task_progress` | detect | no action | TOTAL PHASE SILENCE guard: recent `last_event_at` ⇒ phase alive ⇒ no resume (BR-08) |
| A2 | budget exhausted | budget | escalation | `E23_resume_budget_exhausted` (warning); `run_status=escalated`, sticky until `human_response` |
| A3 | orchestrator recovered between tick and re-invoke | re-check | no action | fresh heartbeat/activity newer than the request ⇒ skip re-invoke, no `orchestrator_resumed` |
| A4 | `/u-supervise` crashed after `resume_requested` | in-flight | expire | a request older than `in_flight_ttl_seconds` with no `resumed`/heartbeat is expired ⇒ no permanent wedge |
| A5 | run already `escalated` | tick | no action | supervisor is a no-op while awaiting a human |

## 4. Process rules (FL)

### FL-01 — Re-invoke is non-destructive
The supervisor only re-runs the meta-orchestrator, which re-derives from the intact log
(INV-01/INV-02). The destructive `verify_and_recover` is never triggered here — it stays
manual and gated (orch-resilience BR-07 / FLOW-04 FL-03).

### FL-02 — Bounded, log-derived
Budget, cooldown, and in-flight state are counted from the log (`orchestrator_resumed` /
`orchestrator_resume_requested`, audit-only), not from external state. A stuck workflow can
be resumed at most `max_auto_resumes` times per phase before it escalates to a human.

### FL-03 — Foreground only
The re-invoke needs the Bash tool; the supervisor is a foreground driver (`/loop` or
`/schedule`) and fails fast with `E_NO_BASH` (control UC-06) rather than stalling in a
background sandbox.

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-10 | consulta-web-report-audit | minor | Supervised auto-resume flow (E2 / B(b)) | — |
