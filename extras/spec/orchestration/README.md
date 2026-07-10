# Siegard Orchestration Engine — Specification

> Version: 0.1.0 | Status: draft | Layer: permanent
> Methodology: Siegard SDD spec model, applied reflexively to the engine (self-spec)
> Fidelity: **prescriptive** — these documents define the *intended* contract of the
> engine. Where the current code diverges, the divergence is a conformance-backlog
> item (recorded in the Phase 2 review), not a silent edit to the spec.

This tree is the specification of Siegard's own event-driven orchestration engine,
written in the **same specification model Siegard produces during its SDD phase**
(the artifact taxonomy, ID prefixes, globals, and cross-validation rules used by
`u-spec-*`). It is Siegard specifying itself.

## Why this exists

The engine is documented today as narrative (`extras/phases.md`, `CLAUDE.md`) plus the
code itself. This tree re-expresses it as **structured, AI-first specifications**:
one intention per rule, controlled vocabulary, testable invariants, explicit
contracts — the same bar the framework imposes on downstream projects.

## Model adaptation (business app → infrastructure)

The SDD model targets business applications (domains, entities, HTTP endpoints, UI).
The engine is infrastructure — an event-sourced state machine with no business domain,
no HTTP, no UI. The mapping:

| SDD artifact (business) | Engine analog |
|---|---|
| `{domain}.spec.md` (UC/BR/ST/EV) | orchestration subsystem spec |
| UC-NN (actor + flow + operationId) | engine operation; actor = orchestrator / worker / hook / reaper |
| BR-NN (testable rule) + **INV-NN** (new) | derived rule + architectural invariant (P1–P12) |
| ST-NN (state machine) | `TaskStatus` / `PhaseStatus` / `run_status` / circuit breaker |
| EV-NN (domain event) | `EventType` catalog — literal fit (the engine IS event-sourced) |
| `error-codes.md` (HTTP) | E-code + `reason` enum + exception catalog |
| `openapi.yaml` (technical contract) | CLI/script contract + event JSON schema → `{domain}.contract.md` |
| cross-domain dependencies | subsystem dependencies (dispatch ⊂ log+state; resilience ⊂ state) |
| front.md / feature / flow-UI / component / design-system | **N/A** — no UI; omitted |
| `flow.md` (FLOW/FL) | reused as *process* flow (dispatch, retry, reaping, recovery, transition) |
| handoff-manifest | machine-readable index of this spec set |

New ID prefix **`INV-NN`** names the architectural invariants (P1–P12 in `CLAUDE.md`);
ordinary `BR-NN` rules reference the invariants they enforce. All other prefixes
(UC/BR/ST/EV/FL/FLOW/DEC/CR) match Siegard's `conventions.md` unchanged.

## Domains in scope

| # | Domain | Subsystem | Primary code |
|---|--------|-----------|--------------|
| 1 | `orch-log` | Append-only event log, hash chain, idempotency, blobs, verify, claim | `lib/orch_core.py`, `skills/orch-log/` |
| 2 | `orch-state` | Event→state reduction, task/phase state machines, tolerant reduce, snapshot | `lib/orch_core.py`, `skills/orch-state/` |
| 3 | `orch-dispatch` | Task lifecycle, worker registry, dispatch policy, least-privilege | `lib/orch_core.py`, `agents/orchestrator-*.md` |
| 4 | `orch-resilience` | Retry/backoff, circuit breaker, DLQ, stale reaper, liveness, crash recovery | `lib/orch_core.py`, `hooks/`, `scripts/` |
| 5 | `orch-phases` | Phase lifecycle, exit criteria, transitions, gates | `skills/phase-*-rules/`, `extras/phases.md` |
| 6 | `orch-control` | Meta + phase orchestrators, heartbeat, escalation, human response | `agents/orchestrator.md`, `agents/orchestrator-*.md` |

## Layout

```
extras/spec/orchestration/
├── README.md                 # this file — index + model adaptation
├── spec-map.md               # module → artifact mapping + coverage targets
├── _globals/
│   ├── conventions.md        # ID prefixes, naming, versioning, layer, prohibited terms
│   ├── event-catalog.md      # the EventType master list (EV-NN)
│   ├── error-catalog.md      # exceptions + failure/skip reasons + escalation E-codes
│   └── glossary.md           # controlled vocabulary
├── domains/
│   ├── orch-log/    {orch-log.spec.md, orch-log.contract.md}
│   ├── orch-state/  ...
│   ├── orch-dispatch/
│   ├── orch-resilience/
│   ├── orch-phases/
│   └── orch-control/
├── flows/                    # FLOW-01..05 (process flows)
└── _validation/              # Phase 2 validator reports + conformance backlog
```

## Phase status

| Phase | Scope | Status |
|-------|-------|--------|
| 0 — Planning | spec-map + globals + skeletons | done |
| 1 — Execution | write 6 domain specs + contracts + flows | done |
| 2 — Review | cross-validation + code-conformance backlog | done — 6/6 VALID, CONF-01..04 raised |
| 3 — Closure | handoff index + coverage matrix | done — `handoff.md`, `coverage-matrix.md` |

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Phase 0: index, model adaptation, domain decomposition | — |
