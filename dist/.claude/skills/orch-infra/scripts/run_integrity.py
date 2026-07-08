#!/usr/bin/env python3
"""run_integrity.py — Wrapper: runs verify_chain in strict mode, returns structured result.

Returns ok (exit 0) if the log does not exist yet (first run).

Exit codes:
    0  Chain intact, or no log present.
    1  Chain invalid or internal error.
"""
import json
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"

sys.path.insert(0, str(_LIB))

from orch_core import ORCH_DIR, CorruptedLogError, now_iso, verify_chain_cached


def main() -> int:
    log_file = ORCH_DIR / "log.jsonl"

    if not log_file.exists():
        print(json.dumps({
            "status": "ok",
            "check": "integrity",
            "timestamp": now_iso(),
            "events_verified": 0,
            "note": "no_log",
        }))
        return 0

    try:
        # Verified-prefix cache: re-hashes only the tail appended since the
        # last verified boundary; any anomaly falls back to the canonical
        # full GENESIS scan inside verify_chain_cached (strict semantics).
        result = verify_chain_cached()
    except CorruptedLogError as exc:
        print(json.dumps({
            "status": "blocked",
            "check": "integrity",
            "timestamp": now_iso(),
            "reason": "corrupted_log",
            "detail": {"message": str(exc)},
        }))
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "blocked",
            "check": "integrity",
            "timestamp": now_iso(),
            "reason": "internal_error",
            "detail": {"message": str(exc)},
        }))
        return 1

    ok = result.ok
    output: dict = {
        "status": "ok" if ok else "blocked",
        "check": "integrity",
        "timestamp": now_iso(),
        "events_verified": result.events_verified,
    }
    if not ok:
        output["reason"] = "chain_invalid"
        if result.first_error_seq is not None:
            output["first_error_seq"] = result.first_error_seq
        if result.error_details:
            output["error_details"] = result.error_details[:5]
        if result.truncation_candidate is not None:
            output["truncation_candidate"] = result.truncation_candidate

    print(json.dumps(output))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
