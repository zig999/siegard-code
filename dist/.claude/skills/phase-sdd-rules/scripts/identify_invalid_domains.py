#!/usr/bin/env python3
"""
identify_invalid_domains.py — SDD repair loop Step R2: INVALID domains + defect origin.

Scans {SPECS_DIR}/_validation/ for domains whose validation report is INVALID
(same `status: INVALID` match the inline R2 check used) and, for each, derives
the defect origin from the machine-readable companion file
{domain}-validation-result.yaml (validation-result.schema.yaml): every
blocking issue carries a `responsible` field in {u-spec-back, u-spec-front,
u-spec-writer}.

Origin mapping (conservative — feeds the SM's stage-granular repair):
    all blocking issues responsible == u-spec-back  -> "back"
    anything else (mixed, front, writer, no yaml, unparseable, no issues)
                                                    -> null (full pipeline)

Scope (fix F1, same contract as check_all_domains_validated): with
--workflow-id, an `/u-improve` restricts the repair-target set to the domains
the change actually touches (scope.py — derived from triage affected_specs).
A stale INVALID report in an untouched domain must not pull that domain into
this workflow's repair dispatch — the scoped gate already treats it as
non-blocking, so repairing it here would be pure out-of-scope work
(orchestrator-sdd R3: "repair scope is exactly the evidence in the validation
reports, never the neighboring domain"). Out-of-scope INVALID domains are
reported as non-blocking evidence (`out_of_scope_invalid`). For u-spec /
greenfield / un-derivable scope, scope.py returns None and the scan stays
global (prior behavior).

Replaces the prompt-inlined R2 python in orchestrator-sdd.md (P11 — exit
criteria in testable code, not in prompts). The YAML subset is extracted with
line regexes (stdlib only, no PyYAML): `warnings` items have no `responsible`
key per schema, so every `responsible:` line in the file belongs to a blocking
issue.

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/identify_invalid_domains.py [--workflow-id <wid>]

Environment:
    ORCH_PROJECT_DIR   — project root (default: ".")
    SPECS_DIR          — specs directory relative to project root (default: "specs")

Output (single JSON line, exit 0):
    {"invalid_domains": ["chat", ...], "defect_origins": {"chat": "back", "ingestion": null},
     "out_of_scope_invalid": [...], "scoped": bool}
Exit 1 on unexpected internal error only ({"status": "error", ...}).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scope import affected_domains  # noqa: E402

_STATUS_INVALID_RE = re.compile(r"status:\s*INVALID", re.IGNORECASE)
_RESPONSIBLE_RE = re.compile(r"^\s*responsible:\s*['\"]?([\w-]+)['\"]?\s*$", re.MULTILINE)


def _defect_origin(result_yaml: Path) -> str | None:
    """Derive the repair origin for one domain from its validation-result.yaml.

    Returns "back" only in the unambiguous all-blocking-issues-are-back case;
    None otherwise (including read/parse failures — fall back to full repair).
    """
    try:
        text = result_yaml.read_text(encoding="utf-8")
    except OSError:
        return None
    if not _STATUS_INVALID_RE.search(text):
        # Companion says VALID (or has no status) while the .md report says
        # INVALID — contradictory evidence, do not reduce the pipeline.
        return None
    responsibles = set(_RESPONSIBLE_RE.findall(text))
    if responsibles == {"u-spec-back"}:
        return "back"
    return None


def evaluate(workflow_id: str | None = None) -> dict:
    project_dir = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
    specs_dir = os.environ.get("SPECS_DIR", "specs")
    val_dir = project_dir / specs_dir / "_validation"
    scope = affected_domains(project_dir, workflow_id) if workflow_id else None

    invalid: list[str] = []
    origins: dict[str, str | None] = {}
    out_of_scope: list[str] = []
    if val_dir.exists():
        for report in sorted(val_dir.glob("*-validation.md")):
            try:
                content = report.read_text(encoding="utf-8")
            except OSError:
                continue
            if not _STATUS_INVALID_RE.search(content):
                continue
            domain = report.stem.replace("-validation", "")
            # Untouched domains inherit their last verdict — never re-dispatched
            # by this workflow's repair loop (fix F1/F3). scope=None → global.
            if scope is not None and domain not in scope:
                out_of_scope.append(domain)
                continue
            invalid.append(domain)
            origins[domain] = _defect_origin(
                val_dir / f"{domain}-validation-result.yaml"
            )
    return {
        "invalid_domains": invalid,
        "defect_origins": origins,
        "out_of_scope_invalid": out_of_scope,
        "scoped": scope is not None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="INVALID domains + defect origin (stdlib only).")
    ap.add_argument("--workflow-id", default=None)
    args = ap.parse_args()
    print(json.dumps(evaluate(args.workflow_id)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        sys.exit(1)
