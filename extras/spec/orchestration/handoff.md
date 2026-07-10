# Orchestration Spec — Handoff Manifest (Phase 3)

> Version: 0.1.0 | Status: approved | Layer: semi-permanent
> The machine-readable index of the orchestration self-spec, analogous to the SDD
> `handoff-manifest.yaml`. Delivered by: orchestration-self-spec. Type: reverse_eng.

## Inventory

| Artifact | Version | Layer | sha256 (16) |
|----------|---------|-------|-------------|
| README.md | 0.1.0 | permanent | 21ce58b727d483f1 |
| spec-map.md | 0.1.0 | semi-permanent | 7c34ca0a6cd9d122 |
| _globals/conventions.md | 0.1.0 | permanent | 115edfd0f9a6233d |
| _globals/event-catalog.md | 0.1.0 | permanent | 406aeb18e6462b17 |
| _globals/error-catalog.md | 0.1.0 | permanent | d2d31ba4ff9417b2 |
| _globals/glossary.md | 0.1.0 | permanent | dee145c638276783 |
| domains/orch-log/orch-log.spec.md | 0.1.0 | permanent | 9cb2653bf64a54ab |
| domains/orch-log/orch-log.contract.md | 0.1.0 | permanent | 3d4aa7afe414753d |
| domains/orch-state/orch-state.spec.md | 0.1.0 | permanent | 57b08e92e5d638a9 |
| domains/orch-state/orch-state.contract.md | 0.1.0 | permanent | 9a4ebb13a5ec4bbf |
| domains/orch-dispatch/orch-dispatch.spec.md | 0.1.0 | permanent | 6400dad85f673bce |
| domains/orch-dispatch/orch-dispatch.contract.md | 0.1.0 | permanent | 1b1b07638ef0e801 |
| domains/orch-resilience/orch-resilience.spec.md | 0.1.0 | permanent | e2b096d54afaa5c4 |
| domains/orch-resilience/orch-resilience.contract.md | 0.1.0 | permanent | c5a130a65970fed4 |
| domains/orch-phases/orch-phases.spec.md | 0.1.0 | permanent | 658c971421b26001 |
| domains/orch-phases/orch-phases.contract.md | 0.1.0 | permanent | 3bb7241887d042ba |
| domains/orch-control/orch-control.spec.md | 0.1.0 | permanent | 89f68bbd8773137c |
| domains/orch-control/orch-control.contract.md | 0.1.0 | permanent | 4e12d5d28ba4c5e6 |
| flows/FLOW-01-dispatch-cycle.flow.md | 0.1.0 | permanent | 5560af52b1e64d73 |
| flows/FLOW-02-retry-cycle.flow.md | 0.1.0 | permanent | c23d30b1c471ac34 |
| flows/FLOW-03-stale-reaping-reconciliation.flow.md | 0.1.0 | permanent | 9e85a17987b5b24d |
| flows/FLOW-04-crash-recovery.flow.md | 0.1.0 | permanent | a913f31a922e539c |
| flows/FLOW-05-phase-transition.flow.md | 0.1.0 | permanent | 83c94efdbbc6a153 |
| _validation/validation-report.md | 0.1.0 | semi-permanent | c8afa81f14a7b7f0 |
| _validation/conformance-backlog.md | 0.1.0 | semi-permanent | 626f35072d5d6a00 |

> sha256 truncated to 16 hex; regenerate with `sha256sum` on edit (this manifest and
> `coverage-matrix.md` are excluded from their own hash list).

## Domains delivered

| Domain | spec_version | contract_version | validation |
|--------|--------------|------------------|------------|
| orch-log | 0.1.0 | 0.1.0 | VALID |
| orch-state | 0.1.0 | 0.1.0 | VALID |
| orch-dispatch | 0.1.0 | 0.1.0 | VALID |
| orch-resilience | 0.1.0 | 0.1.0 | VALID (CONF-01/02) |
| orch-phases | 0.1.0 | 0.1.0 | VALID |
| orch-control | 0.1.0 | 0.1.0 | VALID |

## Status

- Phases 0–3 complete. 6/6 domains VALID (`_validation/validation-report.md`).
- 4 open conformance items (`_validation/conformance-backlog.md`) — engine-side, not
  spec defects; candidates for a follow-up fix cycle.
- Coverage: `coverage-matrix.md`. Deferred: test-phase orchestrator, worker internals.

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Handoff index: 25 artifacts, sha256, per-domain verdicts | — |
