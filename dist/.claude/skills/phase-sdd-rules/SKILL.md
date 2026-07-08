---
name: phase-sdd-rules
description: Exit criteria checkers and worker routing table for the sdd (Specification-Driven Development) phase. Consumed by orchestrator-sdd.md to dispatch spec workers via select_worker.py and evaluate phase transition gates (check_handoff_manifest_approved, check_all_domains_validated, check_error_codes_synced). Includes check_structural_diff.py to determine if spec changes require domain worker dispatch during improve flows. Not user-invocable — orchestrators call scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# phase-sdd-rules

Phase rules skill for the `sdd` (Specification-Driven Development) phase.
Provides exit criteria checkers and worker routing table consumed by `orchestrator-sdd.md`.

## Contract

The orchestrator calls this skill's scripts directly. No inter-skill communication envelope needed.
Every script returns a JSON object to stdout and exits 0 on success or 1 on error.

---

## Phase identity

| Field | Value |
|-------|-------|
| `phase_name` | `sdd` |
| `order` | `1` |
| `required` | `true` |
| `worker_default` | `u-spec-writer` |

---

## Concurrency ceiling (RESOURCE_LIMITS)

The orchestrator MUST enforce these per-batch ceilings before each dispatch in Step 5.1:

| `effective_mode` | Max concurrent workers per batch |
|------------------|----------------------------------|
| `standard` | `2` |
| `targeted` | `1` |

The ceiling is enforced as a hard cap — the orchestrator may dispatch FEWER than the cap (e.g., if only one task is ready) but MUST NOT exceed it. Violation is a protocol violation per RESOURCE_LIMITS.

---

## Worker routing table

Maps `task.type` to worker sub-agent. Consumed by the orchestrator dispatcher.

| task.type | worker subagent_type |
|-----------|----------------------|
| `spec-triage` | `u-spec-triage` |
| `spec-writer` | `u-spec-writer` |
| `spec-reviewer` | `u-spec-reviewer` |
| `spec-back` | `u-spec-back` |
| `spec-front` | `u-spec-front` |
| `spec-validator` | `u-spec-validator` |
| `spec-compliance` | `u-spec-compliance` |
| `*` (default) | `u-spec-writer` |

---

## scripts/select_worker.py

Returns the worker sub-agent name for a given task type.

### Usage

```bash
python3 .claude/skills/phase-sdd-rules/scripts/select_worker.py \
  --task-type <type>
```

### Output (exit 0)

```json
{"worker": "u-spec-writer", "task_type": "spec-writer", "phase": "sdd"}
```

### Error (exit 1, stderr)

```json
{"status": "error", "reason": "internal_error", "detail": "<message>"}
```

---

## Exit criteria

All three criteria must be met before the sdd phase can transition.
Evaluated by `orchestrator-sdd.md` at the end of each cycle.

| Criterion | Script | Description |
|-----------|--------|-------------|
| `handoff_manifest_approved` | `scripts/check_handoff_manifest_approved.py` | `handoff-manifest.yaml` exists and `Status: approved` |
| `all_domains_validated` | `scripts/check_all_domains_validated.py` | No `INVALID` status in `_validation/` (scoped to the change's domains on `/u-improve` via `--workflow-id`) |
| `error_codes_synced` | `scripts/check_error_codes_synced.py` | All `error.code` values in in-scope specs are in `error-codes.md` (scoped to touched domains on `/u-improve` via `--workflow-id`) |

See `exit-criteria.json` for the machine-readable declaration.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCH_PROJECT_DIR` | `.` | Project root |
| `SPECS_DIR` | `specs` | Specs directory, relative to `ORCH_PROJECT_DIR` |

---

## scripts/check_handoff_manifest_approved.py

Criterion: `handoff-manifest.yaml` exists in `SPECS_DIR` and contains `Status: approved`.

```bash
python3 .claude/skills/phase-sdd-rules/scripts/check_handoff_manifest_approved.py
```

Output schema:
```json
{
  "criterion": "handoff_manifest_approved",
  "met": true,
  "evidence": {
    "file": "specs/handoff-manifest.yaml",
    "exists": true,
    "status_found": "approved"
  }
}
```

---

## scripts/check_all_domains_validated.py

Criterion: no `INVALID` status in any in-scope `.yaml` or `.md` file under `SPECS_DIR/_validation/`.

```bash
python3 .claude/skills/phase-sdd-rules/scripts/check_all_domains_validated.py [--workflow-id <wid>]
```

Scope (fix F1): with `--workflow-id`, an `/u-improve` gates only the domains the
change touched (`scope.py`). Untouched domains inherit their last verdict, so a
stale `INVALID` in an unrelated domain does not block the change — it is reported
under `out_of_scope_invalid` for audit. For u-spec / greenfield / un-derivable
scope the check stays global (every domain must be VALID). Without `--workflow-id`
it is global (prior behavior).

Output schema:
```json
{
  "criterion": "all_domains_validated",
  "met": true,
  "evidence": {
    "validation_dir": "specs/_validation",
    "exists": true,
    "total": 5,
    "passing": 5,
    "failing": [],
    "out_of_scope_invalid": [],
    "scoped": false,
    "scope_domains": null
  }
}
```

`met` is `false` if the `_validation/` directory does not exist or contains no in-scope files.

---

## scripts/scope.py

Derives the set of domains a change actually touches, so the gate, the handoff
scan, and the orchestrator dispatch can restrict work to them (fix F1). Reads
`triage.json`.

```bash
python3 .claude/skills/phase-sdd-rules/scripts/scope.py --workflow-id <wid>
# → {"scoped": true,  "domains": ["<affected>", ...]}   /u-improve
# → {"scoped": false, "domains": null}                  u-spec / greenfield / un-derivable
```

`scoped: false` (domains `null`) always means "no scoping — evaluate every
domain" (never "empty scope"), keeping greenfield and legacy triage on prior
behavior. Also exposes `domain_of_validation_file(filename)` used by the gate and
the handoff scan to map a `_validation/` artifact back to its domain.

---

## scripts/check_error_codes_synced.py

Criterion: every `error.code` / `code: Exxx` value found in an in-scope spec YAML/MD file is
registered in `SPECS_DIR/error-codes.md`. Trivially met if no error codes are defined in specs.

With `--workflow-id`, an `/u-improve` gates only the codes referenced by touched domains
(scope.py, fix F1) — an unregistered code living exclusively in untouched domains is reported
under `out_of_scope_missing` and does not block. Files outside `domains/<slug>/` are always
in scope. Without `--workflow-id` (or for u-spec / greenfield) the check is global.

```bash
python3 .claude/skills/phase-sdd-rules/scripts/check_error_codes_synced.py [--workflow-id <wid>]
```

Output schema:
```json
{
  "criterion": "error_codes_synced",
  "met": true,
  "evidence": {
    "error_codes_file": "specs/error-codes.md",
    "error_codes_file_exists": true,
    "spec_codes_found": ["E001", "E002"],
    "registered_codes_count": 10,
    "missing_codes": [],
    "out_of_scope_missing": [],
    "files_scanned": ["domain-auth.yaml", "domain-billing.yaml"],
    "scoped": false,
    "scope_domains": null
  }
}
```

---

## scripts/identify_invalid_domains.py

Utility (repair loop Step R2): lists domains whose validation report in
`{SPECS_DIR}/_validation/` is INVALID and derives each one's defect origin from
the machine-readable `{domain}-validation-result.yaml` (`blocking_issues[].responsible`).
Feeds the SM's stage-granular repair (S16): origin `"back"` (all blocking issues
belong to `u-spec-back`) routes a reduced `["spec-back", "spec-validator"]` repair
pipeline; any other origin (mixed, front, writer, missing or unparseable companion)
returns `null` and keeps the full pipeline — mis-attribution degrades to redundant
work, never to under-repair.

### Usage

```bash
ORCH_PROJECT_DIR=<path> SPECS_DIR=<specs> python3 .claude/skills/phase-sdd-rules/scripts/identify_invalid_domains.py [--workflow-id <wid>]
```

With `--workflow-id`, an `/u-improve` restricts the repair-target set to the touched domains
(scope.py, fix F1): a stale INVALID report in an untouched domain goes to `out_of_scope_invalid`
and never enters `invalid_domains` — the repair loop must not dispatch workers for domains this
workflow did not touch. Without `--workflow-id` (or for u-spec / greenfield) the scan is global.

### Output (exit 0)

```json
{
  "invalid_domains": ["chat", "ingestion"],
  "defect_origins": {"chat": "back", "ingestion": null},
  "out_of_scope_invalid": [],
  "scoped": false
}
```

## scripts/check_structural_diff.py

Utility (not an exit criterion): determines whether a spec change requires dispatching a domain
worker. Used by `orchestrator-sdd.md` during improve flows to decide if structural sections were
modified (endpoints, schemas, auth_rules, data_models, etc.) and a domain worker must run.

Safe fallback: if `improve-scope.json` is missing or the spec is not listed in scope, returns
`domain_worker_required: true` to avoid skipping required work.

### Usage

```bash
ORCH_PROJECT_DIR=<path> python3 .claude/skills/phase-sdd-rules/scripts/check_structural_diff.py \
  --workflow-id <wid> \
  --spec-path <relative-path-to-spec>
```

### Output (exit 0)

```json
{
  "domain_worker_required": true,
  "changed_sections": ["endpoints", "schemas"],
  "structural_sections_found": ["endpoints", "schemas"]
}
```

Structural sections that trigger `domain_worker_required: true`:
`endpoints`, `schemas`, `error_codes`, `component_props`, `state_contracts`,
`data_models`, `auth_rules`, `event_types`, `api_contracts`

---

## scripts/generate_handoff_manifest.py

Utility (not an exit criterion): deterministically produces `SPECS_DIR/handoff-manifest.yaml`
from the validated specs on disk plus `triage.json`. Closes the gap where no pipeline worker
produced the manifest the SDD exit gate requires (the phase previously dead-ended at E08).

Invoked by `orchestrator-sdd.md` in Step 6 **after** `check_all_domains_validated.py` (or
`check_all_improve_reviewers_completed.py` in targeted mode) and `check_error_codes_synced.py`
pass, and **before** `check_handoff_manifest_approved.py`. Deterministic (no LLM): sha256 must be
exact and the output must round-trip through `lib/minimal_yaml.py`, which `validate.py` uses.

### Usage

```bash
ORCH_PROJECT_DIR=<path> SPECS_DIR=<rel> \
  python3 .claude/skills/phase-sdd-rules/scripts/generate_handoff_manifest.py \
  --workflow-id <wid>
```

### Behavior

- Enumerates domains via `glob domains/*/openapi.yaml`; builds `domains[]`, `backend_package[]`
  (openapi + back-spec per domain are required by FLOW-037; `error-codes` / `conventions` added
  when present), and — only if `front/front.md` exists — `frontend_artifacts` + `frontend_package[]`.
  Omitting the frontend blocks lets the Dev orchestrator infer `stack=be` (back-only handoff).
- `handoff.delivered_by` is the const `u-spec-orchestrator` (required by FLOW-030); `handoff.type`
  is derived from triage (`new_domain` / `major_evolution` / `fast_track`). `change_summary` is
  emitted only for evolution handoffs.
- sha256 of every package file is computed at generation time; paths are stored relative to
  `ORCH_PROJECT_DIR` so `validate.py` (`--specs-dir = ORCH_PROJECT_DIR`) resolves them.

### Output (exit 0 when status=ok, exit 1 when status=blocked)

```json
{"status": "ok", "check": "handoff_manifest_generated",
 "manifest_path": "specs/handoff-manifest.yaml", "manifest_id": "HANDOFF-20260601-120000",
 "domains": ["auth"], "stack_implied": "be", "reason": "triage_loaded"}
```

Fail-closed: no domains, a missing required backend artifact, a `handoff_allowed: false` in
`_validation/*-validation-result.yaml`, a `block_handoff` / `non_compliant` in
`_validation/*-compliance.yaml`, or a triage stack/front mismatch (`triage.stack` ∈ {`fullstack`,
`fe`} but no front artifacts on disk — `stack_mismatch_front_expected_but_missing`, fix P0-1) yields
`status: blocked` **without** writing the manifest. The orchestrator treats a blocked generation as
criterion-not-met (Validation Repair Loop / E08).
