# phase-sdd-rules

Phase rules skill for the `sdd` (Specification-Driven Development) phase.
Provides exit criteria checkers and worker routing table consumed by `orchestrator-sdd.md`.

## Contract

The orchestrator calls this skill's scripts directly. No inter-skill communication envelope needed.
Every script returns a JSON object to stdout and exits 0 on success or 1 on error.

---

## allowed-tools

```
Bash(python3 *)
Read
Glob
Grep
```

---

## Phase identity

| Field | Value |
|-------|-------|
| `phase_name` | `sdd` |
| `order` | `1` |
| `required` | `true` |
| `worker_default` | `u-spec-writer` |

---

## Worker routing table

Maps `task.type` to worker sub-agent. Consumed by the orchestrator dispatcher.

| task.type | worker subagent_type |
|-----------|----------------------|
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

### Error (exit 1)

```json
{"status": "error", "reason": "internal_error", "detail": "<message>"}
```

---

## Exit criteria

Three criteria must all be met before the sdd phase can transition.
Evaluated by `orchestrator-sdd.md` at the end of each cycle.

| Criterion | Script | Description |
|-----------|--------|-------------|
| `handoff_manifest_approved` | `scripts/check_handoff_manifest_approved.py` | `handoff-manifest.yaml` exists and `Status: approved` |
| `all_domains_validated` | `scripts/check_all_domains_validated.py` | No `INVALID` status in `_validation/` |
| `error_codes_synced` | `scripts/check_error_codes_synced.py` | All `error.code` values in specs are in `error-codes.md` |

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

Criterion: no `INVALID` status in any `.yaml` or `.md` file under `SPECS_DIR/_validation/`.

```bash
python3 .claude/skills/phase-sdd-rules/scripts/check_all_domains_validated.py
```

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
    "failing": []
  }
}
```

`met` is `false` if the `_validation/` directory does not exist or contains no files.

---

## scripts/check_error_codes_synced.py

Criterion: every `error.code` / `code: Exxx` value found in spec YAML files is registered in
`SPECS_DIR/error-codes.md`. Trivially met if no error codes are defined in specs.

```bash
python3 .claude/skills/phase-sdd-rules/scripts/check_error_codes_synced.py
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
    "files_scanned": ["domain-auth.yaml", "domain-billing.yaml"]
  }
}
```
