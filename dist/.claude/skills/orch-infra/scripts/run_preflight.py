#!/usr/bin/env python3
"""run_preflight.py — Wrapper: runs preflight.py --quick, returns structured result.

Exit codes:
    0  All preflight checks passed.
    1  At least one check failed, or execution error.
"""
import json
import subprocess
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"
_SCRIPTS_DIR = _CLAUDE_DIR / "scripts"

sys.path.insert(0, str(_LIB))

from orch_core import now_iso


def main() -> int:
    preflight_script = _SCRIPTS_DIR / "preflight.py"

    try:
        result = subprocess.run(
            [sys.executable, str(preflight_script), "--quick"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "status": "blocked",
            "check": "preflight",
            "timestamp": now_iso(),
            "reason": "preflight_timeout",
            "detail": {"message": "preflight.py --quick timed out after 30s"},
        }))
        return 1
    except OSError as exc:
        print(json.dumps({
            "status": "blocked",
            "check": "preflight",
            "timestamp": now_iso(),
            "reason": "preflight_exec_error",
            "detail": {"message": str(exc)},
        }))
        return 1

    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({
            "status": "blocked",
            "check": "preflight",
            "timestamp": now_iso(),
            "reason": "invalid_output",
            "detail": {"stdout": result.stdout[:500], "stderr": result.stderr[:500]},
        }))
        return 1

    ok = bool(data.get("ok", False))
    output: dict = {
        "status": "ok" if ok else "blocked",
        "check": "preflight",
        "timestamp": now_iso(),
        "passed": data.get("passed", 0),
        "total": data.get("total", 0),
        "failed_count": data.get("failed_count", 0),
    }
    if not ok:
        output["reason"] = "preflight_failed"
        if "failed_checks" in data:
            output["failed_checks"] = data["failed_checks"]

    print(json.dumps(output))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
