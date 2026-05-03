#!/usr/bin/env python3
"""
circuit_breaker.py — Manual circuit breaker reset script.

Usage:
    python3 .claude/scripts/circuit_breaker.py --reset --confirm --operator <email>

Options:
    --reset          Required. Signals intent to reset the circuit breaker.
    --confirm        Required. Must be explicitly provided; prevents accidental resets.
    --operator       Required. Operator identity (email or handle).
    --notes          Optional. Free-text notes about why the reset is safe.
    --status         Show current circuit breaker status and exit.

Exit codes:
    0  Reset emitted (or status shown).
    1  Circuit not tripped (nothing to reset).
    2  Missing --confirm flag.
    3  Missing --operator flag.
    4  Other error.
"""
import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_DIST_DIR = _SCRIPTS_DIR.parent
_LIB = _DIST_DIR / "lib"
_APPEND = _DIST_DIR / "skills" / "orch-log" / "scripts" / "append.py"

sys.path.insert(0, str(_LIB))

from orch_core import (
    ORCH_DIR,
    reduce_all,
    now_iso,
)


def _show_status(state) -> None:
    cb = state.circuit_breaker
    if cb is None:
        print(json.dumps({"status": "ok", "tripped": False}))
    else:
        print(json.dumps({"status": "tripped", "tripped": True, "detail": cb}))


def main() -> int:
    parser = argparse.ArgumentParser(description="Circuit breaker management script.")
    parser.add_argument("--reset", action="store_true", help="Reset the circuit breaker.")
    parser.add_argument("--confirm", action="store_true",
                        help="Required confirmation flag (prevents accidental resets).")
    parser.add_argument("--operator", type=str, help="Operator identity.")
    parser.add_argument("--notes", type=str, default="", help="Optional reset notes.")
    parser.add_argument("--status", action="store_true", help="Show circuit breaker status.")
    args = parser.parse_args()

    log_file = ORCH_DIR / "log.jsonl"
    if not log_file.exists():
        print(json.dumps({"error": "no_log", "detail": "log.jsonl not found"}),
              file=sys.stderr)
        return 4

    try:
        state = reduce_all()
    except Exception as exc:
        print(json.dumps({"error": "reduce_failed", "detail": str(exc)}), file=sys.stderr)
        return 4

    if args.status:
        _show_status(state)
        return 0

    if not args.reset:
        print(json.dumps({"error": "missing_flag", "detail": "provide --reset to reset"}),
              file=sys.stderr)
        return 4

    if state.circuit_breaker is None:
        print(json.dumps({
            "status": "noop",
            "detail": "circuit breaker is not tripped — nothing to reset",
        }))
        return 1

    if not args.confirm:
        print(json.dumps({
            "error": "confirm_required",
            "detail": "circuit breaker reset requires --confirm (safety gate)",
        }), file=sys.stderr)
        return 2

    if not args.operator:
        print(json.dumps({
            "error": "operator_required",
            "detail": "provide --operator <identity>",
        }), file=sys.stderr)
        return 3

    # Find the seq of the circuit_breaker_tripped event to reference
    from orch_core import read_events, EventType
    cb_seq: int | None = None
    for evt in read_events():
        if evt.event_type == EventType.CIRCUIT_BREAKER_TRIPPED.value:
            cb_seq = evt.seq

    if cb_seq is None:
        print(json.dumps({
            "error": "no_cb_event",
            "detail": "could not find circuit_breaker_tripped event in log",
        }), file=sys.stderr)
        return 4

    # Emit human_response with action=reset_circuit_breaker
    import subprocess
    data = {
        "escalation_seq": cb_seq,
        "action": "reset_circuit_breaker",
        "operator": args.operator,
    }
    if args.notes:
        data["notes"] = args.notes

    cmd = [
        sys.executable, str(_APPEND),
        "--agent", "operator",
        "--event-type", "human_response",
        "--data", json.dumps(data),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(json.dumps({
            "error": "append_failed",
            "detail": result.stderr.strip(),
        }), file=sys.stderr)
        return 4

    evt_out = json.loads(result.stdout)
    print(json.dumps({
        "status": "reset",
        "seq": evt_out.get("seq"),
        "operator": args.operator,
        "reset_at": now_iso(),
        "detail": "circuit breaker reset — orchestrator may now resume spawning",
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
