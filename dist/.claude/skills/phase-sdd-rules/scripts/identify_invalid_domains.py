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

Replaces the prompt-inlined R2 python in orchestrator-sdd.md (P11 — exit
criteria in testable code, not in prompts). The YAML subset is extracted with
line regexes (stdlib only, no PyYAML): `warnings` items have no `responsible`
key per schema, so every `responsible:` line in the file belongs to a blocking
issue.

Environment:
    ORCH_PROJECT_DIR   — project root (default: ".")
    SPECS_DIR          — specs directory relative to project root (default: "specs")

Output (single JSON line, exit 0):
    {"invalid_domains": ["chat", ...], "defect_origins": {"chat": "back", "ingestion": null}}
Exit 1 on unexpected internal error only ({"status": "error", ...}).
"""
import json
import os
import re
import sys
from pathlib import Path

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


def evaluate() -> dict:
    project_dir = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
    specs_dir = os.environ.get("SPECS_DIR", "specs")
    val_dir = project_dir / specs_dir / "_validation"

    invalid: list[str] = []
    origins: dict[str, str | None] = {}
    if val_dir.exists():
        for report in sorted(val_dir.glob("*-validation.md")):
            try:
                content = report.read_text(encoding="utf-8")
            except OSError:
                continue
            if not _STATUS_INVALID_RE.search(content):
                continue
            domain = report.stem.replace("-validation", "")
            invalid.append(domain)
            origins[domain] = _defect_origin(
                val_dir / f"{domain}-validation-result.yaml"
            )
    return {"invalid_domains": invalid, "defect_origins": origins}


def main() -> int:
    print(json.dumps(evaluate()))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        sys.exit(1)
