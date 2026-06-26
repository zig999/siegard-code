#!/usr/bin/env python3
"""CLI: verify hash-chain integrity of the orchestration log, with optional recovery."""
import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import verify_chain, verify_and_recover


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Verify hash-chain integrity of the orchestration log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--mode",
        choices=["strict", "audit"],
        default="strict",
        help=(
            "strict: stop at first error, exit 1. "
            "audit: collect all errors, always exit 0 (for investigation)."
        ),
    )
    # Recovery flags
    p.add_argument(
        "--recover",
        action="store_true",
        help="Truncate log at --from-seq and archive the corrupt tail.",
    )
    p.add_argument(
        "--confirm",
        action="store_true",
        help="Required when using --recover (safety gate — prevents accidental truncation).",
    )
    p.add_argument(
        "--from-seq",
        type=int,
        dest="from_seq",
        help="First seq to remove. Events with seq >= from-seq are archived.",
    )
    p.add_argument(
        "--operator",
        type=str,
        help="Operator identity (email or handle). Required with --recover.",
    )
    return p.parse_args()


def _run_recovery(args: argparse.Namespace) -> int:
    if not args.confirm:
        print(json.dumps({
            "ok": False,
            "error": "confirm_required",
            "detail": "--recover requires --confirm (safety gate)",
        }), file=sys.stderr)
        return 2

    if args.from_seq is None:
        print(json.dumps({
            "ok": False,
            "error": "from_seq_required",
            "detail": "--recover requires --from-seq <seq>",
        }), file=sys.stderr)
        return 2

    if not args.operator:
        print(json.dumps({
            "ok": False,
            "error": "operator_required",
            "detail": "--recover requires --operator <identity>",
        }), file=sys.stderr)
        return 2

    try:
        evt = verify_and_recover(
            from_seq=args.from_seq,
            operator=args.operator,
            confirm=True,
        )
        print(json.dumps({
            "ok": True,
            "recovered": True,
            "seq": evt.seq,
            "seq_truncated_from": evt.data["seq_truncated_from"],
            "events_removed": evt.data["events_removed"],
            "corrupt_file_path": evt.data["corrupt_file_path"],
            "operator": evt.data["operator"],
        }))
        return 0
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": "log_not_found", "detail": str(exc)}), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "invalid_argument", "detail": str(exc)}), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"unexpected: {exc}"}), file=sys.stderr)
        return 1


def main() -> int:
    args = _parse_args()

    if args.recover:
        return _run_recovery(args)

    result = verify_chain(mode=args.mode)

    output = {
        "ok": result.ok,
        "message": result.message,
        "mode": result.mode,
        "events_verified": result.events_verified,
    }
    if result.first_error_seq is not None:
        output["first_error_seq"] = result.first_error_seq
    if result.error_details:
        output["error_details"] = result.error_details
    if result.truncation_candidate is not None:
        output["truncation_candidate"] = result.truncation_candidate

    print(json.dumps(output))

    if args.mode == "audit":
        return 0
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
