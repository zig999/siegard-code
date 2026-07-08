---
name: phase-review-rules
description: Exit criteria checkers and worker routing table for the review (QA) phase. Consumed by orchestrator-review.md to dispatch QA workers via select_worker.py and evaluate phase transition gates (check_all_qa_verdicts_approved, check_no_open_critical_findings, check_documentation_verified). Includes read_qa_verdict.py helper for verdict extraction. Not user-invocable — orchestrators call scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# phase-review-rules

Phase rules skill for the `review` (QA) phase.
Provides exit criteria checkers and worker routing table consumed by `orchestrator-review.md`.

## Contract

The orchestrator calls this skill's scripts directly. No inter-skill communication envelope needed.
Every script returns a JSON object to stdout and exits 0 on success or 1 on error.

---

## Phase identity

| Field | Value |
|-------|-------|
| `phase_name` | `review` |
| `order` | `3` |
| `required` | `true` |
| `worker_default` | `u-be-qa` |

---

## Worker routing table

Maps `task.type` + `stack` to worker sub-agent.
Stack is resolved by `orchestrator-review` from the dev-phase handoff context.
`architecture-review` and `security-review` are stack-independent.

| task.type | stack | worker subagent_type |
|-----------|-------|----------------------|
| `qa` | `be` | `u-be-qa` |
| `qa` | `fe` | `u-fe-qa` |
| `qa` | `fullstack` | `u-be-qa` |
| `architecture-review` | any | `u-architecture-reviewer` |
| `security-review` | any | `u-security-reviewer` |
| `*` (default) | any | `u-be-qa` |

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
{"worker": "u-be-qa", "task_type": "qa", "stack": "be", "phase": "review"}
```

### Error (exit 1, stderr)

```json
{"status": "error", "reason": "internal_error", "detail": "<message>"}
```

---

## Exit criteria

All three criteria must be met before the review phase can transition.

| Criterion | Script | Description |
|-----------|--------|-------------|
| `all_qa_verdicts_approved` | `scripts/check_all_qa_verdicts_approved.py` | Every QA verdict has `verdict: approved` |
| `no_open_critical_findings` | `scripts/check_no_open_critical_findings.py` | No verdict artifact contains `severity: critical` |
| `documentation_verified` | `scripts/check_documentation_verified.py` | At least one artifact has `documentation_verified: true`; none has `documentation_verified: false` |

See `exit-criteria.json` for the machine-readable declaration.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCH_PROJECT_DIR` | `.` | Project root — used to resolve QA verdict artifact paths |

---

## scripts/check_all_qa_verdicts_approved.py

Criterion: every QA verdict artifact from the **latest revision** of each completed
review-phase target contains `verdict: approved`.
Not met if no verdict artifacts are found or any latest-revision artifact has
`verdict: rejected`.

Superseded revisions (fix F7): a re-reviewed target produces `review_<base>` then
`review_<base>_r1` (dev revision appends `_r{n}`). Only the highest revision per base
target gates; earlier revisions — whose delivery was replaced by `return_to_dev` — are
listed under `evidence.superseded` and do not block. This removes the spurious E08 where
an old rejected verdict blocked handoff after the revision was approved.

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
    "not_approved": [],
    "superseded": ["review_dev_tc_001"]
  }
}
```

Accepted verdict values: `approved` (case-insensitive).

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

---

## scripts/classify_qa_mode.py

Classifier consumed by `orchestrator-review.md` Step 3 (task creation). Maps a review task to a `qa_mode` (`micro` | `standard` | `full`) and a `concurrency_hint` (5 | 3 | 2). The mode controls Phase 1/2/3 scope inside the QA worker, dispatch concurrency in Step 4.1, and eligibility for the auto-approval gate in Step 5.0.

### Decision tree (highest precedence first)

1. `full` if `has_nfr` OR `touches_security` OR `touches_public_api`
2. `micro` if `workflow_type == improve` AND `dev_impact == narrow` AND `changed_files_count <= 2` AND `tc_type ∈ {Bugfix, Refactoring}`
3. `standard` otherwise

`has_nfr` is detected by a non-commented `nfr_results:` field in the delivery file. `touches_security` and `touches_public_api` scan `files_created` ∪ `files_modified` for substring patterns (auth/token/security/credential/permission etc. for security; controller/route/openapi etc. for public API).

### Usage

```bash
python3 .claude/skills/phase-review-rules/scripts/classify_qa_mode.py \
  --workflow-type improve|standard|reverse-spec|unknown \
  --dev-impact narrow|moderate|wide|unknown \
  [--changed-files-count <int>] \
  [--tc-type Bugfix|Refactoring|Enhancement|NewFeature|unknown] \
  --delivery-path <rel path> \
  [--project-dir <abs path>]
```

### Output (exit 0)

```json
{
  "qa_mode": "micro",
  "concurrency_hint": 5,
  "rationale": "micro: improve flow, narrow impact, 1 files, type=Bugfix",
  "signals": {
    "workflow_type": "improve",
    "dev_impact": "narrow",
    "tc_type": "Bugfix",
    "changed_files_count": 1,
    "has_nfr": false,
    "touches_security": false,
    "touches_public_api": false,
    "matched_security_paths": [],
    "matched_public_api_paths": []
  }
}
```

---

## scripts/check_micro_unanimous_clean.py

Auto-approval gate evaluated by `orchestrator-review.md` Step 5.0 before the manual E99 escalation. Returns `qualifies: true` only when the strict conjunction holds:

| Rule | Source |
|---|---|
| R1 | At least one completed review task exists |
| R2 | Every completed review task has `qa_mode == "micro"` |
| R3 | Every QA verdict reads `verdict: approved` |
| R4 | No verdict contains a finding with severity ∈ {medium, high, critical} |

When qualified, the orchestrator emits `E18_auto_approval_granted` (info) followed by a synthesized `human_response` with `action: approve, auto_approved: true`.

### Usage

```bash
python3 .claude/skills/phase-review-rules/scripts/check_micro_unanimous_clean.py \
  --project-dir <abs path> \
  --tasks '<JSON: [{"task_id":"...","qa_mode":"micro","verdict_path":"..."}, ...]>'
```

### Output (exit 0)

```json
{
  "qualifies": true,
  "evidence": {
    "total_review_tasks": 2,
    "all_micro": true,
    "all_approved": true,
    "max_finding_severity": "low",
    "non_micro_tasks": [],
    "non_approved_tasks": [],
    "tasks_with_blocking_findings": []
  },
  "rationale": "qualifies: 2 task(s) all micro, all approved, max severity=low"
}
```

---

## scripts/run_suite.py · scripts/parse_test_output.py · scripts/attribute_failures.py · scripts/check_suite_freshness.py

Shared suite-run protocol consumed by `orchestrator-review.md` Step 3.5 (default-on; disable with `SHARED_SUITE_RUN=0`). Together they execute build + tests once per round, parse vitest/jest JSON, and produce per-TC attribution slices that QA workers consume in shared mode (`Suite run mode: shared` in the activation prompt). See Step 3.5 of orchestrator-review.md for the call sequence and §"Embedded skills" / Phase 1 §1.S of the QA worker agents (`u-be-qa.md`, `u-fe-qa.md`) for the worker contract.

---

## scripts/read_qa_verdict.py

Helper: reads and validates the `verdict` field from one or more QA report artifact files.
Used by the orchestrator when it needs to inspect verdict values without running a full criterion check.
Files with missing or unrecognised verdicts are reported as `unknown` (not silently dropped).

### Usage

```bash
python3 .claude/skills/phase-review-rules/scripts/read_qa_verdict.py \
  [--project-dir <dir>] <artifact_path> [<artifact_path> ...]
```

### Output (exit 0)

```json
[
  {"artifact": "path/to/qa-report.md", "verdict": "approved"},
  {"artifact": "path/to/other.md", "verdict": "unknown"}
]
```

Verdict values: `approved` | `rejected` | `file_not_found` | `unknown`

### Error (exit 1, stderr)

```json
{"status": "error", "reason": "internal_error", "detail": "<message>"}
```
