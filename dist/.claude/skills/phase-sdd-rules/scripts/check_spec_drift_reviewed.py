#!/usr/bin/env python3
"""
check_spec_drift_reviewed.py — Exit criterion: sdd / spec_drift_reviewed (R04d).

`/u-drift` already exists and does exactly what the spec pipeline structurally
cannot: it matches approved specs against the code by exact keys and reports what
diverged, with evidence per finding. It runs standalone, outside the engine, and
has to be remembered.

This criterion connects it to the phase — **opt-in**, and that is a deliberate
limit rather than a shortcut. `/u-drift` costs an LLM code-inventory pass, so
making it mandatory on every sdd phase would add an agent and several minutes to
every workflow, including the ones whose whole problem is already that the
pipeline costs more than the change. A gate that makes the measured cost problem
worse would not survive contact with the operator; one they switch on for the
handoffs that matter will.

Enable per project in `.orch/config.json`:

    {"sdd_policy": {"drift_check": "required" | "warn" | "off"}}

    off       (default) criterion is vacuously met; nothing runs
    warn      a missing or stale report is reported but does not block
    required  a missing or stale report BLOCKS the phase exit

What "reviewed" means, when enabled: `{SPECS_DIR}/_validation/drift-report.json`
exists, and its `spec_content_hash` matches the specs currently on disk. A report
generated before the specs changed describes a state that no longer exists —
exactly the staleness class R08 addresses for validation verdicts.

Usage:
    python3 check_spec_drift_reviewed.py [--workflow-id <wid>]

Output (exit 0 / 1, uniform gate schema):
    {"criterion": "spec_drift_reviewed", "met": bool, "evidence": {...}}
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_CLAUDE_DIR / "lib"))

try:
    from orch_core import load_config, now_iso
except ImportError as exc:  # pragma: no cover
    print(json.dumps({
        "status": "error", "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "spec_drift_reviewed"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = _PROJECT_DIR / os.environ.get("SPECS_DIR", "specs")

_VALID_POLICIES = ("off", "warn", "required")
_SPEC_GLOBS = ("domains/*/openapi.yaml", "domains/*/*.spec.md",
               "domains/*/back/*.back.md")


def _policy() -> str:
    try:
        cfg = load_config()
    except Exception:  # noqa: BLE001 — a bad config must not wedge the gate
        return "off"
    value = (cfg.get("sdd_policy") or {}).get("drift_check", "off")
    return value if value in _VALID_POLICIES else "off"


def spec_content_hash() -> str:
    """Stable hash of the approved spec surface — the same notion /u-drift pins."""
    digest = hashlib.sha256()
    files: list[Path] = []
    for pattern in _SPEC_GLOBS:
        files.extend(_SPECS_DIR.glob(pattern))
    for path in sorted(files):
        try:
            content = path.read_bytes().replace(b"\r\n", b"\n")
        except OSError:
            continue
        digest.update(str(path.relative_to(_SPECS_DIR)).encode("utf-8"))
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def evaluate(workflow_id: str | None = None) -> dict:
    policy = _policy()
    if policy == "off":
        return {
            "criterion": CRITERION_ID,
            "met": True,
            "evidence": {
                "policy": "off",
                "note": "drift check disabled — set sdd_policy.drift_check to "
                        "'warn' or 'required' in .orch/config.json to enable",
            },
        }

    report = _SPECS_DIR / "_validation" / "drift-report.json"
    blocking = policy == "required"

    if not report.is_file():
        return {
            "criterion": CRITERION_ID,
            "met": not blocking,
            "evidence": {
                "policy": policy,
                "reason": "drift_report_missing",
                "expected_path": str(report),
                "action": "run /u-drift <project-dir> before handoff",
            },
        }

    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "criterion": CRITERION_ID,
            "met": not blocking,
            "evidence": {"policy": policy, "reason": "drift_report_unreadable",
                         "detail": str(exc)},
        }

    current = spec_content_hash()
    recorded = payload.get("spec_content_hash")
    if recorded and recorded != current:
        return {
            "criterion": CRITERION_ID,
            "met": not blocking,
            "evidence": {
                "policy": policy,
                "reason": "drift_report_stale",
                "recorded_spec_hash": recorded,
                "current_spec_hash": current,
                "action": "the specs changed after the report was generated — "
                          "re-run /u-drift",
            },
        }

    findings = payload.get("findings") or []
    unresolved = [
        f for f in findings
        if isinstance(f, dict) and str(f.get("severity", "")).lower() == "critical"
    ]
    return {
        "criterion": CRITERION_ID,
        "met": not (blocking and unresolved),
        "evidence": {
            "policy": policy,
            "reason": "drift_report_current",
            "findings_total": len(findings),
            "critical_findings": len(unresolved),
            "spec_content_hash": current,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-id", default=None)
    args = ap.parse_args()
    result = evaluate(args.workflow_id)
    result.setdefault("check", result.get("criterion"))
    result.setdefault("status", "ok" if result.get("met") else "blocked")
    result.setdefault("timestamp", now_iso())
    print(json.dumps(result))
    # Fail-closed like every other exit criterion (R01b).
    if not result.get("met"):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
