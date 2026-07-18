# Design Note — `/u-drift` (spec↔code drift analysis workflow)

> Internal design record. Not shipped in `dist/`.
> Establishes the invariants the `/u-drift` artifacts must hold.

## Problem

The lab has no way to audit **drift between approved specs and implemented code**.
Changes made outside the SDD pipeline (manual hotfix, direct spec edit, a legacy
base that evolved) are invisible. The one adjacent mechanism — the `merge` submode
of `/u-reverse-spec` — is **suspended** (`u-reverse-spec.md`), precisely because
deterministic conflict-resolution rules were never implemented. `/u-drift` produces
exactly that missing deterministic input.

## Objective

A workflow that, given a code directory and its approved specs, emits a
**deterministic, machine-consumable drift report** where every finding cites
evidence and maps to a mechanical follow-up action — no free-form recommendation,
no human interpretation step between output and next action (project CORE RULE).

## S0 decision — engine integration posture (resolves plan risk R2)

**Question:** should `/u-drift` run inside the orchestration engine (register
workers, emit task events) or standalone?

**Evidence gathered:**

| Fact | Source |
|---|---|
| `emit.py` standalone (no `ORCH_WORKER_ID`, no workers registry) exits 1 with `worker_id could not be inferred` | `orch-report/scripts/emit.py` worker-id resolution |
| `append_event` auto-bootstraps `.orch/` via `ensure_dirs()` and GENESIS chain, but the worker-id gate fails first | `lib/orch_core.py` `append_event` |
| `orchestrator-reverse-spec` does **not** register workers nor pass `task_id`/`attempt` to its analyzer/writer | grep of `orchestrator-reverse-spec.md` (no `register_worker`, no `task_id`) |
| The reverse-spec pipeline "runs entirely OUTSIDE the orchestration engine: no phase/task events, no heartbeats, no stale reaper" | `orchestrator-reverse-spec.md:114` |

**Decision: `/u-drift` runs STANDALONE, outside the engine — mirroring the
established reverse-spec precedent.**

- No `emit.py`, no synthetic task log, no `register_worker`, no engine preflight.
- The auditable trail is **`drift-report.json` itself**: each finding carries
  spec/code evidence (satisfies invariant P8), and the report carries a
  `spec_content_hash` + `code_commit_sha` for staleness detection (plan R8).
- When `/u-drift` invokes the reverse-spec analyzer in **code-inventory mode**,
  the activation prompt states explicitly *"standalone mode — do NOT emit
  orchestration events; no task_id is issued"* so the analyzer's `emit.py`
  boilerplate is never triggered.

**Consequence (accepted, documented):** a dead analyzer subagent during `/u-drift`
is detected by nothing — recovery is manual, identical to the reverse-spec flow.
This is acceptable for a read-only, single-shot, human-initiated analysis.

## Determinism boundary (resolves plan R3)

| Layer | Producer | Determinism |
|---|---|---|
| Spec inventory | `spec_inventory.py` (stdlib) | Deterministic — same specs → identical JSON |
| Code inventory | `u-reverse-spec-analyzer` (LLM) | Non-deterministic extraction, **constrained by `validate_inventory.py`**: schema-shape check + every `file:line` evidence must physically resolve (path exists, line ≤ file length). Invalid → 1 directed re-dispatch → still invalid = `blocked`. |
| Matching | `match_drift.py` (stdlib) | Deterministic — same two inventories → byte-identical findings |
| Severity / action | rules in `match_drift.py` | Deterministic table |
| Rendering | `render_report.py` (stdlib) | Deterministic — `drift-report.json` → identical `.md` |
| Semantic verdict (Release B) | `u-drift-analyzer` (LLM) | Constrained by `validate_findings.py`; escape hatch `undecidable`, never a guess |

## Structural vs semantic scope (design finding)

Only artifacts with a **code-derivable key** can be matched deterministically:

| Artifact | Key | Release |
|---|---|---|
| Endpoint | `{method} {normalized_path}` + `operationId` | A (structural) |
| Error code | code string + HTTP status | A (structural) |
| Entity / field | entity name / `entity.field` | A (structural) |
| State-machine state | `entity` + enum value | A (structural) |
| Domain event | event name string | A (structural) |
| **Business rule** | none — `BR-NN` has no code label | **B (semantic only)** |
| Drift *within* a matched item (status code changed, validation bound changed) | n/a — requires behavior comparison | **B (semantic)** |

Release A therefore reports `missing_in_code` / `missing_in_spec` / `aligned`
(present-on-both-sides-by-key) for the five keyable artifact classes. Release B
adds `business_rule` matching, refines a subset of `aligned` endpoints to
`drifted`, and introduces `undecidable`. The schema is forward-compatible: it
carries all statuses from Release A; B populates the remainder without a schema
change.

## Path normalization (resolves plan R6)

`match_drift.py` normalizes every endpoint before keying:
1. method → lowercase
2. path params → `{param}` (`:id`, `{id}`, `<id>` all → `{id}`; positional names collapse to `{param}` only when the spec/code names differ — see skill rules)
3. trailing slash stripped
4. `base_path` (router prefix) provided by the analyzer is stripped from code paths before comparison

Zero matches with **both** sides non-empty → a single finding
`base_path_mismatch_suspected` (blocking, `needs_human`). **Never** a heuristic
fallback that silently pairs unrelated endpoints.

## Direction of truth (resolves plan R5)

| Status | Truth assumption | default_action |
|---|---|---|
| `missing_in_code` | spec is truth (SDD principle) | `create_implementation_cr` |
| `missing_in_spec` (domain exists) | code is a fact to document | `update_spec` → `/u-improve` payload |
| `missing_in_spec` (no domain) | code is a fact to document | `create_spec` → scoped `/u-reverse-spec` |
| `drifted` | undecided | `needs_human` — finding carries **both** fix-spec and fix-code payloads |
| `undecidable` | undecided | `needs_human` |

## Release status

| Release | Scope | Status |
|---------|-------|--------|
| S0 | engine-integration decision (standalone) | Done — recorded above |
| A (v2.25.0) | structural drift: command, skill, 3 schema pairs, 5 scripts, analyzer code-inventory mode, tests | Done — full suite green |
| B (v2.26.0) | semantic layer: `u-drift-analyzer`, `drift-verdicts` pair, `validate_findings.py`, `merge_semantic.py`, tests | Done — full suite green |
| C | reverse-spec merge unsuspension | **Partial (deliberate).** Safe half shipped: the merge-suspended guidance now routes the compare-without-overwrite use case to `/u-drift` (the deterministic, auditable comparison the suspension said was missing). The **auto-apply resolver is intentionally NOT shipped** — auto-overwriting specs was suspended as a safety decision ("silently overwrite valid spec content"), and overriding it is a hard-to-reverse action that must not be rushed. Deferred follow-up below. |

### Release C follow-up — merge auto-apply resolver (deferred)

To fully unsuspend merge, a future change must add a resolver that consumes
`drift-report.json` and applies ONLY the safe, additive class automatically:
- `missing_in_spec` (domain exists) → append the documented artifact to the draft spec.
- `missing_in_code`, `drifted`, `undecidable` → never auto-applied (spec is truth /
  human triage) — surfaced, not resolved.

That resolver needs its own tests proving no `approved` spec is ever mutated and every
applied change is traceable to a finding id. It is out of scope for this delivery
because it changes safety-guarded behavior and warrants a focused, separately reviewed
change.

## QA remediation (post-build adversarial review)

| # | Finding | Resolution |
|---|---------|------------|
| QA-1 | `spec_content_hash` embedded absolute paths → not reproducible across checkouts | Fixed — `sha256_of_files` hashes paths relative to `specs_dir`; regression test `test_content_hash_portable_across_paths` |
| QA-2 | `u-drift-analyzer` (and reverse-spec analyzer's code-inventory mode) lacked `Write` for JSON emission | Fixed — added `Write` to both agents' `allowed-tools` |
| QA-3 | openapi parse failure degraded silently to zero endpoints (fabricated drift) | Fixed — the domain is now excluded and surfaced as `skipped/parse_failed`; regression test `test_openapi_parse_failure_skips_domain` |
| QA-4 | runtime `spec-inventory`/`code-inventory` outputs had no schema regression guard | Fixed — added `test_runtime_output_validates_against_schema` and `TestCodeInventoryExample` |
| QA-5 | `normalize_path` collapses all params to `{param}` → sibling param routes collide | Accepted tradeoff (documented in SKILL.md); side-independent normalization requires it |
| QA-6 | domain status read from `.spec.md` only | Fixed — a back-spec explicitly draft/review while the business spec is approved now marks the domain not-approved (skipped) with a diagnostic; regression test `test_inconsistent_status_spec_approved_back_draft_skipped` |
| QA-7 | `drift-report.yaml` example's aligned ref format differed from runtime | Fixed — example now uses the runtime `ST User` format |
| QA-8 | `merge_semantic` could fold an out-of-contract endpoint verdict into a contradictory finding | Fixed (final review) — endpoint verdicts outside the structural aligned set are ignored; regression test `test_out_of_contract_endpoint_verdict_ignored` |

## Scope guard (resolves plan R7)

Only specs with `Status: approved` are audited. `draft` specs are recorded in the
report's `skipped[]` (metadata, not findings) — auditing reverse-spec-generated
drafts against the code that generated them measures nothing. Zero approved specs
→ `blocked`, code `no_approved_specs`.
