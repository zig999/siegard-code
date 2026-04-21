#!/usr/bin/env python3
"""CLI: human-readable summary of current orchestration state."""
import sys
from collections import Counter
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import CorruptedLogError, IllegalTransition, reduce_all


def _bar(count: int, total: int, width: int = 20) -> str:
    filled = int(width * count / total) if total else 0
    return "█" * filled + "░" * (width - filled)


def main() -> int:
    try:
        state = reduce_all()
    except CorruptedLogError as exc:
        print(f"ERROR: corrupted log — {exc}", file=sys.stderr)
        return 1
    except IllegalTransition as exc:
        print(f"ERROR: illegal transition — {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Header
    wf = state.workflow_id or "(none)"
    print(f"Workflow : {wf}")
    print(f"Status   : {state.run_status}")
    print(f"Phase    : {state.current_phase or '(none)'}")
    print(f"Last seq : {state.last_seq}")

    if state.escalation:
        print(f"ESCALATION: {state.escalation.get('code', '?')} — {state.escalation.get('reason', '')}")

    if state.circuit_breaker:
        print(f"CIRCUIT BREAKER: {state.circuit_breaker.get('status', '?')}")

    # Tasks by status
    if state.tasks:
        print()
        print("Tasks")
        print("─────")
        def _status_str(s) -> str:
            return s.value if hasattr(s, "value") else str(s)

        status_counts: Counter = Counter(_status_str(t.status) for t in state.tasks.values())
        total = len(state.tasks)
        for status, count in sorted(status_counts.items()):
            bar = _bar(count, total)
            print(f"  {status:<20} {bar}  {count:>3} / {total}")

        # Per-phase breakdown
        phase_counts: dict[str, Counter] = {}
        for t in state.tasks.values():
            phase_counts.setdefault(t.phase, Counter())[_status_str(t.status)] += 1
        print()
        print("Tasks by phase")
        print("──────────────")
        for phase, counts in sorted(phase_counts.items()):
            parts = ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
            print(f"  {phase:<20} {parts}")
    else:
        print()
        print("Tasks  : (none)")

    # Phases
    if state.phases:
        print()
        print("Phases")
        print("──────")
        for name, p in sorted(state.phases.items(), key=lambda kv: kv[1].order):
            marker = "▶" if name == state.current_phase else " "
            phase_status = p.status.value if hasattr(p.status, "value") else str(p.status)
            print(f"  {marker} {p.order}. {name:<20} {phase_status}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
