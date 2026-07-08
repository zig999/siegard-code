#!/usr/bin/env python3
"""
check_error_codes_synced.py — Exit criterion: sdd / error_codes_synced.

Criterion met when:
  - Every error code (pattern: Exxx) found in an IN-SCOPE spec YAML/MD file
    under SPECS_DIR (excluding _validation/) is also present in
    SPECS_DIR/error-codes.md.
  - Trivially met if no error codes are defined in any in-scope spec file.

Scope (fix F1, same contract as check_all_domains_validated): with
--workflow-id, an `/u-improve` gates ONLY the codes referenced by the domains
the change actually touches (scope.py — derived from triage affected_specs).
An unregistered code that lives exclusively in untouched domains is a
pre-existing defect of those domains, not of this change — it is reported as
non-blocking evidence (`out_of_scope_missing`) instead of blocking the gate.
Files outside any `domains/<slug>/` directory (front specs, flows, globals)
are ALWAYS in scope — attribution is impossible, so the check stays
conservative. For u-spec / greenfield / un-derivable scope, scope.py returns
None and the check stays global (prior behavior).

Scans for patterns: "error.code: Exxx", "error_code: Exxx", "code: Exxx"

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/check_error_codes_synced.py [--workflow-id <wid>]

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
    SPECS_DIR         — specs directory, relative to ORCH_PROJECT_DIR (default: specs)

Output (exit 0 when status=ok, exit 1 when status=blocked):
    {"status": "ok" | "blocked", "check": "error_codes_synced",
     "timestamp": "<ISO-8601>", "evidence": {...}}
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scope import affected_domains, domain_of_spec_path  # noqa: E402

CHECK_ID = "error_codes_synced"

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_ERROR_CODES_FILE = _SPECS_DIR / "error-codes.md"

# Matches: error.code: E123  |  error_code: E123  |  code: E123
_SPEC_CODE_RE = re.compile(r"(?:error[._]code|code)\s*:\s*(E\d+)", re.MULTILINE)
# Matches any E-code token in error-codes.md
_REGISTERED_CODE_RE = re.compile(r"\b(E\d+)\b")


def _collect_spec_codes(scope: set[str] | None) -> tuple[set[str], set[str], list[str]]:
    """Returns (in_scope_codes, out_of_scope_codes, files_scanned).

    A code is in scope when at least one file referencing it is in scope.
    scope=None → every file is in scope (global, prior behavior). A file with
    no `domains/<slug>/` component in its path is always in scope.
    """
    in_scope_codes: set[str] = set()
    out_of_scope_codes: set[str] = set()
    files_scanned: list[str] = []

    # M12: error codes are declared in .md specs too (*.back.md, *.spec.md), not only
    # YAML. Scan both; exclude error-codes.md itself so the registry's own codes aren't
    # counted as references.
    candidates = sorted(set(_SPECS_DIR.rglob("*.yaml")) | set(_SPECS_DIR.rglob("*.md")))
    for f in candidates:
        if "_validation" in f.parts:
            continue
        if f.name == "error-codes.md":
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        found = _SPEC_CODE_RE.findall(content)
        if not found:
            continue
        rel = str(f.relative_to(_SPECS_DIR))
        files_scanned.append(rel)
        dom = domain_of_spec_path(rel)
        if scope is None or dom is None or dom in scope:
            in_scope_codes.update(found)
        else:
            out_of_scope_codes.update(found)

    # A code referenced both in and out of scope is gated (in-scope wins).
    out_of_scope_codes -= in_scope_codes
    return in_scope_codes, out_of_scope_codes, files_scanned


def _collect_registered_codes() -> set[str]:
    if not _ERROR_CODES_FILE.exists():
        return set()
    content = _ERROR_CODES_FILE.read_text(encoding="utf-8")
    return set(_REGISTERED_CODE_RE.findall(content))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evaluate(workflow_id: str | None = None) -> dict:
    scope = affected_domains(_PROJECT_DIR, workflow_id) if workflow_id else None
    spec_codes, out_of_scope_codes, files_scanned = _collect_spec_codes(scope)
    registered_codes = _collect_registered_codes()

    missing = sorted(spec_codes - registered_codes)
    # Unregistered codes living exclusively in untouched domains: surfaced for
    # audit, non-blocking — this change did not introduce them (fix F1/F3).
    out_of_scope_missing = sorted(out_of_scope_codes - registered_codes)
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
            "out_of_scope_missing": out_of_scope_missing,
            "files_scanned": files_scanned,
            "scoped": scope is not None,
            "scope_domains": sorted(scope) if scope is not None else None,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workflow-id", default=None)
    args = ap.parse_args()
    result = evaluate(args.workflow_id)
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
