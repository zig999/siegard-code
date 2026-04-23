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

Output (exit 0):
    {"criterion": "all_domains_validated", "met": bool, "evidence": {...}}

Output (exit 1):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import os
import re
import sys
from pathlib import Path

CRITERION_ID = "all_domains_validated"

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_VALIDATION_DIR = _SPECS_DIR / "_validation"

_STATUS_RE = re.compile(r"^\s*[Ss]tatus\s*:\s*(\S+)", re.MULTILINE)


def evaluate() -> dict:
    if not _VALIDATION_DIR.exists():
        return {
            "criterion": CRITERION_ID,
            "met": False,
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
            "criterion": CRITERION_ID,
            "met": False,
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

    return {
        "criterion": CRITERION_ID,
        "met": len(failing) == 0,
        "evidence": {
            "validation_dir": str(_VALIDATION_DIR),
            "exists": True,
            "total": len(files),
            "passing": passing_count,
            "failing": failing,
        },
    }


def main() -> None:
    print(json.dumps(evaluate()))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
