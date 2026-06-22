#!/usr/bin/env python3
"""
respond_escalation.py — append a human_response to resolve an active escalation (SIEGARD-07).

Standardizes the resume protocol that was previously tacit knowledge (hand-write
a human_response event with the right escalation_seq). Useful for headless /
batch contexts where AskUserQuestion is not available, or to resume a background
orchestrator that escalated and came to rest.

By default it targets the currently-active escalation (reduce_all().escalation);
pass --escalation-seq to target a specific one. After appending, re-invoke the
relevant orchestrator to resume.

Usage:
    # Respond to the active escalation
    python3 .claude/scripts/respond_escalation.py --action approve --operator alice --json

    # Target a specific escalation seq
    python3 .claude/scripts/respond_escalation.py --escalation-seq 553 --action return_to_dev --json

Action values are escalation-specific (see ESCALATION_CODES.md), e.g.:
    confirm_proceed | approve | return_to_dev | return_partial | accept_with_failures

Exit codes:
    0  human_response appended.
    1  No active escalation / log missing / append failed.
    3  Missing required argument.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from orch_core import EventType, append_event, reduce_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve an active escalation with a human_response.")
    parser.add_argument("--action", required=True, help="Response action (escalation-specific).")
    parser.add_argument("--operator", default="operator", help="Operator identity recorded in the event.")
    parser.add_argument("--notes", default=None, help="Optional free-text note.")
    parser.add_argument("--escalation-seq", type=int, default=None,
                        help="Target a specific escalation seq (default: the active one).")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        state = reduce_all()
    except FileNotFoundError:
        out = {"status": "error", "reason": "log_missing", "detail": "no .orch/log.jsonl"}
        print(json.dumps(out), file=sys.stderr)
        return 1

    active = state.escalation
    if args.escalation_seq is not None:
        esc_seq = args.escalation_seq
        code = active.get("code") if active and active.get("seq") == esc_seq else None
    else:
        if not active:
            out = {"status": "error", "reason": "no_active_escalation",
                   "detail": "reduce_all().escalation is None — nothing to respond to"}
            print(json.dumps(out), file=sys.stderr)
            return 1
        esc_seq = active["seq"]
        code = active.get("code")

    data = {"escalation_seq": esc_seq, "action": args.action, "operator": args.operator}
    if args.notes:
        data["notes"] = args.notes

    try:
        ev = append_event(agent=args.operator, event_type=EventType.HUMAN_RESPONSE.value, data=data)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "append_failed", "detail": str(exc)}), file=sys.stderr)
        return 1

    out = {
        "status": "ok",
        "escalation_seq": esc_seq,
        "escalation_code": code,
        "action": args.action,
        "operator": args.operator,
        "response_seq": ev.seq,
        "next_step": "re-invoke the relevant orchestrator to resume",
    }
    print(json.dumps(out) if args.as_json else json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
