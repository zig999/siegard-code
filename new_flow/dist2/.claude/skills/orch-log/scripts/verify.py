#!/usr/bin/env python3
"""CLI: verify hash-chain integrity of the orchestration log."""
import argparse
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from orch_core import verify_chain


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
    return p.parse_args()


def main() -> int:
    args = _parse_args()

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
