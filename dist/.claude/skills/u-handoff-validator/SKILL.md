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

`validate.py` prints a single JSON envelope to stdout (see **Envelope shape**) and signals validity via exit code (`0` valid / `1` invalid). The caller acts only on `status`, `errors[]` (rule-id-prefixed strings), and `halt_signal`. The envelope conforms to `handoff-validation-envelope.schema.yaml`.

## Validation rules

The deployed implementation is **`validate.py`** (stdlib-only, prod-hardening task 03b): it loads the manifest via `minimal_yaml`, evaluates the 13 rules below, and prints a flat JSON envelope. `rules.yaml` is the declarative catalog — documentation, NOT loaded at runtime. Each rule has:
- `id` — stable identifier (FLOW-NNN or HDF-NNN)
- `severity` — `blocking` (populates `errors[]`) or `warning` (populates `warnings[]`)
- `applies_to` — DESCRIPTIVE ONLY: which caller the rule matters to. `validate.py` evaluates **all** rules regardless of `--caller`; scoping is data-driven (see note under the catalog).
- `check` — declarative description of the predicate `validate.py` hard-codes

### Rule catalog

| ID | Description | Severity | Applies to |
|---|---|---|---|
| FLOW-030 | `handoff.delivered_by` must be `u-spec-orchestrator` | blocking | all |
| FLOW-031 | `domains[]` must have at least 1 entry | blocking | all |
| FLOW-032 | `backend_package[]` must have at least 1 entry | blocking | be |
| FLOW-033 | `new_domain` handoff must NOT include `change_summary` | blocking | all |
| FLOW-034 | `major_evolution`, `fast_track`, and `reverse_eng` handoffs MUST include `change_summary` | blocking | all |
| FLOW-035 | `change_summary.dev_impact` must be a valid enum value | blocking | all |
| FLOW-036 | `change_summary.type` must match `handoff.type`: fast_track → `[patch, minor]`; major_evolution → `[major]`; reverse_eng → `[patch, minor, major]` | blocking | all |
| FLOW-037 | for `new_domain`/`major_evolution`, `backend_package[]` must include both `openapi` and `back-spec` | blocking | be\* |
| HDF-010 | `handoff.type` must be in `{new_domain, major_evolution, fast_track, reverse_eng}` | blocking | all |
| HDF-020 | Every `backend_package[].sha256` must match the actual file at `{specs_dir}/{path}` | blocking | be |
| HDF-021 | Every `frontend_package[].sha256` must match the actual file at `{specs_dir}/{path}` | blocking | fe |
| HDF-030 | `change_summary.dev_impact = stop_domain_task_contracts` — caller must halt affected domains | blocking | all |
| HDF-040 | `frontend_artifacts` omitted for backend-only handoffs — otherwise required fields present | blocking | fe |

> \* The **Applies to** column is descriptive (which caller the rule matters to). `validate.py` evaluates **all** rules regardless of `--caller`; scoping is data-driven: FLOW-037 fires only for `new_domain`/`major_evolution`, HDF-021 only when `frontend_package` is present, HDF-040 only when `frontend_artifacts` is present.

## Execution protocol

`validate.py --manifest <path> --specs-dir <dir> [--caller <id>]`:

1. Load `manifest_path` via the stdlib `minimal_yaml` loader. If the file is missing or unparseable → emit `status: invalid` with the reason in `errors[]` and exit `1` (fail-closed). No external JSON-Schema validation runs — `handoff-manifest.schema.yaml` is the reference structure, not an executed step.
2. Evaluate all 13 rules (FLOW-030..037, HDF-010/020/021/030/040) against the loaded mapping, regardless of `--caller`. Scoping is data-driven (FLOW-037 by `handoff.type`; HDF-021 only when `frontend_package` present; HDF-040 only when `frontend_artifacts` present). HDF-020/021 read each pinned file under `--specs-dir` and compare sha256.
3. Each blocking failure appends a rule-id-prefixed string to `errors[]` (e.g. `"FLOW-030: …"`). `change_summary.dev_impact: stop_domain_task_contracts` sets `halt_signal: true` (HDF-030) — flow control for the caller, not an error.
4. Print the envelope as one JSON object; exit `0` when `status: valid` (empty `errors`), else `1`.

## Envelope consumption rules

The caller MUST:
- Halt and escalate to human when `status: invalid` (exit code `1`)
- Halt affected domains when `halt_signal: true` (HDF-030 — `change_summary.dev_impact = stop_domain_task_contracts`)
- Proceed normally when `status: valid` and `halt_signal: false`
- Act on `status` and `halt_signal` for flow control; `errors[]` are rule-id-prefixed strings (e.g. `"FLOW-030: …"`) for diagnostics/surfacing, not for branching logic

## Envelope shape

`validate.py` emits this flat JSON object (one line):

```json
{
  "status": "valid | invalid",
  "errors": ["FLOW-030: …", "HDF-020: sha256 mismatch for …"],
  "warnings": [],
  "halt_signal": true,
  "validated_by": "u-handoff-validator",
  "caller": "u-spec-orchestrator | u-be-orchestrator-core | u-fe-orchestrator-core"
}
```

`errors[]` are rule-id-prefixed strings (not structured objects). This shape conforms to `handoff-validation-envelope.schema.yaml`. The SDD→Dev gate (`check_handoff_manifest_approved.py`) consumes `status` (must be `valid`) and surfaces `errors[]`; orchestrators additionally honor `halt_signal`.

## Versioning

When adding or changing a rule:
1. Change `validate.py` first — it is the executable source of truth (the SDD gate runs it).
2. Update `rules.yaml` and the rule catalog table in this SKILL.md to match.
3. Add a fixture pair (valid + invalid) under `tests/fixtures/`.
4. Extend the validator test layer (`tests/test_layer5_flows.py` and/or `tests/test_layer_hard_handoff_generation.py`) to cover the new rule.

New rule IDs: use `HDF-NNN` (handoff-specific) for rules introduced after the extraction. FLOW-NNN IDs are preserved for backward compatibility with existing tests.
