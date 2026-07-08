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

CANONICAL LOGIC LIVES IN lib/spec_scope.py (single source — the dev-phase
backlog scope guard consumes the same derivation, L4). This file re-exports it
unchanged and keeps the CLI; every existing `from scope import ...` consumer
is unaffected.

Scope rules:
  - trigger != "u-improve"  → None  (u-spec / greenfield: EVERY domain is in
    scope; callers must NOT narrow — return None to signal "no scoping").
  - triage missing / unparseable → None (fail open: behave as before, global).
  - u-improve → the set of domain slugs referenced by affected_specs[].path
    (paths matching `domains/<slug>/`). Empty set (e.g. front-only change with
    no domain path) → None (conservative: do not narrow when we cannot derive).

`None` ALWAYS means "no scoping / evaluate globally" — never "empty scope".
This keeps greenfield and un-derivable cases on the exact prior behavior.

Usage (CLI, consumed by orchestrator-sdd and orchestrator-dev):
    python3 .claude/skills/phase-sdd-rules/scripts/scope.py --workflow-id <wid>
    → {"scoped": bool, "domains": [...] | null, "reason": "..."}

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
"""
import argparse
import json
import os
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))

from spec_scope import (  # noqa: E402,F401 — re-exported for existing consumers
    _DOMAIN_IN_PATH_RE,
    affected_domains,
    domain_of_spec_path,
    domain_of_validation_file,
    domains_in_text,
)


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
