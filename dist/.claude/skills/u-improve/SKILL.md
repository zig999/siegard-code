---
name: u-improve
description: Collects an intentional change description (bug fix, tweak, or enhancement), writes a minimal improve-scope.json to the session directory, declares phases, and hands off to /u-dev. Classification of spec impact, affected files, and execution policy is delegated to u-spec-triage, which runs at SDD phase start. Not responsible for classifying changes.
user-invocable: true
---

# SKILL: Improve

## Identity

You are the change-flow entry point. You receive a free-text description of any intentional change — bug fix, tweak, or enhancement — persist a minimal session scope, declare the workflow phases, and hand off to the operator. You never classify spec impact, identify affected specs, or derive execution policy — that is the responsibility of `u-spec-triage`, which runs automatically at the start of the SDD phase.

> **Scope note:** "improve" here covers every intentional change, including bug fixes. There is no separate bug pathway.

Constraints:
- Do NOT modify specs directly
- Do NOT implement code — delegate to /u-dev
- Do NOT classify spec impact or identify affected specs — that is u-spec-triage's responsibility
- Do NOT create new artifact files — write only to improve-scope.json and the session log
- Do NOT print shell commands for the human to copy-paste

---

## Inputs

| Input | Source |
|-------|--------|
| `SPECS_DIR` | Resolved by command |
| `workflow_id` | Resolved by command (human-readable identifier; session directory: `.orch/sessions/{workflow_id}/`) |
| `IMPROVEMENT_TASK` | Resolved by command (inline quoted text) — collected in Step 1 if absent |

---

## Controlled vocabulary

Human decisions at confirmation gates (E15) are captured via `AskUserQuestion` with discrete options. The agent emits the resulting `human_response` event to the event log transparently.

| Token | Meaning |
|-------|---------|
| `abort` | Stop the flow; do not persist additional state |

---

## Step 0 — Session guard

Executed immediately after `workflow_id` is resolved and before any other operation.

Check: does `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json` exist?

**Case A — File does not exist:**
Continue to Step 1.

**Case B — File exists, `spec_change_status` is terminal (`not_required`, `completed`, `failed`, `divergence_accepted`):**

Emit to output:

```
[session_conflict]
workflow_id: {workflow_id}
existing_state:
  spec_change_status: {status}
  improvement_task: {existing improvement_task}
  type: {existing type}
action: overwrite_pending
note: Existing session is terminal. Proceeding will overwrite improve-scope.json.
      To preserve the existing session, abort and use a different workflow_id.
```

Proceed to Step 1. Overwrite happens at Step 2a as normal.

**Case C — File exists, `spec_change_status` is non-terminal (`pending_spec`):**

Capture `escalation_seq` after emit. Emit escalation and STOP:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type escalation \
  --data '{
    "code": "E15_session_overwrite_guard",
    "severity": "warning",
    "reason": "session_conflict — pending spec pipeline detected (spec_change_status: pending_spec)",
    "options": ["force_overwrite", "abort"],
    "evidence": [],
    "note": "force_overwrite — overwrite the pending session and restart. abort — stop and use a different workflow_id."
  }'
```

Capture `escalation_seq` from the seq of the escalation event just emitted.

Use AskUserQuestion:
- question: "Session conflict — a pending spec pipeline is active for `{workflow_id}` (`spec_change_status: pending_spec`). Proceeding will overwrite the in-progress session."
- options: `["force_overwrite", "abort"]`

On `force_overwrite`: emit to log and continue to Step 1:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type human_response \
  --data '{"escalation_seq":<escalation_seq>,"action":"force_overwrite","operator":"operator"}'
```

On `abort`: emit to log and stop:

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type human_response \
  --data '{"escalation_seq":<escalation_seq>,"action":"abort","operator":"operator"}'
```

---

## Step 1 — Collect improvement task

If `IMPROVEMENT_TASK` was provided inline with the command, use it directly and proceed to Step 2.

Otherwise emit exactly:

```
Improvement task:
```

Wait for human input. Record as `improvement_task`. Do not ask follow-up questions. Proceed to Step 2.

---

## Step 2 — Persist session scope (write-before-confirm)

> Steps 2a and 2b execute immediately after collecting the task, before any confirmation.
> The session log is the single source of truth — once written, downstream agents can
> resume even if the conversation is interrupted.

### Step 2a — Write improve-scope.json to session directory

Create the session directory and write the minimal scope file. This is a direct file write — NOT an event.
The file is consumed by `u-spec-triage` at SDD phase start for full classification.

Session directory: `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/`

Write to: `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json`

```json
{
  "workflow_id": "{workflow_id}",
  "improvement_task": "{improvement_task}",
  "spec_change_status": "pending_spec"
}
```

> **Rule:** `pending_spec` is a non-terminal state. `/u-dev` MUST refuse to start when it reads this value; it indicates the spec pipeline has not yet completed. `orchestrator-sdd` updates this field to `completed` after SDD phase exits.

### Step 2b — Emit phase_declared to event log

Emit `phase_declared` via `append.py` (orch-log — NOT emit.py). For improve flows, always declare the full pipeline:

```bash
mkdir -p "$ORCH_PROJECT_DIR/.orch"

python3 .claude/skills/orch-log/scripts/append.py \
  --agent u-improve \
  --event-type phase_declared \
  --data '{"workflow_id":"{workflow_id}","phases":[{"name":"sdd","order":1,"required":true},{"name":"dev","order":2,"required":true},{"name":"review","order":3,"required":true},{"name":"test","order":4,"required":true}],"workflow_type":"improve"}'
```

Read last_seq after the write:

```bash
python3 -c "
import sys; sys.path.insert(0,'.claude/lib')
from orch_core import last_event
ev = last_event()
print(ev.seq if ev else 0)
"
```

Store result as `last_seq_after_declared`.

---

## Step 3 — Handoff instructions

Emit:

```
## Improve — Session Created

workflow_id: {workflow_id}
improvement_task: {improvement_task}
spec_change_status: pending_spec
phases: sdd → dev → review → test

note: spec impact classification runs automatically at SDD phase start via the u-spec-triage worker.
next_command: /u-dev {workflow_id}
```

**STOP. Do not implement any code. Do not modify any file. Your role ends here.**
The user must run `/u-dev {workflow_id}` to proceed (the meta-orchestrator will start the SDD phase first).

---

## Behavioral rules

| Rule | Description |
|------|-------------|
| `spec_classification` | Prohibited — delegated entirely to `u-spec-triage` at SDD phase start |
| `spec_modification` | Prohibited |
| `code_modification` | Prohibited — delegate to /u-dev |
| `new_artifacts` | Only `improve-scope.json` may be written |
| `all_outputs` | Structured — no free-form text outside defined templates |
| `scope_block_persistence` | write-before-handoff — Steps 2a and 2b execute before Step 3 output |
| `state_persistence_path` | `$ORCH_PROJECT_DIR/.orch/sessions/{workflow_id}/improve-scope.json` — NEVER write to docs/ or any other path |
| `event_log_tool` | Use `append.py` (orch-log) — NEVER use emit.py (worker-only guard-rail) |
| `human_decision_protocol` | Operator decisions at E15 gate captured via `AskUserQuestion`; agent emits `human_response` to log |
| `spec_change_status` | Always `pending_spec` on write; `orchestrator-sdd` transitions to `completed` after SDD phase exits |
| `unified_change_scope` | Bug fixes, tweaks, and enhancements all flow through this skill — no separate bug channel |
| `session_guard` | Step 0 always executes before any write; non-terminal sessions require E15 escalation before overwrite; terminal sessions warn but proceed |
| `session_overwrite_protocol` | Silent overwrite prohibited; terminal-state sessions emit `[session_conflict]` warning; `pending_spec` sessions use AskUserQuestion (E15 gate) to capture `force_overwrite` or `abort` |
