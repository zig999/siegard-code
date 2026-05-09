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


def read_verdict(path: Path) -> str:
    if not path.exists():
        return "file_not_found"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return "file_not_found"

    # Match `verdict:` at any indentation level (covers both YAML frontmatter and body).
    m = re.search(r"^\s*verdict\s*:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
    if not m:
        return "unknown"

    # Strip surrounding quotes and whitespace (handles `verdict: "approved"` or `verdict: approved`).
    raw = m.group(1).strip().strip("\"'")
    return raw if raw in VALID_VERDICTS else "unknown"


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
