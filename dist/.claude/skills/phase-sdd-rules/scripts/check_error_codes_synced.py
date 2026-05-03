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

Output (exit 0):
    {"criterion": "error_codes_synced", "met": bool, "evidence": {...}}

Output (exit 1):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import json
import os
import re
import sys
from pathlib import Path

CRITERION_ID = "error_codes_synced"

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


def evaluate() -> dict:
    spec_codes, files_scanned = _collect_spec_codes()
    registered_codes = _collect_registered_codes()

    missing = sorted(spec_codes - registered_codes)
    met = len(missing) == 0

    return {
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": {
            "error_codes_file": str(_ERROR_CODES_FILE),
            "error_codes_file_exists": _ERROR_CODES_FILE.exists(),
            "spec_codes_found": sorted(spec_codes),
            "registered_codes_count": len(registered_codes),
            "missing_codes": missing,
            "files_scanned": files_scanned,
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
