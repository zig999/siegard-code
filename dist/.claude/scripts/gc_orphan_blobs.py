#!/usr/bin/env python3
"""
gc_orphan_blobs.py — Garbage-collect blobs not referenced by any log event.

Scans .orch/blobs/ and deletes any file whose event_id does not appear as a
_blob_ref in the current log.jsonl. Safe to run while the workflow is paused;
must NOT run while workers are actively appending to the log.

Usage:
    python3 .claude/scripts/gc_orphan_blobs.py [--delete] [--json]

Options:
    --delete   Actually delete orphan blobs. Default: dry-run (report only).
    --json     Machine-readable JSON output.

Exit codes:
    0  Success (orphans processed, or none found).
    1  No blobs directory or no blob files found.
    4  Error (log absent or unreadable).
"""
import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_DIST_DIR = _SCRIPTS_DIR.parent
_LIB = _DIST_DIR / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import BLOBS_DIR, ORCH_DIR, get_active_workers, is_blob_ref, now_iso, read_events


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _collect_referenced_blob_names() -> set[str]:
    """Returns the set of blob filenames referenced by events in the log."""
    referenced: set[str] = set()
    for event in read_events():
        if is_blob_ref(event.data):
            blob_ref = event.data.get("_blob_ref", "")
            # blob_ref is relative to ORCH_DIR, e.g. "blobs/evt_ABC123.json"
            referenced.add(Path(blob_ref).name)
    return referenced


def gc_orphan_blobs(*, delete: bool = False) -> dict:
    _base = {
        "generated_at": now_iso(),
        "mode": "delete" if delete else "dry_run",
        "blobs_total": 0,
        "blobs_referenced": 0,
        "orphans_found": 0,
        "orphans_deleted": 0,
        "bytes_freed": 0,
        "bytes_reclaimable": 0,
        "orphans": [],
        "errors": [],
    }

    if not BLOBS_DIR.exists():
        return {**_base, "status": "noop", "detail": "blobs directory does not exist"}

    all_blobs = sorted(BLOBS_DIR.glob("*.json"))
    if not all_blobs:
        return {**_base, "status": "noop", "detail": "no blob files found"}

    referenced = _collect_referenced_blob_names()

    orphans = [p for p in all_blobs if p.name not in referenced]
    orphan_details = [
        {"file": p.name, "size_bytes": p.stat().st_size}
        for p in orphans
    ]
    total_bytes = sum(d["size_bytes"] for d in orphan_details)

    deleted = 0
    errors: list[str] = []
    if delete:
        for path in orphans:
            try:
                path.unlink()
                deleted += 1
            except OSError as exc:
                errors.append(f"{path.name}: {exc}")

    status = "deleted" if (delete and deleted > 0) else ("dry_run" if not delete else "noop")
    return {
        **_base,
        "status": status,
        "blobs_total": len(all_blobs),
        "blobs_referenced": len(all_blobs) - len(orphans),
        "orphans_found": len(orphans),
        "orphans_deleted": deleted,
        "bytes_freed": total_bytes if delete else 0,
        "bytes_reclaimable": total_bytes if not delete else 0,
        "orphans": orphan_details,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Garbage-collect blobs not referenced by any log event."
    )
    parser.add_argument(
        "--delete", action="store_true",
        help="Delete orphan blobs. Without this flag, runs in dry-run mode."
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Machine-readable JSON output."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Override the active-worker safety check (only when no workers run)."
    )
    args = parser.parse_args()

    log_file = ORCH_DIR / "log.jsonl"
    if not log_file.exists():
        msg = {"error": "no_log", "detail": "log.jsonl not found — nothing to GC"}
        if args.as_json:
            print(json.dumps(msg))
        else:
            print(f"Error: {msg['detail']}", file=sys.stderr)
        return 4

    # A5: deleting blobs while workers are mid-flight can drop a blob a worker just
    # externalized before its referencing event lands in the log. Refuse --delete when
    # workers are registered (overridable with --force on a known-idle system). The
    # docstring's "must NOT run while workers are appending" is now enforced, not advisory.
    if args.delete and not args.force:
        active = get_active_workers()
        if active:
            msg = {
                "error": "active_workers",
                "detail": f"{len(active)} worker(s) registered — refusing --delete; "
                          f"re-run when idle or pass --force.",
            }
            if args.as_json:
                print(json.dumps(msg), file=sys.stderr)
            else:
                print(f"Error: {msg['detail']}", file=sys.stderr)
            return 3

    try:
        result = gc_orphan_blobs(delete=args.delete)
    except Exception as exc:
        msg = {"error": "gc_failed", "detail": str(exc)}
        if args.as_json:
            print(json.dumps(msg), file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 4

    if args.as_json:
        print(json.dumps(result, indent=2))
        return 0

    # Human-readable output
    mode_label = "DELETE" if args.delete else "DRY-RUN"
    print(f"gc_orphan_blobs [{mode_label}] — {result['generated_at']}")
    print(f"  Blobs total:      {result['blobs_total']}")
    print(f"  Referenced:       {result['blobs_referenced']}")
    print(f"  Orphans found:    {result['orphans_found']}")

    if result["orphans_found"] == 0:
        print("  No orphans — nothing to do.")
        return 0

    if args.delete:
        print(f"  Orphans deleted:  {result['orphans_deleted']}")
        print(f"  Bytes freed:      {result['bytes_freed']:,}")
    else:
        print(f"  Bytes reclaimable:{result['bytes_reclaimable']:,}")
        print()
        print("  Orphan files (would be deleted with --delete):")
        for o in result["orphans"]:
            print(f"    {o['file']}  ({o['size_bytes']:,} bytes)")
        print()
        print("  Re-run with --delete to remove orphans.")

    if result["errors"]:
        print()
        print("  Errors during deletion:")
        for e in result["errors"]:
            print(f"    {e}")
        return 4

    return 0


if __name__ == "__main__":
    sys.exit(main())
