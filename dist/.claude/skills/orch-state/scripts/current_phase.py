#!/usr/bin/env python3
"""CLI: print current phase derived from the event log.

Default: reduces the log (reduce_all) and derives the current phase.

--from-stdin: derives the same output from a pre-reduced OrchState JSON
(the exact stdout of reduce.py) read from stdin — no second full-log
reduction. Orchestrators that already hold reduce.py output MUST use this
mode: it removes one O(n) log pass per cycle. A reduce.py error object on
stdin is propagated verbatim (same shape, exit 1), so the caller's error
handling is identical in both modes.
"""
import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import CorruptedLogError, IllegalTransition, reduce_all


def _output(phase: str | None, phase_state_dict: dict | None) -> dict:
    return {
        "current_phase": phase,
        "status": phase_state_dict.get("status") if phase_state_dict else None,
        "order": phase_state_dict.get("order") if phase_state_dict else None,
    }


def _from_stdin() -> int:
    try:
        state_dict = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": "invalid_state_json",
                          "detail": str(exc)}))
        return 1
    if isinstance(state_dict, dict) and state_dict.get("status") == "error":
        # Propagate the reduce.py error verbatim — caller sees the same
        # failure it would have seen re-reducing.
        print(json.dumps(state_dict))
        return 1
    phase = state_dict.get("current_phase")
    ps = (state_dict.get("phases") or {}).get(phase) if phase else None
    print(json.dumps(_output(phase, ps)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--from-stdin", action="store_true",
        help="Derive from reduce.py JSON on stdin instead of re-reducing the log.",
    )
    args = ap.parse_args()

    if args.from_stdin:
        return _from_stdin()

    try:
        state = reduce_all()
    except CorruptedLogError as exc:
        print(json.dumps({"status": "error", "reason": "corrupted_log", "detail": str(exc)}))
        return 1
    except IllegalTransition as exc:
        print(json.dumps({"status": "error", "reason": "illegal_transition", "detail": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    phase = state.current_phase
    phase_state = state.phases.get(phase) if phase else None
    print(json.dumps(_output(
        phase, phase_state.to_dict() if phase_state is not None else None,
    )))
    return 0


if __name__ == "__main__":
    sys.exit(main())
