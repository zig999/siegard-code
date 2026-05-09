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

Output (exit 0 when status=ok, exit 1 when status=blocked):
    {"status": "ok" | "blocked", "check": "handoff_manifest_approved",
     "timestamp": "<ISO-8601>", "evidence": {...}}
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CHECK_ID = "handoff_manifest_approved"

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_MANIFEST_FILE = _SPECS_DIR / "handoff-manifest.yaml"

# Matches: Status: approved  (key is case-insensitive, value must be "approved")
_STATUS_RE = re.compile(r"^\s*[Ss]tatus\s*:\s*(\S+)", re.MULTILINE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate() -> dict:
    if not _MANIFEST_FILE.exists():
        return {
            "status": "blocked",
            "check": CHECK_ID,
            "criterion": CHECK_ID,
            "met": False,
            "timestamp": _now_iso(),
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
        "status": "ok" if met else "blocked",
        "check": CHECK_ID,
        "criterion": CHECK_ID,
        "met": met,
        "timestamp": _now_iso(),
        "evidence": {
            "file": str(_MANIFEST_FILE),
            "exists": True,
            "status_found": status_raw,
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
