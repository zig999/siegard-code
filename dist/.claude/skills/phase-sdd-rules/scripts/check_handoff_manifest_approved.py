#!/usr/bin/env python3
"""
check_handoff_manifest_approved.py — Exit criterion: sdd / handoff_manifest_approved.

Criterion met when:
  - SPECS_DIR/handoff-manifest.yaml exists
  - u-handoff-validator/validate.py returns status: valid (13 rules + sha256)
Approval is DERIVED, not a literal field: generate_handoff_manifest.py only writes the
manifest over VALID specs with clean compliance, so a schema-valid manifest IS the
approval. The canonical schema declares additionalProperties:false and defines no
`status` field, so a top-level `Status: approved` line cannot be both present and
schema-valid — the regex below is retained only to surface `status_found` in evidence,
never as a gate condition.
Fail-closed: a missing manifest, validator error, or any blocking rule keeps it unmet.

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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CHECK_ID = "handoff_manifest_approved"

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")
_MANIFEST_FILE = _SPECS_DIR / "handoff-manifest.yaml"

# prod-hardening task 04 (C3/A3-F2): the gate now invokes the real semantic
# validator instead of trusting a shallow `Status: approved` regex.
_VALIDATE = Path(__file__).resolve().parents[2] / "u-handoff-validator" / "validate.py"

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
    status_approved = (status_raw or "").lower() == "approved"

    # Run the deterministic semantic validator (13 rules + sha256). Fail-closed:
    # any invocation error or unparseable output leaves validator_status unset,
    # which keeps met False.
    validator_status = None
    validator_errors: list = []
    try:
        proc = subprocess.run(
            [sys.executable, str(_VALIDATE),
             "--manifest", str(_MANIFEST_FILE),
             "--specs-dir", str(_PROJECT_DIR),
             "--caller", "u-spec-orchestrator"],
            capture_output=True, text=True,
        )
        env = json.loads(proc.stdout or "{}")
        validator_status = env.get("status")
        validator_errors = env.get("errors", []) or []
    except Exception as exc:  # noqa: BLE001 — fail-closed
        validator_status = "error"
        validator_errors = [f"validator_invocation_failed: {exc}"]

    # Approval is derived from the semantic validator alone (see module docstring).
    # status_approved is kept in evidence for traceability but is NOT a gate condition.
    met = validator_status == "valid"

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
            "status_approved": status_approved,
            "validator_status": validator_status,
            "validator_errors": validator_errors[:10],
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
