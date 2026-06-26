#!/usr/bin/env python3
"""
Operational recovery for stuck improve workflows.

A workflow gets stuck when orchestrator-sdd completed the spec pipeline but
spec_change_status was not updated to "completed" in improve-scope.json, and
orchestrator-dev's spec_change_status guard is blocking the dev phase.

Usage:
  python3 .claude/scripts/fix_stuck_improve.py --session <workflow_id> --action <action>

Actions:
  accept_divergence  Set spec_change_status="divergence_accepted" and proceed to /u-dev.
                     Use when you want to skip the spec update and go straight to implementation.
  retry              Validate log integrity and print the command to re-run the spec pipeline.

Options:
  --dry-run          Show what would change without writing anything.
"""
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPTS_DIR.parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

try:
    from orch_core import ORCH_DIR, verify_chain, read_events_filtered, EventType, now_iso
except ImportError as exc:
    print(f"ERROR: cannot import orch_core from {_LIB_DIR}: {exc}", file=sys.stderr)
    sys.exit(1)


def _resolve_scope_path(workflow_id: str) -> Path:
    return ORCH_DIR / "sessions" / workflow_id / "improve-scope.json"


def _load_scope(scope_path: Path) -> dict:
    if not scope_path.exists():
        print(f"ERROR: improve-scope.json not found at {scope_path}", file=sys.stderr)
        print(f"       Check that --session matches the session directory name under .orch/sessions/",
              file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(scope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: improve-scope.json is malformed: {exc}", file=sys.stderr)
        sys.exit(1)


def _action_accept_divergence(workflow_id: str, dry_run: bool) -> int:
    scope_path = _resolve_scope_path(workflow_id)
    scope = _load_scope(scope_path)

    current = scope.get("spec_change_status", "<absent>")
    if current in ("completed", "divergence_accepted"):
        print(f"INFO: spec_change_status is already '{current}' — no action needed.")
        return 0

    print(f"Session    : {workflow_id}")
    print(f"File       : {scope_path}")
    print(f"Current    : spec_change_status = '{current}'")
    print(f"New        : spec_change_status = 'divergence_accepted'")
    print()

    if dry_run:
        print("DRY RUN — no changes written.")
        return 0

    scope["spec_change_status"] = "divergence_accepted"
    scope["divergence_accepted_at"] = now_iso()
    scope["divergence_accepted_by"] = "fix_stuck_improve.py"
    scope_path.write_text(json.dumps(scope, indent=2) + "\n", encoding="utf-8")

    print("Written.")
    print()
    print("Next step:")
    print(f"  /u-dev {workflow_id}")
    print()
    print("NOTE: The spec changes described in improve-scope.json were NOT applied.")
    print("      Review affected_specs entries and decide whether to update specs manually.")
    return 0


def _action_retry(workflow_id: str, dry_run: bool) -> int:
    scope_path = _resolve_scope_path(workflow_id)
    scope = _load_scope(scope_path)

    current = scope.get("spec_change_status", "<absent>")
    print(f"Session            : {workflow_id}")
    print(f"spec_change_status : {current}")
    print()

    if current != "pending_spec":
        print(f"INFO: spec_change_status is '{current}' — a spec pipeline retry is only needed when 'pending_spec'.")
        return 0

    # Validate log integrity
    print("Validating log integrity...")
    result = verify_chain(mode="strict")
    if not result.ok:
        print(f"ERROR: Log integrity check failed — {result.message}", file=sys.stderr)
        print("       Resolve log corruption before retrying.", file=sys.stderr)
        print("       See: python3 .claude/scripts/preflight.py", file=sys.stderr)
        return 1
    print(f"  OK — {result.events_verified} events verified.")

    # Check for existing spec_pipeline_return
    returns = [
        e for e in read_events_filtered(event_type=EventType.SPEC_PIPELINE_RETURN.value)
        if e.data.get("workflow_id") == workflow_id
    ]
    if returns:
        seq = returns[-1].seq
        print(f"\nINFO: spec_pipeline_return already emitted at seq {seq}.")
        print("      The spec pipeline completed but improve-scope.json was not updated.")
        print("      Fix: update spec_change_status manually to 'completed' in improve-scope.json")
        print(f"      File: {scope_path}")
        return 0

    print()
    print("Diagnosis: spec pipeline was interrupted before completing.")
    print()
    print("IMPORTANT: Before retrying, ensure latest artifacts are deployed:")
    print("  copy the contents of siegard-code dist/.claude/ into this project's .claude/")
    print()
    if dry_run:
        print("DRY RUN — no changes written.")
    print("Next step:")
    print("  /u-orchestrator")
    print()
    print("The orchestrator will re-enter the SDD phase and resume the fast-track pipeline.")
    return 0


def main() -> int:
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    workflow_id: str | None = None
    action: str | None = None
    dry_run = "--dry-run" in args

    i = 0
    while i < len(args):
        if args[i] == "--session" and i + 1 < len(args):
            workflow_id = args[i + 1]
            i += 2
        elif args[i] == "--action" and i + 1 < len(args):
            action = args[i + 1]
            i += 2
        else:
            i += 1

    if not workflow_id:
        print("ERROR: --session <workflow_id> is required.", file=sys.stderr)
        return 1
    if not action:
        print("ERROR: --action <accept_divergence|retry> is required.", file=sys.stderr)
        return 1
    if action not in ("accept_divergence", "retry"):
        print(f"ERROR: unknown action '{action}'. Choose: accept_divergence, retry.", file=sys.stderr)
        return 1

    if action == "accept_divergence":
        return _action_accept_divergence(workflow_id, dry_run)
    return _action_retry(workflow_id, dry_run)


if __name__ == "__main__":
    sys.exit(main())
