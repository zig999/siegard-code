---
description: Run runtime cleanup interactively. Garbage-collects orphan blobs and purges temporary .orch/ files. Usage: /u-cleanup [light|full|reset|delete-log] [--workflow-id <id>] [--operator <identity>]
---

Read the following file:
1. .claude/skills/orch-cleanup/SKILL.md

## Argument resolution

Extract from `$ARGUMENTS`:

| Argument | Values | Default |
|----------|--------|---------|
| `MODE` | `light` \| `full` \| `reset` \| `delete-log` | `light` |
| `--workflow-id <id>` | string | none (all sessions) |
| `--operator <id>` | string | required for `reset` and `delete-log` modes |

**Mode definitions:**

- `light` — Scenario A: remove worker registry, metrics, lock file
- `full` — Scenario B: light + orphan blobs + session dirs
- `reset` — Scenario C: full + archive log.jsonl (log preserved as archive file)
- `delete-log` — Scenario D: full + permanently delete log.jsonl and all archives (**irreversible**)

If `MODE` is not provided, default to `light`.

If `MODE` is `reset` or `delete-log` and `--operator` is not provided, stop and ask:
> "This mode requires an operator identity for audit logging. Provide --operator <identity> to continue."

## Execution flow

### Step 1 — Pre-condition check

Verify no active workers are running by checking for claimed tasks:

```bash
python3 .claude/skills/orch-state/scripts/reduce.py
```

Parse the output: if any task has `"status": "claimed"`, **stop** and report:
```
Cleanup aborted: active workers detected (tasks with status "claimed").
Wait for all workers to complete before running cleanup.
```

If `.orch/` does not exist: report "Nothing to clean — .orch/ directory not found." and stop.

If `log.jsonl` is corrupt and `MODE` is not `delete-log`: abort and report:
```
Cleanup aborted: log.jsonl is corrupted. Repair the log before running cleanup,
or use delete-log mode to eliminate it completely.
```

### Step 2 — Dry-run

Run the appropriate dry-run based on `MODE`:

**light:**
```bash
python3 .claude/scripts/purge.py --json
```

**full:**
```bash
python3 .claude/scripts/purge.py --blobs --sessions [--workflow-id <id>] --json
```

**reset:**
```bash
python3 .claude/scripts/purge.py --blobs --sessions --reset-log --operator <identity> --json
```

**delete-log:**
```bash
python3 .claude/scripts/purge.py --blobs --sessions --delete-log --operator <identity> --json
```

Present the dry-run output to the user in a readable summary:
- Files to delete (count and total size)
- For `reset`: list of files that will be archived
- For `delete-log`: list of log files that will be permanently deleted

If nothing to clean: report "Nothing to clean." and stop.

### Step 3 — Confirmation

Ask the user:
> "Proceed with deletion? (yes/no)"

For `delete-log` mode, add a warning before the question:
> "WARNING: delete-log mode will permanently delete log.jsonl and all log archives. There is no recovery. This cannot be undone."

For `reset` mode, clarify before the question:
> "Note: reset mode will archive log.jsonl before truncating it. The archive will remain in .orch/."

If the user answers anything other than `yes`: **abort**. Report "Cleanup cancelled."

### Step 4 — Execute

Run the same command from Step 2 with `--confirm` appended:

**light:**
```bash
python3 .claude/scripts/purge.py --confirm --json
```

**full:**
```bash
python3 .claude/scripts/purge.py --blobs --sessions [--workflow-id <id>] --confirm --json
```

**reset:**
```bash
python3 .claude/scripts/purge.py --blobs --sessions --reset-log --operator <identity> --confirm --json
```

**delete-log:**
```bash
python3 .claude/scripts/purge.py --blobs --sessions --delete-log --operator <identity> --confirm --json
```

### Step 5 — Report

Parse the JSON output and report:

On success (`status: done`):
```
Cleanup complete.
  Files deleted: <n>
  Bytes freed:   <size>
  [Log archived: <archive_name>]      ← reset mode only
  [Log deleted:  <list of files>]     ← delete-log mode only
```

On error (`status: done_with_errors` or exit code 4):
```
Cleanup completed with errors:
  Files deleted: <n>
  Errors:
    <error list>
```

Surface any exit code 4 as a hard error with the full error detail.
