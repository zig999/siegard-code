---
name: orch-cleanup
description: Runtime cleanup — garbage-collect orphan blobs (gc_orphan_blobs.py) and purge temporary .orch/ files (purge.py). Pre-conditions enforced before any run — no active workers, log integrity verified. Maintenance use only; never run while a workflow is active. Not user-invocable — callers run the scripts directly.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# orch-cleanup

Runtime cleanup skill: garbage-collect orphan blobs and purge temporary `.orch/` files.

## Pre-conditions

**Always verify before invoking either script:**

| Condition | Check | Failure action |
|-----------|-------|----------------|
| No active workers | `python3 .claude/skills/orch-state/scripts/reduce.py` — check `tasks` for any with status `claimed` | Abort — running cleanup while workers append corrupts the log |
| `.orch/` exists | `Path(".orch").exists()` | Skip — nothing to clean |
| `log.jsonl` readable | Exit code of `orch-log verify` is 0 | Abort if corrupt **unless** the intent is to delete the log (`--delete-log`) |

---

## scripts/gc_orphan_blobs.py

Garbage-collects blobs in `.orch/blobs/` whose `event_id` is not referenced by any event in `log.jsonl`.

**When to use:** after a workflow completes or is aborted, to reclaim disk space from unreferenced blobs.

### Usage

```bash
# Step 1 — dry-run (always run first)
python3 .claude/scripts/gc_orphan_blobs.py --json

# Step 2 — execute (only after reviewing dry-run output)
python3 .claude/scripts/gc_orphan_blobs.py --delete --json
```

### Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--delete` | off | Perform actual deletions. Without it: dry-run only. |
| `--json` | off | Machine-readable JSON output. Always use when called by an agent. |

### Output schema

```json
{
  "status": "dry_run | deleted | noop",
  "mode": "dry_run | delete",
  "blobs_total": 10,
  "blobs_referenced": 8,
  "orphans_found": 2,
  "orphans_deleted": 0,
  "bytes_freed": 0,
  "bytes_reclaimable": 4096,
  "orphans": [{"file": "evt_ABC.json", "size_bytes": 2048}],
  "errors": []
}
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (orphans processed, or none found) |
| 1 | No blobs directory or no blob files found |
| 4 | Error (log absent or unreadable) |

---

## scripts/purge.py

Deletes temporary runtime files from `.orch/`. Always requires `--confirm` to execute; without it, runs in dry-run mode.

**When to use:** after a workflow completes, is aborted, or before starting a fresh session. Choose the scenario below that matches the intent.

### Scenarios

#### Scenario A — Light cleanup (workers, metrics, lock)

Removes worker registry entries, metrics snapshots, and the flock lock file. Safe for routine cleanup between sessions.

```bash
# Dry-run
python3 .claude/scripts/purge.py --json

# Execute
python3 .claude/scripts/purge.py --confirm --json
```

#### Scenario B — Full cleanup (add blobs and sessions)

Includes orphan blobs (GC logic) and session artifact directories.

```bash
# Dry-run
python3 .claude/scripts/purge.py --blobs --sessions --json

# Execute
python3 .claude/scripts/purge.py --blobs --sessions --confirm --json

# Limit sessions to a specific workflow
python3 .claude/scripts/purge.py --blobs --sessions --workflow-id <id> --confirm --json
```

#### Scenario C — Safe log reset (archive + truncate)

Archives `log.jsonl` to a timestamped file and truncates it to empty. The original log data is preserved in `.orch/log.jsonl.<workflow>.<timestamp>`. Forces `--blobs`. Requires `--operator`.

**Use when:** resetting between workflow runs while keeping the old log available for audit.

```bash
# Dry-run
python3 .claude/scripts/purge.py --blobs --sessions --reset-log --operator <identity> --json

# Execute
python3 .claude/scripts/purge.py --blobs --sessions --reset-log --operator <identity> --confirm --json
```

#### Scenario D — Complete log deletion (irreversible)

Deletes `log.jsonl` and all archive files matching `log.jsonl.*`. Forces `--blobs`. Requires `--operator`. **No recovery possible.**

**Use when:** eliminating all trace of a workflow, compliance deletion, or clean-slate restart with no audit trail.

```bash
# Dry-run
python3 .claude/scripts/purge.py --blobs --sessions --delete-log --operator <identity> --json

# Execute
python3 .claude/scripts/purge.py --blobs --sessions --delete-log --operator <identity> --confirm --json
```

`--reset-log` and `--delete-log` are mutually exclusive.

### Parameters

| Flag | Required | Description |
|------|----------|-------------|
| `--confirm` | For execution | Safety gate — required to perform actual deletions |
| `--blobs` | No | Include orphan blobs |
| `--sessions` | No | Include session dirs under `.orch/sessions/` |
| `--workflow-id <id>` | No | Limit `--sessions` to a specific workflow |
| `--reset-log` | No | Archive and truncate `log.jsonl`. Forces `--blobs`. |
| `--delete-log` | No | Delete `log.jsonl` and all `log.jsonl.*` archives. Forces `--blobs`. Irreversible. |
| `--operator <identity>` | With `--reset-log` or `--delete-log` | Recorded in output for auditability |
| `--json` | Always (agent use) | Machine-readable JSON output |

### Output schema

```json
{
  "status": "dry_run | done | done_with_errors | noop",
  "mode": "dry_run | delete",
  "files_deleted": 5,
  "bytes_freed": 8192,
  "log_reset": null,
  "log_delete": null,
  "errors": []
}
```

`log_reset` when `--reset-log` was used:
```json
{
  "status": "reset",
  "archive": ".orch/log.jsonl.workflow-id.20260503T120000Z",
  "original_size_bytes": 102400,
  "operator": "<identity>",
  "reset_at": "2026-05-03T12:00:00Z"
}
```

`log_delete` when `--delete-log` was used:
```json
{
  "status": "deleted | deleted_with_errors | noop",
  "files_deleted": ["log.jsonl", "log.jsonl.wf-id.20260503T120000Z"],
  "original_size_bytes": 102400,
  "operator": "<identity>",
  "deleted_at": "2026-05-03T12:00:00Z",
  "errors": []
}
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success — files deleted |
| 2 | Dry-run completed — `--confirm` not provided |
| 3 | Missing required argument or mutually exclusive flags |
| 4 | Error |

---

## scripts/gc_worktrees.py

Garbage-collects integrated per-TC worktrees and branches (SIEGARD-08). The dev phase creates one worktree + branch per Task Contract under `.orch/worktrees/<task_id>` (`feat/TC-*`, `fix/TC-*`, `refactor/TC-*`) and integrates + removes them at Step 5.6 on the success path. This script reclaims any that survived an abnormal exit (crash, abort, non-retryable failure).

**Safety:** only **merged** worktrees/branches are removed. An unmerged TC worktree holds un-integrated work and is KEPT (surfaced under `kept_unmerged`); non-TC worktrees are left untouched. Dry-run by default; `--confirm` executes.

**When to use:** after a workflow completes or is aborted, to reclaim worktrees/branches that Step 5.6 did not clean up.

### Usage

```bash
# Dry-run (always first)
python3 .claude/scripts/gc_worktrees.py --json

# Execute
python3 .claude/scripts/gc_worktrees.py --confirm --json
```

### Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--confirm` | off | Perform removals. Without it: dry-run only. |
| `--main-branch` | `main` (or `$ORCH_MAIN_BRANCH`) | Integration branch tested for "merged". |
| `--json` | off | Machine-readable JSON output. Always use from an agent. |

### Output schema

```json
{
  "status": "dry_run | ok | error",
  "dry_run": true,
  "remove_worktrees": [{"path": ".orch/worktrees/dev_myflow_tc_001", "branch": "feat/TC-dev_myflow_tc_001"}],
  "delete_branches": ["feat/TC-dev_myflow_tc_001"],
  "kept_unmerged": [],
  "candidates": 1
}
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (removed, or dry-run with nothing to do) |
| 2 | Dry-run with candidates pending (`--confirm` not provided) |
| 3 | Active workers — refused (same gate as purge.py) |
| 4 | Error (not a git repo, git failure) |

---

## Decision matrix

| Situation | Script | Scenario |
|-----------|--------|----------|
| Workflow completed normally — free disk space | `gc_orphan_blobs.py` | — |
| Workflow completed — routine reset between sessions | `purge.py` | A or B |
| Workflow aborted — clean worker registry and lock | `purge.py` | A |
| Workflow completed/aborted — reclaim integrated per-TC worktrees/branches | `gc_worktrees.py` | — |
| Reset with audit trail preserved | `purge.py` | C |
| Eliminate all log data — no recovery needed | `purge.py` | D |
| Scheduled maintenance GC | `gc_orphan_blobs.py` | — |

---

## Invariants

- Always run dry-run before execute. Never skip it.
- Never run while any task has status `claimed` (active workers).
- Scenario D (`--delete-log`) is irreversible — no archive, no recovery. Require explicit human confirmation before invoking with `--confirm`.
- Scenario C (`--reset-log`) preserves the log as an archive file — it is not irreversible.
- `--reset-log` and `--delete-log` are mutually exclusive.
- Always pass `--json` when called from an agent context. Parse output before reporting.
- Treat exit code 4 as a hard error — surface it via escalation, do not retry silently.
- A corrupt log does NOT block `--delete-log`. It blocks all other scenarios.
