#!/usr/bin/env python3
"""
check_all_domains_validated.py — Exit criterion: sdd / all_domains_validated.

Criterion met when:
  - SPECS_DIR/_validation/ exists and contains at least one file
  - No .yaml or .md file in that directory contains Status: INVALID

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/check_all_domains_validated.py

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
    SPECS_DIR         — specs directory, relative to ORCH_PROJECT_DIR (default: specs)

Output (exit 0 when status=ok, exit 1 when status=blocked):
    {"status": "ok" | "blocked", "check": "all_domains_validated",
     "timestamp": "<ISO-8601>", "evidence": {...}}
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CHECK_ID = "all_domains_validated"

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_VALIDATION_DIR = _SPECS_DIR / "_validation"

_STATUS_RE = re.compile(r"^\s*[Ss]tatus\s*:\s*(\S+)", re.MULTILINE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate() -> dict:
    if not _VALIDATION_DIR.exists():
        return {
            "status": "blocked",
            "check": CHECK_ID,
            "criterion": CHECK_ID,
            "met": False,
            "timestamp": _now_iso(),
            "evidence": {
                "validation_dir": str(_VALIDATION_DIR),
                "exists": False,
                "total": 0,
                "passing": 0,
                "failing": [],
            },
        }

    files = sorted(_VALIDATION_DIR.glob("*.yaml")) + sorted(_VALIDATION_DIR.glob("*.md"))

    if not files:
        return {
            "status": "blocked",
            "check": CHECK_ID,
            "criterion": CHECK_ID,
            "met": False,
            "timestamp": _now_iso(),
            "evidence": {
                "validation_dir": str(_VALIDATION_DIR),
                "exists": True,
                "total": 0,
                "passing": 0,
                "failing": [],
            },
        }

    failing = []
    passing_count = 0

    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            failing.append({"file": f.name, "reason": "unreadable"})
            continue

        match = _STATUS_RE.search(content)
        status_value = match.group(1).upper() if match else None

        if status_value == "INVALID":
            failing.append({"file": f.name, "status": match.group(1)})
        else:
            passing_count += 1

    met = len(failing) == 0
    return {
        "status": "ok" if met else "blocked",
        "check": CHECK_ID,
        "criterion": CHECK_ID,
        "met": met,
        "timestamp": _now_iso(),
        "evidence": {
            "validation_dir": str(_VALIDATION_DIR),
            "exists": True,
            "total": len(files),
            "passing": passing_count,
            "failing": failing,
        },
    }


def main() -> int:
    result = evaluate()
    print(json.dumps(result))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({
            "status": "blocked",
            "check": CHECK_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evidence": {"error": "internal_error", "detail": str(exc)},
        }), file=sys.stderr)
        sys.exit(1)
