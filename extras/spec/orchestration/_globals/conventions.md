# Orchestration Spec — Conventions

> Version: 0.1.0 | Status: draft | Layer: permanent
> Scope: identifier prefixes, naming, versioning, and prohibited language for the
> orchestration-engine specification. Mirrors Siegard's `u-spec-globals/conventions.md`,
> adapted for infrastructure (no HTTP/UI) and extended with `INV-NN`.

## 1. Identifier prefixes

| Prefix | File | Meaning |
|--------|------|---------|
| `UC-NN` | `{domain}.spec.md` | Use Case — an engine operation triggered by an actor |
| `BR-NN` | `{domain}.spec.md` | Business Rule — a programmatically testable constraint |
| `INV-NN` | `_globals` / `{domain}.spec.md` | Architectural Invariant (P1–P12); BRs reference the INV they enforce |
| `ST-NN` | `{domain}.spec.md` | State machine (task / phase / run / circuit breaker) |
| `EV-NN` | `_globals/event-catalog.md` | Event type in the append-only log |
| `FL-NN` | `flows/*.flow.md` | Process-flow navigation rule |
| `FLOW-NN` | `flows/*.flow.md` | Process-flow document ID |
| `ERR-NN` | `_globals/error-catalog.md` | Failure taxonomy entry (exception, reason, or E-code) |
| `DEC-NN` | `decisions.md` | Architecture decision |
| `CR-NN` | change-request | Change request |

Actors are engine roles, not humans/business personas: `orchestrator` (meta),
`phase-orchestrator`, `worker`, `reaper` (stale-monitor), `hook` (on_stop /
on_subagent_stop), `operator` (human via escalation/human_response).

## 2. Numbering

- Sequential per type within a domain: `UC-01`, `UC-02`, … `EV-NN` is global (one catalog).
- **Never reuse a number**, even after removal — mark it `deprecated`.
- Cross-references use a verifiable anchor: `[INV-04](../_globals/conventions.md#inv-04-idempotency)`.
- Every claim that describes current behavior cites code as `` `path:line` `` (fidelity anchor).

## 3. Event naming (EV)

- `snake_case`, past-tense or noun-state (`task_completed`, `phase_transitioned`,
  `circuit_breaker_tripped`) — matches the `EventType` enum verbatim (`lib/orch_core.py:325`).
- An EV name in a spec MUST equal an `EventType` value. Introducing an EV in a spec
  without a matching enum member is a blocking validator error (Phase 2).

## 4. Versioning

| Bump | When |
|------|------|
| Patch (0.0.x) | Wording fixes, no contract change |
| Minor (0.x.0) | New UC / BR / INV / EV / ST, or a new optional field |
| Major (x.0.0) | Breaking change to an event schema, a state transition, or a CLI contract |

Status ladder: `draft` → `review` → `approved` → `deprecated`. At `approved`: zero
`TODO`, zero vague terms, every threshold explicit.

## 5. Layer classification

| Layer | Meaning | Examples here |
|-------|---------|---------------|
| `permanent` | defines behavior | all `.spec.md`, `.contract.md`, globals, flows |
| `semi-permanent` | explains execution | spec-map, validation reports |
| `ephemeral` | records a run | (none in this tree) |

## 6. Prohibited language

Forbidden vague terms (fail the AI-first completeness test): *may, generally,
adequate, appropriate, fast, reasonable, etc., similar to, coming soon, when
necessary, robust* (as an unquantified claim).

**Completeness test:** if two independent readers, using only a spec, would build
divergent implementations of any detail (a threshold, an ordering, a state edge, an
event field), that spec is incomplete. Concrete values are mandatory when known:
thresholds (`stale standard=300s`), formulas (`min(base·2^(n-1), cap)·U(0.8,1.2)`),
enum members, exit codes, idempotency keys.

## 7. Contract artifact (`.contract.md`)

Replaces `openapi.yaml`. Each domain's `.contract.md` specifies the engine's real
public surface:
- **CLI contracts** — for each script (`append.py`, `reduce.py`, `check_stale.py`,
  `emit.py`, checkers): invocation, args, stdin, stdout JSON schema, exit code.
- **Event schema** — for each EV the domain owns: required `data` fields (from
  `_REQUIRED_DATA_FIELDS`, `lib/orch_core.py:547`), types, validation.
- **Library contract** — for each public `orch_core` function the domain owns:
  signature, pre/post-conditions, raised exceptions.

## Changelog

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 0.1.0 | 2026-07-09 | orchestration-self-spec | minor | Initial conventions, adapted from SDD globals + INV/ERR prefixes | — |
