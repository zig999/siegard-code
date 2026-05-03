---
name: u-handoff-validator
description: Validates a handoff-manifest.yaml against schema and semantic rules before it is consumed by Dev orchestrators. Single source of truth for manifest validation — replaces inline checks in BE and FE orchestrator cores.
user-invocable: false
---

# SKILL: Handoff Manifest Validator

## Purpose

Validate the canonical `handoff-manifest.yaml` produced by `u-spec-orchestrator` before any Dev orchestrator consumes it. Returns a structured envelope (`handoff-validation-envelope.yaml`) that the caller uses to decide whether to proceed, halt, or escalate.

This skill consolidates rules that previously lived inline in `u-be-orchestrator-core.md` and `u-fe-orchestrator-core.md`. Both orchestrators now invoke this skill instead of duplicating checks.

## When invoked

- By `u-be-orchestrator-core` at session start, if `{SPECS_DIR}/handoff-manifest.yaml` exists
- By `u-fe-orchestrator-core` at session start, if `{SPECS_DIR}/handoff-manifest.yaml` exists
- By `u-spec-to-dev-handoff` protocol before writing a new manifest (pre-write validation)

## Inputs

| Field | Value |
|---|---|
| `manifest_path` | Absolute path to `{SPECS_DIR}/handoff-manifest.yaml` |
| `caller` | `u-be-orchestrator-core` \| `u-fe-orchestrator-core` \| `u-spec-orchestrator` |
| `specs_dir` | Absolute path to `{SPECS_DIR}/` — used to resolve package paths for integrity checks |

## Outputs

A single `handoff-validation-envelope.yaml` object conforming to `handoff-validation-envelope.schema.yaml`. No free text. The caller MUST NOT interpret narrative — only the envelope fields.

## Validation rules

Rules are declared in `rules.yaml`. Each rule has:
- `id` — stable identifier (FLOW-NNN or HDF-NNN)
- `severity` — `blocking` (halt) or `warning` (log + proceed)
- `applies_to` — list of callers that must run the rule
- `check` — declarative predicate

### Rule catalog

| ID | Description | Severity | Applies to |
|---|---|---|---|
| FLOW-030 | `handoff.delivered_by` must be `u-spec-orchestrator` | blocking | all |
| FLOW-031 | `domains[]` must have at least 1 entry | blocking | all |
| FLOW-032 | `backend_package[]` must have at least 1 entry | blocking | be |
| FLOW-033 | `new_domain` handoff must NOT include `change_summary` | blocking | all |
| FLOW-034 | `major_evolution` and `fast_track` handoffs MUST include `change_summary` | blocking | all |
| FLOW-035 | `change_summary.dev_impact` must be a valid enum value | blocking | all |
| FLOW-036 | `fast_track` requires `change_summary.type` in `[patch, minor]`; `major_evolution` requires `major` | blocking | all |
| FLOW-037 | `backend_package[]` must include both `openapi` and `back-spec` artifacts | blocking | be |
| HDF-010 | `handoff.type` must be in `{new_domain, major_evolution, fast_track, reverse_eng}` | blocking | all |
| HDF-020 | Every `backend_package[].sha256` must match the actual file at `{specs_dir}/{path}` | blocking | be |
| HDF-021 | Every `frontend_package[].sha256` must match the actual file at `{specs_dir}/{path}` | blocking | fe |
| HDF-030 | `change_summary.dev_impact = stop_domain_task_contracts` — caller must halt affected domains | blocking | all |
| HDF-040 | `frontend_artifacts` omitted for backend-only handoffs — otherwise required fields present | blocking | fe |

Rules marked `be` run only when `caller = u-be-orchestrator-core`. Rules marked `fe` run only when `caller = u-fe-orchestrator-core`. Rules marked `all` always run.

## Execution protocol

1. Load `manifest_path`. If file missing → emit envelope with `status: invalid` and `errors: [{rule: HDF-000, message: "manifest not found"}]`.
2. Run schema conformance (JSON Schema draft-07 against `handoff-manifest.schema.yaml`). If fails → emit envelope with `status: invalid` and the schema violations as errors. Stop.
3. For each rule in `rules.yaml` whose `applies_to` includes `caller`:
   - Run the declarative check
   - If pass → append `{rule, status: pass}` to `checks[]`
   - If fail blocking → append `{rule, status: fail}` to `checks[]` and a structured entry to `errors[]`
   - If fail warning → append `{rule, status: fail}` to `checks[]` and a structured entry to `warnings[]`
4. Emit final envelope:
   - `status: valid` when `errors` is empty
   - `status: invalid` otherwise

## Envelope consumption rules

The caller MUST:
- Halt and escalate to human when `status: invalid`
- Halt affected domains when `checks[]` contains a `pass` entry for `HDF-030` (dev_impact = stop_domain_task_contracts)
- Proceed normally when `status: valid` and no halt rule triggered
- Never attempt to interpret `errors[].message` — only act on `errors[].rule`

## Envelope shape

```yaml
validation_envelope:
  validated_by: u-handoff-validator
  timestamp: <ISO-8601>
  manifest_id: <HANDOFF-YYYYMMDD-HHMMSS>
  manifest_sha256: <sha256 of manifest file>
  caller: u-be-orchestrator-core | u-fe-orchestrator-core | u-spec-orchestrator
  layer: ephemeral

status: valid | invalid

checks:
  - rule: FLOW-030 | FLOW-031 | ... | HDF-NNN
    status: pass | fail
    severity: blocking | warning

errors:
  - rule: <rule-id>
    message: <structured, non-narrative>
    path: <JSONPath into manifest — e.g., $.backend_package[2].sha256>

warnings:
  - rule: <rule-id>
    message: <structured, non-narrative>
    path: <JSONPath into manifest>
```

## Versioning

When adding or changing a rule:
1. Update `rules.yaml`
2. Update the rule catalog table in this SKILL.md
3. Add a fixture pair (valid + invalid) under `tests/dist/fixtures/`
4. Extend `tests/dist/layer5-flows.test.js` (or a dedicated handoff-validator layer) to cover the new rule

New rule IDs: use `HDF-NNN` (handoff-specific) for rules introduced after the extraction. FLOW-NNN IDs are preserved for backward compatibility with existing tests.
