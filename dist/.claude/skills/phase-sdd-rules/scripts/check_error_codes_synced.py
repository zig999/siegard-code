#!/usr/bin/env python3
"""
check_error_codes_synced.py — Exit criterion: sdd / error_codes_synced.

Criterion met when:
  - Every error code (pattern: Exxx) found in spec YAML files under SPECS_DIR
    (excluding _validation/) is also present in SPECS_DIR/error-codes.md.
  - Trivially met if no error codes are defined in any spec file.

Scans for patterns: "error.code: Exxx", "error_code: Exxx", "code: Exxx"

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/check_error_codes_synced.py

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
    SPECS_DIR         — specs directory, relative to ORCH_PROJECT_DIR (default: specs)

Output (exit 0 when status=ok, exit 1 when status=blocked):
    {"status": "ok" | "blocked", "check": "error_codes_synced",
     "timestamp": "<ISO-8601>", "evidence": {...}}
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CHECK_ID = "error_codes_synced"

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_ERROR_CODES_FILE = _SPECS_DIR / "error-codes.md"

# Matches: error.code: E123  |  error_code: E123  |  code: E123
_SPEC_CODE_RE = re.compile(r"(?:error[._]code|code)\s*:\s*(E\d+)", re.MULTILINE)
# Matches any E-code token in error-codes.md
_REGISTERED_CODE_RE = re.compile(r"\b(E\d+)\b")


def _collect_spec_codes() -> tuple[set[str], list[str]]:
    """Returns (codes_found, files_scanned)."""
    codes: set[str] = set()
    files_scanned: list[str] = []

    for f in sorted(_SPECS_DIR.rglob("*.yaml")):
        if "_validation" in f.parts:
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        found = _SPEC_CODE_RE.findall(content)
        if found:
            codes.update(found)
            files_scanned.append(str(f.relative_to(_SPECS_DIR)))

    return codes, files_scanned


def _collect_registered_codes() -> set[str]:
    if not _ERROR_CODES_FILE.exists():
        return set()
    content = _ERROR_CODES_FILE.read_text(encoding="utf-8")
    return set(_REGISTERED_CODE_RE.findall(content))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate() -> dict:
    spec_codes, files_scanned = _collect_spec_codes()
    registered_codes = _collect_registered_codes()

    missing = sorted(spec_codes - registered_codes)
    met = len(missing) == 0

    return {
        "status": "ok" if met else "blocked",
        "check": CHECK_ID,
        "criterion": CHECK_ID,
        "met": met,
        "timestamp": _now_iso(),
        "evidence": {
            "error_codes_file": str(_ERROR_CODES_FILE),
            "error_codes_file_exists": _ERROR_CODES_FILE.exists(),
            "spec_codes_found": sorted(spec_codes),
            "registered_codes_count": len(registered_codes),
            "missing_codes": missing,
            "files_scanned": files_scanned,
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
