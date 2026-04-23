# phase-review-rules

Phase rules skill for the `review` (QA) phase.
Provides exit criteria checkers and worker routing table consumed by `orchestrator-review.md`.

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
| `phase_name` | `review` |
| `order` | `3` |
| `required` | `true` |
| `worker_default` | `u-be-qa-docs` |

---

## Worker routing table

Maps `task.type` + `stack` to worker sub-agent.
Stack is resolved by `orchestrator-review` from the dev-phase handoff context.

| task.type | stack | worker subagent_type |
|-----------|-------|----------------------|
| `qa` | `be` | `u-be-qa-docs` |
| `qa` | `fe` | `u-fe-qa-docs` |
| `qa` | `fullstack` | `u-be-qa-docs` |
| `architecture-review` | any | `u-architecture-reviewer` |
| `security-review` | any | `u-security-reviewer` |
| `*` (default) | any | `u-be-qa-docs` |

---

## scripts/select_worker.py

Returns the worker sub-agent name for a given task type and optional stack.

### Usage

```bash
python3 .claude/skills/phase-review-rules/scripts/select_worker.py \
  --task-type <type> \
  [--stack <be|fe|fullstack>]
```

### Output (exit 0)

```json
{"worker": "u-be-qa-docs", "task_type": "qa", "stack": "be", "phase": "review"}
```

### Error (exit 1)

```json
{"status": "error", "reason": "internal_error", "detail": "<message>"}
```

---

## Exit criteria

Three criteria must all be met before the review phase can transition.

| Criterion | Script | Description |
|-----------|--------|-------------|
| `all_qa_verdicts_approved` | `scripts/check_all_qa_verdicts_approved.py` | Every QA verdict has `verdict: approved` or `verdict: approved_with_reservations` |
| `no_open_critical_findings` | `scripts/check_no_open_critical_findings.py` | No verdict artifact contains `severity: critical` |
| `documentation_verified` | `scripts/check_documentation_verified.py` | At least one artifact has `documentation_verified: true`; none has `documentation_verified: false` |

See `exit-criteria.json` for the machine-readable declaration.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCH_PROJECT_DIR` | `.` | Project root — used to resolve QA verdict artifact paths |

---

## scripts/check_all_qa_verdicts_approved.py

Criterion: every QA verdict artifact from completed review-phase tasks contains
`verdict: approved` or `verdict: approved_with_reservations`.
Not met if no verdict artifacts are found.

```bash
python3 .claude/skills/phase-review-rules/scripts/check_all_qa_verdicts_approved.py
```

Output schema:
```json
{
  "criterion": "all_qa_verdicts_approved",
  "met": true,
  "evidence": {
    "total": 4,
    "approved": 4,
    "not_approved": []
  }
}
```

Accepted verdict values: `approved`, `approved_with_reservations` (case-insensitive).

---

## scripts/check_no_open_critical_findings.py

Criterion: no QA verdict artifact contains a finding entry with `severity: critical`.

```bash
python3 .claude/skills/phase-review-rules/scripts/check_no_open_critical_findings.py
```

Output schema:
```json
{
  "criterion": "no_open_critical_findings",
  "met": true,
  "evidence": {
    "total": 4,
    "clean": 4,
    "with_critical": []
  }
}
```

---

## scripts/check_documentation_verified.py

Criterion: at least one review-phase QA artifact contains `documentation_verified: true`,
and none contains `documentation_verified: false`.
Not met if no QA artifacts exist or if none has the `documentation_verified:` field.

```bash
python3 .claude/skills/phase-review-rules/scripts/check_documentation_verified.py
```

Output schema:
```json
{
  "criterion": "documentation_verified",
  "met": true,
  "evidence": {
    "total": 4,
    "verified_true": 2,
    "verified_false": [],
    "field_absent": 2
  }
}
```
