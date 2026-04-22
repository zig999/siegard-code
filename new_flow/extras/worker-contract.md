# Worker Contract

Every worker sub-agent must comply with this contract. Violations result in `task_failed` synthesized by the `on_subagent_stop` hook.

---

## 1. What a Worker Receives

Workers are spawned via `Agent()`. The prompt contains:

```
CONTEXT:
  task_id:    dev_tc_003
  attempt:    1
  worker_id:  worker-dev-be-003

ENVIRONMENT (set these as shell env vars before calling emit.py):
  ORCH_TASK_ID=dev_tc_003
  ORCH_ATTEMPT=1
  ORCH_WORKER_ID=worker-dev-be-003
  ORCH_PROJECT_DIR=/path/to/project
  SPECS_DIR=sessions/2026-04-21/specs

TASK SPEC:
  <task specification>

INSTRUCTIONS:
  <phase-specific instructions>
```

Workers do **not** inherit shell env vars from the orchestrator. The prompt is the only communication channel.

---

## 2. Worker Lifecycle

```
Receive prompt
    │
    ▼
Set env vars
    export ORCH_TASK_ID="..." ORCH_ATTEMPT=1 ORCH_WORKER_ID="..."
    export ORCH_PROJECT_DIR="..." SPECS_DIR="..."
    │
    ▼
Report progress (optional, any number of times)
    python3 .claude/skills/orch-report/scripts/emit.py \
      --kind progress \
      --task-id $ORCH_TASK_ID \
      --data '{"phase": "<phase>", "note": "Writing auth service..."}'
    │
    ▼
Do the work
    (implement, write files, run tests, etc.)
    │
    ├─ success ──► emit task_completed
    └─ failure ──► emit task_failed
```

---

## 3. Emission Contract

All events are emitted via `emit.py` from the `orch-report` skill.

### Load skill

Workers must load `orch-report` to access `emit.py`:
```
skills:
  - orch-report
```

### Emit progress

```bash
python3 .claude/skills/orch-report/scripts/emit.py \
  --kind progress \
  --task-id "$ORCH_TASK_ID" \
  --attempt "$ORCH_ATTEMPT" \
  --data '{"phase": "<phase>", "note": "Running tests — 8/12 passing"}'
```

### Emit success

```bash
python3 .claude/skills/orch-report/scripts/emit.py \
  --kind completed \
  --task-id "$ORCH_TASK_ID" \
  --attempt "$ORCH_ATTEMPT" \
  --data '{
    "phase":     "dev",
    "artifacts": ["src/auth/jwt.py", "tests/test_jwt.py"],
    "summary":   "Implemented JWT signing with RS256; 12 tests passing"
  }'
```

### Emit failure

```bash
python3 .claude/skills/orch-report/scripts/emit.py \
  --kind failed \
  --task-id "$ORCH_TASK_ID" \
  --attempt "$ORCH_ATTEMPT" \
  --data '{
    "phase":     "dev",
    "reason":    "spec_unclear: RS256 key path not specified in task contract",
    "retryable": false
  }'
```

### Guard-rail (non-negotiable)

`emit.py` accepts **only** `progress`, `completed`, `failed`. Any other kind is rejected with exit code 1. Workers cannot emit orchestrator-type events (`task_claimed`, `task_dlq`, `escalation`, etc.).

---

## 4. Terminal Event Rules

| Rule | Detail |
|------|--------|
| Exactly one terminal event | Each invocation emits exactly one `task_completed` or `task_failed` |
| Emit before exit | Terminal event must be emitted before the worker stops |
| No silent exit | If worker exits without terminal event, `on_subagent_stop` synthesizes `task_failed(retryable=true)` |
| Artifacts = paths | `artifacts` contains file paths, never inline content |

---

## 5. `retryable` Flag

| Value | Use when |
|-------|---------|
| `true` | Transient error: rate limit, timeout, tool failure, context overflow |
| `false` | Permanent error: invalid spec, permission denied, missing dependency, conflicting requirements |

Setting `retryable=false` sends the task directly to DLQ without backoff. Use it only when retrying would produce the same outcome.

---

## 6. Artifact Schemas by Worker Type

### Impl workers (`u-be-developer`, `u-fe-developer`)

Produce: `SESSION_DIR/delivery/<task_id>-delivery.md`

Required frontmatter:
```yaml
task_id: dev_tc_001
qa_ready: true
prohibition_violations: []
```

Optional:
```yaml
summary: "One-line description"
spec_divergences: []
```

Body: free-form Markdown (`## Changes`, `## Tests Written`, `## Notes for QA`).

---

### Planning workers (`u-be-planner`, `u-fe-planner`)

Produce: `SESSION_DIR/backlog/backlog.json`

```json
[
  {
    "task_id": "dev_tc_001",
    "spec":    "sessions/2026-04-21/backlog/tc-001.md",
    "deps":    [],
    "tier":    "critical",
    "type":    "impl",
    "stack":   "be",
    "title":   "POST /auth/login with JWT issuance"
  }
]
```

`task_id` pattern: `dev_tc_NNN` (zero-padded).
`tier` values: `critical` | `standard`.
`deps`: list of `task_id`s that must complete before this task can start; `[]` if none.

---

### QA workers (`u-be-qa-docs`, `u-fe-qa-docs`)

Produce: `SPECS_DIR/qa/<task_id>-qa.md`

Required frontmatter:
```yaml
task_id: dev_tc_001
verdict: approved
documentation_verified: true
```

`verdict` values: `approved` | `approved_with_reservations` | `rejected`

Optional findings:
```yaml
findings:
  - id: QA-001
    severity: critical | high | medium | low
    description: "Clear description of the issue"
    file: src/auth/jwt.py
    suggestion: "Recommended fix"
```

`critical` findings block exit criterion `no_open_critical_findings`.

---

## 7. Environment Variable Reference

| Variable | Required | Set by | Description |
|----------|----------|--------|------------|
| `ORCH_TASK_ID` | Yes | Worker (from prompt) | Task identifier |
| `ORCH_ATTEMPT` | Yes | Worker (from prompt) | Attempt number (1-based) |
| `ORCH_WORKER_ID` | Yes | Worker (from prompt) | Worker identity — used as `agent` in events |
| `ORCH_PROJECT_DIR` | Yes | Worker (from prompt) | Absolute path to project root |
| `SPECS_DIR` | Phase-specific | Worker (from prompt) | Relative path to specs directory |
