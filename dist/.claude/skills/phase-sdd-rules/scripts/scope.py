#!/usr/bin/env python3
"""
scope.py — derive the set of domains a change actually touches (fix F1).

An `/u-improve` that modifies one domain's contract is classified `full` (a
breaking change legitimately needs the full spec pipeline), which runs in
`standard` mode. Standard mode used to treat EVERY on-disk domain as `new` and
re-run writer→reviewer→back→validator for all of them, and the exit gate
(check_all_domains_validated) + the handoff scan (generate_handoff_manifest)
required EVERY domain VALID — so a one-domain change cascaded across the whole
project (~60% wasted worker-tasks) and a stale INVALID/handoff_allowed:false in
an untouched domain blocked an unrelated change (the F3 symptom).

This module answers one question deterministically: which domains are in the
change scope? Callers (the orchestrator dispatch, the gate, the manifest scan)
restrict their work to that set. Untouched domains inherit their last recorded
verdict — they are neither re-dispatched nor re-gated.

Scope rules:
  - trigger != "u-improve"  → None  (u-spec / greenfield: EVERY domain is in
    scope; callers must NOT narrow — return None to signal "no scoping").
  - triage missing / unparseable → None (fail open: behave as before, global).
  - u-improve → the set of domain slugs referenced by affected_specs[].path
    (paths matching `domains/<slug>/`). Empty set (e.g. front-only change with
    no domain path) → None (conservative: do not narrow when we cannot derive).

`None` ALWAYS means "no scoping / evaluate globally" — never "empty scope".
This keeps greenfield and un-derivable cases on the exact prior behavior.

Usage (CLI, consumed by orchestrator-sdd):
    python3 .claude/skills/phase-sdd-rules/scripts/scope.py --workflow-id <wid>
    → {"scoped": bool, "domains": [...] | null, "reason": "..."}

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

# Matches the domain slug in a spec path, e.g. "specs/domains/ifs-integration/openapi.yaml".
_DOMAIN_IN_PATH_RE = re.compile(r"(?:^|/)domains/([^/]+)/")


def _read_triage(project_dir: Path, workflow_id: str) -> dict | None:
    triage_path = project_dir / ".orch" / "sessions" / workflow_id / "triage.json"
    if not triage_path.exists():
        return None
    try:
        return json.loads(triage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def affected_domains(project_dir: Path, workflow_id: str) -> set[str] | None:
    """Domains in the change scope, or None to signal 'no scoping (evaluate all)'."""
    triage = _read_triage(project_dir, workflow_id)
    if triage is None:
        return None
    if triage.get("trigger") != "u-improve":
        return None  # u-spec / greenfield — every domain is in scope
    domains: set[str] = set()
    for spec in triage.get("affected_specs", []):
        path = spec.get("path") or ""
        m = _DOMAIN_IN_PATH_RE.search(path)
        if m:
            domains.add(m.group(1))
    return domains or None  # empty → conservative global (do not narrow)


def domain_of_spec_path(path: str) -> str | None:
    """Extract the domain slug from a spec file path (`.../domains/<slug>/...`).

    Returns None for paths outside a domain directory (front specs, flows,
    globals) — callers treat those as always in scope (cannot narrow).
    """
    m = _DOMAIN_IN_PATH_RE.search(path)
    return m.group(1) if m else None


def domain_of_validation_file(filename: str) -> str | None:
    """Extract the domain slug from a `_validation/` artifact filename.

    Recognized: `<domain>-validation-result.yaml`, `<domain>-validation.md`,
    `<domain>-compliance.yaml`. Returns None for files with no domain prefix.
    """
    for suffix in ("-validation-result.yaml", "-validation.md", "-compliance.yaml"):
        if filename.endswith(suffix):
            stem = filename[: -len(suffix)]
            return stem or None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Derive change scope (stdlib only).")
    ap.add_argument("--workflow-id", required=True)
    args = ap.parse_args()
    project_dir = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
    scope = affected_domains(project_dir, args.workflow_id)
    if scope is None:
        print(json.dumps({"scoped": False, "domains": None,
                          "reason": "no_scoping_evaluate_all"}))
    else:
        print(json.dumps({"scoped": True, "domains": sorted(scope),
                          "reason": "u_improve_affected_domains"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
