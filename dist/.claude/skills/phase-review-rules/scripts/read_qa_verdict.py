#!/usr/bin/env python3
"""
read_qa_verdict.py — Read and validate QA verdict from a qa-report file.

Reads one or more QA report artifact files and extracts the `verdict` field.
Validates each verdict against the allowed enum. Files with missing or
unrecognised verdicts are reported as `unknown` (not silently dropped).

Usage:
    python3 .claude/skills/phase-review-rules/scripts/read_qa_verdict.py \
      [--project-dir <dir>] <artifact_path> [<artifact_path> ...]

Output (exit 0):
    JSON array: [{"artifact": "<path>", "verdict": "<verdict>"}, ...]
    verdict values: approved | rejected | file_not_found | unknown

Output (exit 1):
    {"status": "error", "reason": "internal_error", "detail": "<message>"}
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

VALID_VERDICTS = {"approved", "rejected"}

# SIEGARD BUG-2 — single source of truth for verdict extraction, imported by every
# review-phase gate (check_all_qa_verdicts_approved, check_micro_unanimous_clean) so
# the gates can never disagree on the same artifact (the historical drift: this
# script captured `(.+)$` while check_all captured `(\S+)`, so a bare
# `verdict: Approved with caveats` read as "unknown" here but "approved" there).
#
# Tolerant of the Markdown decoration the QA templates historically emitted:
#   verdict: approved
#   **Verdict:** Approved          (bold field name and/or bold value)
#   - **verdict**: "approved"      (bullet + bold + quotes)
# Leading [\s*\-]* absorbs bullet/bold prefixes; [\s*]* around the colon absorbs
# bold markers; the value is lower-cased before comparison. A line starting with
# `#` (YAML comment) cannot match — `#` is outside the prefix class. Any value that
# is not exactly approved/rejected (e.g. "approved with caveats") collapses to
# "unknown" — gates MUST NOT auto-pass an ambiguous verdict.
_VERDICT_RE = re.compile(
    r"^[\s*\-]*verdict[\s*]*:[\s*]*(.+?)[\s*]*$",
    re.MULTILINE | re.IGNORECASE,
)


def extract_verdict(content: str) -> str:
    """Returns the canonical verdict for a QA artifact's text.

    One of: "approved" | "rejected" | "unknown". Case-insensitive; tolerant of
    Markdown bold/bullet prefixes around the field name and the value.
    """
    m = _VERDICT_RE.search(content)
    if not m:
        return "unknown"
    raw = m.group(1).strip().strip("*").strip().strip("\"'").strip().lower()
    return raw if raw in VALID_VERDICTS else "unknown"


def read_verdict(path: Path) -> str:
    if not path.exists():
        return "file_not_found"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return "file_not_found"
    return extract_verdict(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=os.environ.get("ORCH_PROJECT_DIR", "."))
    parser.add_argument("artifacts", nargs="+")
    args = parser.parse_args()

    project_dir = Path(args.project_dir)
    results = []
    for artifact_str in args.artifacts:
        verdict = read_verdict(project_dir / artifact_str)
        results.append({"artifact": artifact_str, "verdict": verdict})

    print(json.dumps(results))


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
