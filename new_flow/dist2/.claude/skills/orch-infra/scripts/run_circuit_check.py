#!/usr/bin/env python3
"""run_circuit_check.py — Wrapper: evaluates circuit breaker state, returns structured result.

Returns ok (exit 0) if the log does not exist yet (first run).

Exit codes:
    0  Circuit open (healthy).
    1  Circuit tripped or evaluation error.
"""
import json
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"

sys.path.insert(0, str(_LIB))

from orch_core import (
    ORCH_DIR,
    CorruptedLogError,
    IllegalTransition,
    evaluate_circuit_state,
    now_iso,
    reduce_all,
)


def main() -> int:
    log_file = ORCH_DIR / "log.jsonl"

    if not log_file.exists():
        print(json.dumps({
            "status": "ok",
            "check": "circuit",
            "timestamp": now_iso(),
            "tripped": False,
            "failure_count": 0,
            "threshold": 0,
            "note": "no_log",
        }))
        return 0

    try:
        state = reduce_all()
    except (CorruptedLogError, IllegalTransition) as exc:
        print(json.dumps({
            "status": "blocked",
            "check": "circuit",
            "timestamp": now_iso(),
            "reason": "reduce_failed",
            "detail": {"message": str(exc)},
        }))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "blocked",
            "check": "circuit",
            "timestamp": now_iso(),
            "reason": "internal_error",
            "detail": {"message": str(exc)},
        }))
        return 1

    now = now_iso()
    cb = evaluate_circuit_state(state, now)

    tripped = bool(cb.get("should_trip", False) or cb.get("already_tripped", False))
    output: dict = {
        "status": "blocked" if tripped else "ok",
        "check": "circuit",
        "timestamp": now,
        "tripped": tripped,
        "failure_count": cb.get("failure_count", 0),
        "threshold": cb.get("threshold", 0),
    }
    if tripped:
        output["reason"] = "circuit_tripped"

    print(json.dumps(output))
    return 1 if tripped else 0


if __name__ == "__main__":
    sys.exit(main())
