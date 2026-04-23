#!/usr/bin/env python3
"""
check_handoff_manifest_approved.py — Exit criterion: sdd / handoff_manifest_approved.

Criterion met when:
  - SPECS_DIR/handoff-manifest.yaml exists
  - File contains a line matching Status: approved (case-insensitive value)

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/check_handoff_manifest_approved.py

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
    SPECS_DIR         — specs directory, relative to ORCH_PROJECT_DIR (default: specs)

Output (exit 0):
    {"criterion": "handoff_manifest_approved", "met": bool, "evidence": {...}}

Output (exit 1):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import os
import re
import sys
from pathlib import Path

CRITERION_ID = "handoff_manifest_approved"

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_MANIFEST_FILE = _SPECS_DIR / "handoff-manifest.yaml"

# Matches: Status: approved  (key is case-insensitive, value must be "approved")
_STATUS_RE = re.compile(r"^\s*[Ss]tatus\s*:\s*(\S+)", re.MULTILINE)


def evaluate() -> dict:
    if not _MANIFEST_FILE.exists():
        return {
            "criterion": CRITERION_ID,
            "met": False,
            "evidence": {
                "file": str(_MANIFEST_FILE),
                "exists": False,
                "status_found": None,
            },
        }

    content = _MANIFEST_FILE.read_text(encoding="utf-8")
    match = _STATUS_RE.search(content)
    status_raw = match.group(1) if match else None
    met = (status_raw or "").lower() == "approved"

    return {
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "file": str(_MANIFEST_FILE),
            "exists": True,
            "status_found": status_raw,
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
