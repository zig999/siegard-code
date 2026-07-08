---
name: phase-test-rules
description: Exit criteria checkers and worker routing table for the test (automated testing) phase. Consumed by orchestrator-test.md to dispatch test workers via select_worker.py and evaluate phase transition gates (check_all_test_tasks_terminal, check_all_tests_passed, check_no_critical_failures). DLQ tasks block transition. Not user-invocable — orchestrators call scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# phase-test-rules

Phase rules skill for the `test` (automated testing) phase.
Provides exit criteria checkers and worker routing table consumed by `orchestrator-test.md`.

## Contract

The orchestrator calls this skill's scripts directly. No inter-skill communication envelope needed.
Every script returns a JSON object to stdout and exits 0 on success or 1 on error.

---

## Phase identity

| Field | Value |
|-------|-------|
| `phase_name` | `test` |
| `order` | `4` |
| `required` | `true` |
| `worker_default` | `u-test-runner` |

---

## Worker routing table

Maps `task.type` + `stack` to worker sub-agent.
All stacks route to the same worker — `u-test-runner` is stack-agnostic.

| task.type | stack | worker subagent_type |
|-----------|-------|----------------------|
| `test-run` | `be` | `u-test-runner` |
| `test-run` | `fe` | `u-test-runner` |
| `test-run` | `fullstack` | `u-test-runner` |
| `*` (default) | any | `u-test-runner` |

---

## scripts/select_worker.py

Returns the worker sub-agent name for a given task type and optional stack.

### Usage

```bash
python3 .claude/skills/phase-test-rules/scripts/select_worker.py \
  --task-type <type> \
  [--stack <be|fe|fullstack>]
```

### Output (exit 0)

```json
{"worker": "u-test-runner", "task_type": "test-run", "stack": "be", "phase": "test"}
```

### Error (exit 1, stderr)

```json
{"status": "error", "reason": "internal_error", "detail": "<message>"}
```

---

## Exit criteria

All three criteria must be met before the test phase can transition. DLQ tasks block transition —
a failed task is not a passing test run.

| Criterion | Script | Description |
|-----------|--------|-------------|
| `all_test_tasks_terminal` | `scripts/check_all_test_tasks_terminal.py` | All test tasks in `completed`; zero DLQ tasks |
| `all_tests_passed` | `scripts/check_all_tests_passed.py` | Every test report artifact has `result: passed` |
| `no_critical_failures` | `scripts/check_no_critical_failures.py` | No test report artifact contains `severity: critical` failures |

See `exit-criteria.json` for the machine-readable declaration.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCH_PROJECT_DIR` | `.` | Project root — used to resolve test report artifact paths |

---

## scripts/check_all_test_tasks_terminal.py

Criterion: every task in the `test` phase has status `completed`. DLQ tasks block the criterion.
Not met if there are no test tasks (phase hasn't started).

```bash
python3 .claude/skills/phase-test-rules/scripts/check_all_test_tasks_terminal.py
```

Output schema:
```json
{
  "criterion": "all_test_tasks_terminal",
  "met": true,
  "evidence": {
    "total": 5,
    "terminal": 5,
    "non_terminal": [],
    "dlq": [],
    "dlq_blocks_criterion": false
  }
}
```

---

## scripts/check_all_tests_passed.py

Criterion: every test report artifact from completed test-phase tasks contains `result: passed`.
Not met if no test report artifacts are found.
Artifact paths are resolved relative to `ORCH_PROJECT_DIR`.

```bash
python3 .claude/skills/phase-test-rules/scripts/check_all_tests_passed.py
```

Output schema:
```json
{
  "criterion": "all_tests_passed",
  "met": true,
  "evidence": {
    "total": 5,
    "passed": 5,
    "failed": []
  }
}
```

Accepted result values: `passed` (case-insensitive).
Any other value (`failed`, `error`, `skipped`) is treated as not passed.

---

## scripts/check_no_critical_failures.py

Criterion: no test report artifact contains a failure entry with `severity: critical`.
Artifact paths are resolved relative to `ORCH_PROJECT_DIR`.

```bash
python3 .claude/skills/phase-test-rules/scripts/check_no_critical_failures.py
```

Output schema:
```json
{
  "criterion": "no_critical_failures",
  "met": true,
  "evidence": {
    "total": 5,
    "clean": 5,
    "with_critical": []
  }
}
```
