#!/usr/bin/env python3
"""
check_structural_diff.py — Determine if a spec change requires a domain worker.

Reads changed_sections from triage.json (written by u-spec-triage) for a given spec path.
Outputs: {"domain_worker_required": bool, "changed_sections": [...], "structural_sections_found": [...]}

Safe fallback: if triage file is missing or spec is not found, returns domain_worker_required: true
to avoid skipping required work.

Usage:
    ORCH_PROJECT_DIR=<path> python3 check_structural_diff.py \
        --workflow-id <wid> --spec-path <path>
"""
import json
import os
import sys
import argparse
from pathlib import Path

STRUCTURAL = {
    "endpoints", "schemas", "error_codes", "component_props",
    "state_contracts", "data_models", "auth_rules", "event_types", "api_contracts"
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--workflow-id", required=True)
    p.add_argument("--spec-path", required=True)
    args = p.parse_args()

    project_dir = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
    triage_path = project_dir / ".orch" / "sessions" / args.workflow_id / "triage.json"

    if not triage_path.exists():
        print(json.dumps({
            "domain_worker_required": True,
            "changed_sections": [],
            "structural_sections_found": [],
            "reason": "triage_file_not_found",
        }))
        return

    try:
        triage = json.loads(triage_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({
            "domain_worker_required": True,
            "changed_sections": [],
            "structural_sections_found": [],
            "reason": f"triage_file_invalid: {exc}",
        }))
        return

    spec_entry = next(
        (s for s in triage.get("affected_specs", []) if s.get("path") == args.spec_path),
        None,
    )

    if spec_entry is None:
        print(json.dumps({
            "domain_worker_required": True,
            "changed_sections": [],
            "structural_sections_found": [],
            "reason": "spec_not_in_triage",
        }))
        return

    # Prefer changed_sections (new field); fall back to sections (legacy §N notation).
    # §N values will not match STRUCTURAL labels → domain_worker_required: false (conservative for legacy).
    changed = set(spec_entry.get("changed_sections", spec_entry.get("sections", [])))
    structural_hit = bool(changed & STRUCTURAL)

    print(json.dumps({
        "domain_worker_required": structural_hit,
        "changed_sections": sorted(changed),
        "structural_sections_found": sorted(changed & STRUCTURAL),
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "domain_worker_required": True,
            "changed_sections": [],
            "structural_sections_found": [],
            "reason": f"internal_error: {exc}",
        }))
        sys.exit(1)
