#!/usr/bin/env python3
"""Select worker sub-agent for a test-phase task."""
import argparse
import json
import sys

ROUTING_TABLE = {
    ("test-run", "be"):        "u-test-runner",
    ("test-run", "fe"):        "u-test-runner",
    ("test-run", "fullstack"): "u-test-runner",
}
DEFAULT_WORKER = "u-test-runner"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-type", required=True)
    parser.add_argument("--stack", default="be")
    args = parser.parse_args()

    task_type = args.task_type.strip()
    stack = args.stack.strip()

    worker = ROUTING_TABLE.get((task_type, stack), DEFAULT_WORKER)

    print(json.dumps({
        "worker": worker,
        "task_type": task_type,
        "stack": stack,
        "phase": "test",
    }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }))
        sys.exit(1)
