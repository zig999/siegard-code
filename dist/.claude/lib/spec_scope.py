#!/usr/bin/env python3
"""spec_scope.py — canonical change-scope derivation (fix F1 / L4).

Single source of truth for "which domains does this change touch", shared by:
  - phase-sdd-rules (dispatch, exit gates, repair targets — via scope.py,
    which re-exports this module and adds the CLI)
  - phase-dev-rules (check_backlog_scope.py — the post-planner guard that
    rejects Task Contracts referencing domains outside the change scope)

Scope rules (unchanged from the original scope.py, v2.4.0):
  - trigger != "u-improve"  → None  (u-spec / greenfield: EVERY domain is in
    scope; callers must NOT narrow — None signals "no scoping").
  - triage missing / unparseable → None (fail open: behave as before, global).
  - u-improve → the set of domain slugs referenced by affected_specs[].path
    (paths matching `domains/<slug>/`). Empty set → None (conservative: do
    not narrow when we cannot derive).

`None` ALWAYS means "no scoping / evaluate globally" — never "empty scope".
"""
import json
import re
from pathlib import Path

# Matches the domain slug in a spec path, e.g. "specs/domains/ifs-integration/openapi.yaml".
# EXACTLY the v2.4.0 scope.py pattern — this module replaces it as the single
# source; any charset change here would silently shift gate semantics.
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


def domains_in_text(text: str) -> set[str]:
    """Every domain slug referenced anywhere in a text blob.

    Used by the backlog scope guard: a Task Contract file cites its spec
    inputs as `.../domains/<slug>/...` paths — this collects them all,
    format-agnostically.
    """
    return set(_DOMAIN_IN_PATH_RE.findall(text))


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
