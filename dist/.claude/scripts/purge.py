#!/usr/bin/env python3
"""
purge.py — Delete all temporary runtime files from .orch/.

Temporary targets (always included):
    .orch/workers/*.json          Worker registry entries
    .orch/metrics/current.json    Session metrics snapshot
    .orch/metrics/last_error.json Last error snapshot
    .orch/log.jsonl.lock          flock lock file

Optional targets (explicit flags required):
    --blobs                       Orphan blobs via gc logic (or all if --reset-log/--delete-log)
    --sessions [--workflow-id X]  Session artifact dirs under .orch/sessions/
    --reset-log                   Archive log.jsonl, delete all blobs, truncate log
    --delete-log                  Completely delete log.jsonl and all log archives (irreversible)

Requires --confirm to perform actual deletions. Without it, runs in dry-run mode
and prints the deletion plan without touching any file.

Usage:
    # Dry-run: show what would be deleted
    python3 .claude/scripts/purge.py [--blobs] [--sessions] [--workflow-id <id>]

    # Execute core cleanup (workers, metrics, lock)
    python3 .claude/scripts/purge.py --confirm

    # Full cleanup including blobs and sessions
    python3 .claude/scripts/purge.py --blobs --sessions --confirm

    # Archive log, wipe everything, reset to clean state (log preserved as archive)
    python3 .claude/scripts/purge.py --blobs --sessions --reset-log \
        --confirm --operator <identity>

    # Completely delete log and all archives (irreversible — no recovery possible)
    python3 .claude/scripts/purge.py --blobs --sessions --delete-log \
        --confirm --operator <identity>

Options:
    --confirm        Required to perform actual deletions (safety gate).
    --blobs          Include orphan blobs (gc_orphan_blobs logic).
    --sessions       Include session dirs under .orch/sessions/.
    --workflow-id    Limit --sessions to a specific workflow_id.
    --reset-log      Archive log.jsonl and truncate it. Forces --blobs.
                     Requires --confirm and --operator.
    --delete-log     Delete log.jsonl and all log.jsonl.* archives. Forces --blobs.
                     Requires --confirm and --operator. Mutually exclusive with --reset-log.
    --operator       Operator identity (required with --reset-log or --delete-log).
    --json           Machine-readable JSON output.

Exit codes:
    0  Success (files deleted, or dry-run with nothing to do).
    2  Dry-run completed — nothing deleted (--confirm not provided).
    3  Missing required argument or mutually exclusive flags.
    4  Error.
"""
import argparse
import json
import shutil
import sys
from datetime import timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_DIST_DIR = _SCRIPTS_DIR.parent
_LIB = _DIST_DIR / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import (
    BLOBS_DIR,
    METRICS_DIR,
    ORCH_DIR,
    WORKERS_DIR,
    LOG_PATH,
    LOCK_PATH,
    LogLock,
    now_iso,
    reduce_all,
)

# gc_orphan_blobs is in the same directory
sys.path.insert(0, str(_SCRIPTS_DIR))
from gc_orphan_blobs import gc_orphan_blobs


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------

_Item = dict  # {"path": Path, "kind": str, "size_bytes": int, "is_dir": bool}


def _item(path: Path, kind: str) -> _Item:
    try:
        if path.is_dir():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        else:
            size = path.stat().st_size
    except OSError:
        size = 0
    return {"path": path, "kind": kind, "size_bytes": size, "is_dir": path.is_dir()}


def _build_plan(
    *,
    include_blobs: bool,
    include_sessions: bool,
    workflow_id: str | None,
    reset_log: bool,
) -> list[_Item]:
    plan: list[_Item] = []

    # --- Always: worker registry entries ---
    if WORKERS_DIR.exists():
        for p in sorted(WORKERS_DIR.glob("*.json")):
            plan.append(_item(p, "worker_registry"))

    # --- Always: metrics snapshots ---
    for name in ("current.json", "last_error.json"):
        p = METRICS_DIR / name
        if p.exists():
            plan.append(_item(p, "metrics"))

    # --- Always: lock file ---
    if LOCK_PATH.exists():
        plan.append(_item(LOCK_PATH, "lock_file"))

    # --- Optional: blobs (orphans only, or all if reset_log) ---
    if include_blobs or reset_log:
        if BLOBS_DIR.exists():
            if reset_log:
                # Reset-log path: delete ALL blobs (log is being wiped)
                for p in sorted(BLOBS_DIR.glob("*.json")):
                    plan.append(_item(p, "blob_all"))
            else:
                # GC path: only orphans (log stays intact)
                from orch_core import is_blob_ref, read_events
                referenced: set[str] = set()
                if LOG_PATH.exists():
                    for event in read_events():
                        if is_blob_ref(event.data):
                            referenced.add(Path(event.data["_blob_ref"]).name)
                for p in sorted(BLOBS_DIR.glob("*.json")):
                    if p.name not in referenced:
                        plan.append(_item(p, "blob_orphan"))

    # --- Optional: session dirs ---
    sessions_root = ORCH_DIR / "sessions"
    if include_sessions and sessions_root.exists():
        if workflow_id:
            target = sessions_root / workflow_id
            if target.exists():
                plan.append(_item(target, "session_dir"))
        else:
            for d in sorted(sessions_root.iterdir()):
                if d.is_dir():
                    plan.append(_item(d, "session_dir"))

    return plan


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _execute_plan(plan: list[_Item]) -> tuple[int, int, list[str]]:
    """Delete everything in plan. Returns (deleted_count, bytes_freed, errors)."""
    deleted = 0
    freed = 0
    errors: list[str] = []

    for item in plan:
        path: Path = item["path"]
        try:
            if item["is_dir"]:
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted += 1
            freed += item["size_bytes"]
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    return deleted, freed, errors


def _delete_log_completely(operator: str) -> dict:
    """
    Deletes log.jsonl and any archive files matching log.jsonl.* pattern.
    Returns a summary dict.
    """
    deleted_files: list[str] = []
    errors: list[str] = []
    original_size = 0

    if LOG_PATH.exists():
        try:
            original_size = LOG_PATH.stat().st_size
            LOG_PATH.unlink()
            deleted_files.append(LOG_PATH.name)
        except OSError as exc:
            errors.append(f"{LOG_PATH.name}: {exc}")

    for archive in sorted(ORCH_DIR.glob("log.jsonl.*")):
        try:
            archive.unlink()
            deleted_files.append(archive.name)
        except OSError as exc:
            errors.append(f"{archive.name}: {exc}")

    if not deleted_files and not errors:
        return {"status": "noop", "detail": "log.jsonl not found"}

    return {
        "status": "deleted" if not errors else "deleted_with_errors",
        "files_deleted": deleted_files,
        "original_size_bytes": original_size,
        "operator": operator,
        "deleted_at": now_iso(),
        "errors": errors,
    }


def _archive_and_reset_log(operator: str) -> dict:
    """
    Archives log.jsonl to log.jsonl.<timestamp> and truncates it.
    Returns a summary dict.
    """
    if not LOG_PATH.exists():
        return {"status": "noop", "detail": "log.jsonl not found"}

    from datetime import datetime
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Derive workflow_id for archive name (best-effort)
    wf_id = "unknown"
    try:
        state = reduce_all()
        if state.workflow_id:
            wf_id = state.workflow_id
    except Exception:
        pass

    archive_name = f"log.jsonl.{wf_id}.{ts}"
    archive_path = ORCH_DIR / archive_name

    original_size = LOG_PATH.stat().st_size
    # A5: archive + truncate under the log lock so a concurrent worker append cannot
    # land between copy2 and the truncation (which would lose that event without ever
    # archiving it). Reading state for wf_id above is best-effort and stays unlocked.
    with LogLock():
        shutil.copy2(LOG_PATH, archive_path)
        LOG_PATH.write_bytes(b"")

    return {
        "status": "reset",
        "archive": str(archive_path),
        "original_size_bytes": original_size,
        "operator": operator,
        "reset_at": now_iso(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete all temporary runtime files from .orch/."
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Required to perform actual deletions (safety gate)."
    )
    parser.add_argument(
        "--blobs", action="store_true",
        help="Include orphan blobs."
    )
    parser.add_argument(
        "--sessions", action="store_true",
        help="Include session dirs under .orch/sessions/."
    )
    parser.add_argument(
        "--workflow-id", type=str, default=None,
        help="Limit --sessions to a specific workflow_id."
    )
    parser.add_argument(
        "--reset-log", action="store_true",
        help="Archive and truncate log.jsonl. Forces --blobs. Requires --operator."
    )
    parser.add_argument(
        "--delete-log", action="store_true",
        help="Completely delete log.jsonl and all log archives. Forces --blobs. Requires --operator. Irreversible."
    )
    parser.add_argument(
        "--operator", type=str, default=None,
        help="Operator identity (required with --reset-log or --delete-log)."
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Machine-readable JSON output."
    )
    args = parser.parse_args()

    if not ORCH_DIR.exists():
        result = {
            "generated_at": now_iso(),
            "status": "noop",
            "detail": ".orch/ directory not found — nothing to clean",
        }
        print(json.dumps(result) if args.as_json else f"Nothing to clean: {result['detail']}")
        return 0

    # Validation
    if args.reset_log and args.delete_log:
        msg = {"error": "exclusive_flags", "detail": "--reset-log and --delete-log are mutually exclusive"}
        print(json.dumps(msg) if args.as_json else f"Error: {msg['detail']}", file=sys.stderr)
        return 3

    if (args.reset_log or args.delete_log) and not args.operator:
        flag = "--reset-log" if args.reset_log else "--delete-log"
        msg = {"error": "operator_required", "detail": f"{flag} requires --operator <identity>"}
        print(json.dumps(msg) if args.as_json else f"Error: {msg['detail']}", file=sys.stderr)
        return 3

    # Build plan
    try:
        plan = _build_plan(
            include_blobs=args.blobs,
            include_sessions=args.sessions,
            workflow_id=args.workflow_id,
            reset_log=args.reset_log or args.delete_log,
        )
    except Exception as exc:
        msg = {"error": "plan_failed", "detail": str(exc)}
        print(json.dumps(msg) if args.as_json else f"Error building plan: {exc}", file=sys.stderr)
        return 4

    total_bytes = sum(item["size_bytes"] for item in plan)
    log_reset_plan = args.reset_log and LOG_PATH.exists()

    # Collect log files that would be deleted by --delete-log for dry-run display
    log_delete_items: list[dict] = []
    if args.delete_log:
        if LOG_PATH.exists():
            log_delete_items.append({"file": LOG_PATH.name, "size_bytes": LOG_PATH.stat().st_size})
        for archive in sorted(ORCH_DIR.glob("log.jsonl.*")):
            log_delete_items.append({"file": archive.name, "size_bytes": archive.stat().st_size})
    log_delete_plan = bool(log_delete_items)

    # --- DRY-RUN (no --confirm) ---
    if not args.confirm:
        dry_result = {
            "generated_at": now_iso(),
            "mode": "dry_run",
            "status": "dry_run",
            "files_to_delete": len(plan),
            "bytes_reclaimable": total_bytes,
            "log_reset_planned": log_reset_plan,
            "log_delete_planned": log_delete_plan,
            "log_delete_items": log_delete_items,
            "items": [
                {"path": str(item["path"].relative_to(ORCH_DIR)), "kind": item["kind"],
                 "size_bytes": item["size_bytes"]}
                for item in plan
            ],
        }
        if args.as_json:
            print(json.dumps(dry_result, indent=2))
        else:
            print(f"purge [DRY-RUN] — {dry_result['generated_at']}")
            print(f"  Files to delete:   {len(plan)}")
            print(f"  Bytes reclaimable: {total_bytes:,}")
            if log_reset_plan:
                print(f"  Log reset:         yes (will archive + truncate log.jsonl)")
            if log_delete_plan:
                print(f"  Log delete:        yes (IRREVERSIBLE — will delete log and all archives)")
                for lf in log_delete_items:
                    print(f"    {lf['file']}  ({lf['size_bytes']:,} bytes)")
            if not plan and not log_reset_plan and not log_delete_plan:
                print("  Nothing to clean.")
            else:
                print()
                by_kind: dict[str, list] = {}
                for item in plan:
                    by_kind.setdefault(item["kind"], []).append(item)
                for kind, items in sorted(by_kind.items()):
                    print(f"  [{kind}] ({len(items)})")
                    for item in items:
                        rel = item["path"].relative_to(ORCH_DIR)
                        print(f"    {rel}  ({item['size_bytes']:,} bytes)")
                print()
                print("  Re-run with --confirm to execute.")
        return 2

    # --- EXECUTE ---
    deleted, freed, errors = _execute_plan(plan)
    log_reset_result: dict = {}
    log_delete_result: dict = {}
    if args.reset_log:
        log_reset_result = _archive_and_reset_log(args.operator or "unknown")
    if args.delete_log:
        log_delete_result = _delete_log_completely(args.operator or "unknown")

    result = {
        "generated_at": now_iso(),
        "mode": "delete",
        "status": "done" if not errors else "done_with_errors",
        "files_deleted": deleted,
        "bytes_freed": freed,
        "log_reset": log_reset_result if log_reset_result else None,
        "log_delete": log_delete_result if log_delete_result else None,
        "errors": errors,
    }

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"purge [DELETE] — {result['generated_at']}")
        print(f"  Files deleted:  {deleted}")
        print(f"  Bytes freed:    {freed:,}")
        if log_reset_result:
            lr = log_reset_result
            if lr.get("status") == "reset":
                print(f"  Log archived:   {Path(lr['archive']).name}")
                print(f"  Log truncated:  yes")
            else:
                print(f"  Log reset:      {lr.get('detail', 'noop')}")
        if log_delete_result:
            ld = log_delete_result
            if ld.get("status") in ("deleted", "deleted_with_errors"):
                for f in ld.get("files_deleted", []):
                    print(f"  Log deleted:    {f}")
            else:
                print(f"  Log delete:     {ld.get('detail', 'noop')}")
            if ld.get("errors"):
                errors = errors + ld["errors"]
        if errors:
            print()
            print("  Errors:")
            for e in errors:
                print(f"    {e}")
            return 4

    return 0


if __name__ == "__main__":
    sys.exit(main())
