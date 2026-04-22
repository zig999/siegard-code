#!/usr/bin/env python3
"""CLI: print current phase derived from the event log."""
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import CorruptedLogError, IllegalTransition, reduce_all


def main() -> int:
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

    output: dict = {
        "current_phase": phase,
        "status": phase_state.status if phase_state is not None else None,
        "order": phase_state.order if phase_state is not None else None,
    }

    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
