#!/usr/bin/env python3
"""
evaluate_circuit.py — Evaluates circuit breaker state from current OrchState.

M3: Wraps orch_core.evaluate_circuit_state() so the orchestrator calls this
script instead of reimplementing the logic inline.

Usage:
    python3 .claude/scripts/evaluate_circuit.py

Output (stdout): JSON object with circuit breaker evaluation result.

Exit codes:
    0  Evaluation complete (check 'should_trip' in output).
    1  Error (log absent or reduce failed).
"""
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_DIST_DIR = _SCRIPTS_DIR.parent
_LIB = _DIST_DIR / "lib"

sys.path.insert(0, str(_LIB))

from orch_core import (
    ORCH_DIR,
    CorruptedLogError,
    IllegalTransition,
    evaluate_circuit_state,
    load_config,
    now_iso,
    reduce_all,
)


def main() -> int:
    log_file = ORCH_DIR / "log.jsonl"
    if not log_file.exists():
        print(json.dumps({
            "should_trip": False,
            "already_tripped": False,
            "failure_count": 0,
            "threshold": 50,
            "window_start": now_iso(),
            "window_end": now_iso(),
            "window_minutes": 10,
            "note": "no_log",
        }))
        return 0

    try:
        state = reduce_all()
    except (CorruptedLogError, IllegalTransition) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": f"internal_error: {exc}"}))
        return 1

    now = now_iso()
    # A4: honor operator overrides in .orch/config.json (was silently ignored — the
    # evaluator fell back to built-in defaults). Bad config → fall back to defaults.
    try:
        config = load_config()
    except Exception:  # noqa: BLE001
        config = None
    result = evaluate_circuit_state(state, now, config)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
