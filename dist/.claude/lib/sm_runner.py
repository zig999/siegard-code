#!/usr/bin/env python3
"""CLI wrapper for StateMachine evaluation.

Usage:
    sm_runner.py --machine <name> --inputs '<json>'   # Evaluate
    sm_runner.py --machine <name> --inputs '<json>' --state <state>
    sm_runner.py --list                               # List registered machines

Output: JSON with action.name and action.params to stdout.
Exit codes:
    0 = match found
    1 = error (unknown machine, invalid input JSON, no_match)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from orch_core import (  # noqa: E402
    DEV_TRANSITIONS,
    META_TRANSITIONS,
    REVIEW_TRANSITIONS,
    SDD_TRANSITIONS,
    TEST_TRANSITIONS,
    Action,
    DevStateMachine,
    MetaStateMachine,
    ReviewStateMachine,
    SddStateMachine,
    StateMachine,
    TestPhaseStateMachine,
)

# Each entry: {"machine": StateMachine, "initial_state": str}
REGISTERED_MACHINES: dict[str, dict] = {
    "test": {
        "machine": TestPhaseStateMachine(TEST_TRANSITIONS),
        "initial_state": "entry",
    },
    "meta": {
        "machine": MetaStateMachine(META_TRANSITIONS),
        "initial_state": "post_infra",
    },
    "dev": {
        "machine": DevStateMachine(DEV_TRANSITIONS),
        "initial_state": "post_manifest",
    },
    "review": {
        "machine": ReviewStateMachine(REVIEW_TRANSITIONS),
        "initial_state": "classify_qa_mode_done",
    },
    "sdd": {
        "machine": SddStateMachine(SDD_TRANSITIONS),
        "initial_state": "triage_done",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a registered orchestrator state machine.",
    )
    parser.add_argument("--machine", help="Machine name (e.g. sdd, dev, review, test, meta)")
    parser.add_argument("--inputs", default="{}", help="JSON object of inputs")
    parser.add_argument("--state", default=None, help="Override initial state")
    parser.add_argument("--list", action="store_true", help="List registered machines")
    args = parser.parse_args()

    if args.list:
        print(json.dumps({"registered_machines": sorted(REGISTERED_MACHINES.keys())}))
        return 0

    if not args.machine:
        print(json.dumps({"error": "missing_machine_arg"}), file=sys.stderr)
        return 1

    if args.machine not in REGISTERED_MACHINES:
        print(
            json.dumps(
                {
                    "error": "unknown_machine",
                    "machine": args.machine,
                    "available": sorted(REGISTERED_MACHINES.keys()),
                }
            ),
            file=sys.stderr,
        )
        return 1

    try:
        inputs = json.loads(args.inputs)
        if not isinstance(inputs, dict):
            raise ValueError("inputs must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps({"error": "invalid_inputs_json", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 1

    entry = REGISTERED_MACHINES[args.machine]
    sm: StateMachine = entry["machine"]
    state = args.state or entry["initial_state"]

    action = sm.evaluate(state, inputs)
    print(json.dumps({"action": action.name, "params": action.params, "state": state}))
    return 0 if action.name != "no_match" else 1


if __name__ == "__main__":
    sys.exit(main())
