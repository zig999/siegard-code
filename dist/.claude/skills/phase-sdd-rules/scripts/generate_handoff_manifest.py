#!/usr/bin/env python3
"""
generate_handoff_manifest.py — produces SPECS_DIR/handoff-manifest.yaml (fix F1).

The SDD exit gate (check_handoff_manifest_approved.py) requires an approved,
schema-valid handoff-manifest.yaml, but no pipeline worker produced one — the
phase dead-ended at E08. This script closes that gap: it deterministically
assembles the manifest from the validated specs on disk plus triage.json, so
orchestrator-sdd can self-complete the phase.

Deterministic by design (not an LLM worker): sha256 must be exact, delivered_by
is a const, and the output must round-trip through the stdlib minimal_yaml loader
that validate.py uses. The manifest is a pure function of on-disk artifacts.

Run order (orchestrator-sdd Step 6): invoked only AFTER all_domains_validated and
error_codes_synced pass, and BEFORE check_handoff_manifest_approved.py.

Usage:
    python3 .claude/skills/phase-sdd-rules/scripts/generate_handoff_manifest.py \
      --workflow-id <wid>

Environment:
    ORCH_PROJECT_DIR  — project root (default: .)
    SPECS_DIR         — specs directory, relative to ORCH_PROJECT_DIR (default: specs)

Output (exit 0 when status=ok, exit 1 when status=blocked):
    {"status": "ok" | "blocked", "check": "handoff_manifest_generated",
     "manifest_path": "...", "manifest_id": "...", "domains": [...],
     "stack_implied": "be|fe|fullstack", "reason": "..."}

Fail-closed: any irresolvable input, a compliance/validation block signal, or a
triage stack/front mismatch (declared fullstack|fe but no front artifacts, fix
P0-1) yields status=blocked WITHOUT writing an approved manifest.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scope import affected_domains, domain_of_validation_file  # noqa: E402

CHECK_ID = "handoff_manifest_generated"

_SEMVER_RE = re.compile(r"([0-9]+\.[0-9]+\.[0-9]+)")
_VERSION_HINT_RE = re.compile(r"[Vv]ersion[^0-9]{0,12}([0-9]+\.[0-9]+\.[0-9]+)")
_HANDOFF_ALLOWED_FALSE_RE = re.compile(r"handoff_allowed\s*:\s*false", re.IGNORECASE)
_COMPLIANCE_BLOCK_RE = re.compile(
    r"verdict\s*:\s*non_compliant|action\s*:\s*block_handoff", re.IGNORECASE
)

_DEFAULT_VERSION = "1.0.0"
_PASS_MSG = "Validation passed. No blocking issues."


# --------------------------------------------------------------------------- #
# Block-style YAML emitter (minimal_yaml is block-only — no flow collections). #
# --------------------------------------------------------------------------- #
def _scalar(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, int):
        return str(v)
    s = str(v)
    # Quote when a bare scalar would confuse the partition(":") / sequence parser,
    # or when minimal_yaml._coerce would change its type (pure-int, bool/null lookalikes).
    needs_quote = (
        s == ""
        or ":" in s or "#" in s
        or s != s.strip()
        or s[0] in "-?[]{}&*!|>%@`\"'"
        or re.fullmatch(r"-?\d+", s) is not None
        or s.lower() in ("true", "false", "null", "~")
    )
    if needs_quote:
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _dump(obj, indent: int = 0) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                lines.append(f"{pad}{k}:")
                lines.extend(_dump(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{pad}{k}: []")
                else:
                    lines.append(f"{pad}{k}:")
                    lines.extend(_dump(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_scalar(v)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                entries = list(item.items())
                first_k, first_v = entries[0]
                # Sequence items here only ever hold scalar values.
                lines.append(f"{pad}- {first_k}: {_scalar(first_v)}")
                for k, v in entries[1:]:
                    lines.append(f"{pad}  {k}: {_scalar(v)}")
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    return lines


def _to_yaml(manifest: dict) -> str:
    return "\n".join(_dump(manifest)) + "\n"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path, project_dir: Path) -> str:
    return path.resolve().relative_to(project_dir.resolve()).as_posix()


def _read_triage(project_dir: Path, workflow_id: str) -> tuple[dict, str]:
    triage_path = project_dir / ".orch" / "sessions" / workflow_id / "triage.json"
    if not triage_path.exists():
        return {}, "triage_missing_default_new_domain"
    try:
        return json.loads(triage_path.read_text(encoding="utf-8")), "triage_loaded"
    except (json.JSONDecodeError, OSError):
        return {}, "triage_unparseable_default_new_domain"


def _openapi_version(text: str) -> str:
    """info.version from an OpenAPI doc; first `version:` under the `info:` block."""
    under_info = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^info\s*:", stripped):
            under_info = True
            continue
        if under_info:
            if line and not line[0].isspace() and not stripped.startswith("#"):
                under_info = False  # left the info block
            m = re.match(r"version\s*:\s*['\"]?([0-9]+\.[0-9]+\.[0-9]+)", stripped)
            if m:
                return m.group(1)
    return _DEFAULT_VERSION


def _md_version(text: str) -> str:
    m = _VERSION_HINT_RE.search(text)
    if m:
        return m.group(1)
    m = _SEMVER_RE.search(text)
    return m.group(1) if m else _DEFAULT_VERSION


def _handoff_type(triage: dict) -> str:
    trigger = triage.get("trigger", "u-spec")
    mode_hint = triage.get("mode_hint", "full")
    if trigger == "u-improve":
        return "major_evolution" if mode_hint == "full" else "fast_track"
    return "new_domain"


def _change_summary(triage: dict, htype: str) -> dict:
    mode_hint = triage.get("mode_hint", "")
    if htype == "major_evolution":
        cs_type = "major"
    else:  # fast_track
        cs_type = "minor" if mode_hint.endswith("minor") else "patch"
    changed = [s.get("path") for s in triage.get("affected_specs", []) if s.get("path")]
    return {
        "type": cs_type,
        "cr": "none",
        "changed_files": changed or ["unknown"],
        "dev_impact": "reevaluate_task_contracts",
    }


def _in_scope(filename: str, scope: set[str] | None) -> bool:
    """A file is in scope when scope is None (global), the file has no domain
    prefix, or its domain is in the change scope (fix F1/F3)."""
    if scope is None:
        return True
    dom = domain_of_validation_file(filename)
    return dom is None or dom in scope


def _approval_blocked(validation_dir: Path, scope: set[str] | None = None) -> list[str]:
    """Fail-closed scan for explicit block signals from validation/compliance.

    Scoped (fix F1/F3): on an `/u-improve`, only the domains the change touches
    can block the handoff. A stale handoff_allowed:false or a non_compliant
    verdict left in an untouched domain no longer blocks an unrelated change.
    """
    reasons: list[str] = []
    if not validation_dir.exists():
        return reasons
    for f in sorted(validation_dir.glob("*-validation-result.yaml")):
        if not _in_scope(f.name, scope):
            continue
        try:
            if _HANDOFF_ALLOWED_FALSE_RE.search(f.read_text(encoding="utf-8")):
                reasons.append(f"{f.name}: handoff_allowed=false")
        except OSError:
            continue
    for f in sorted(validation_dir.glob("*-compliance.yaml")):
        if not _in_scope(f.name, scope):
            continue
        try:
            if _COMPLIANCE_BLOCK_RE.search(f.read_text(encoding="utf-8")):
                reasons.append(f"{f.name}: compliance block_handoff/non_compliant")
        except OSError:
            continue
    return reasons


def _backend_package(domain_dir: Path, project_dir: Path, specs_dir: Path) -> list[dict]:
    """Per-domain openapi + back-spec (required by FLOW-037); shared catalogs optional."""
    pkg: list[dict] = []
    openapi = domain_dir / "openapi.yaml"
    if openapi.exists():
        pkg.append({"path": _rel(openapi, project_dir), "artifact": "openapi",
                    "sha256": _sha256(openapi)})
    domain = domain_dir.name
    back = domain_dir / "back" / f"{domain}.back.md"
    if back.exists():
        pkg.append({"path": _rel(back, project_dir), "artifact": "back-spec",
                    "sha256": _sha256(back)})
    return pkg


def _shared_backend_entries(specs_dir: Path, project_dir: Path) -> list[dict]:
    entries: list[dict] = []
    error_codes = specs_dir / "error-codes.md"
    if error_codes.exists():
        entries.append({"path": _rel(error_codes, project_dir), "artifact": "error-codes",
                        "sha256": _sha256(error_codes)})
    for conv in (specs_dir / "_global" / "conventions.md", specs_dir / "conventions.md"):
        if conv.exists():
            entries.append({"path": _rel(conv, project_dir), "artifact": "conventions",
                            "sha256": _sha256(conv)})
            break
    return entries


def _frontend(specs_dir: Path, project_dir: Path) -> tuple[dict | None, list[dict]]:
    front_md = specs_dir / "front" / "front.md"
    if not front_md.exists():
        return None, []
    features_dir = specs_dir / "front" / "features"
    flows_dir = specs_dir / "front" / "_flows"
    components_dir = specs_dir / "front" / "components"

    feature_files = sorted(features_dir.glob("*.feature.spec.md")) if features_dir.exists() else []
    flow_files = sorted(flows_dir.glob("*.flow.md")) if flows_dir.exists() else []
    component_files = sorted(components_dir.glob("*.component.spec.md")) if components_dir.exists() else []

    artifacts = {
        "front_md_version": _md_version(front_md.read_text(encoding="utf-8")),
        "features": [{"name": f.name[: -len(".feature.spec.md")],
                      "path": _rel(f, project_dir)} for f in feature_files],
        "flows": [{"name": f.name[: -len(".flow.md")],
                   "path": _rel(f, project_dir)} for f in flow_files],
    }

    package = [{"path": _rel(front_md, project_dir), "artifact": "front",
                "sha256": _sha256(front_md)}]
    for f in feature_files:
        package.append({"path": _rel(f, project_dir), "artifact": "feature-spec",
                        "sha256": _sha256(f)})
    for f in component_files:
        package.append({"path": _rel(f, project_dir), "artifact": "component-spec",
                        "sha256": _sha256(f)})
    for f in flow_files:
        package.append({"path": _rel(f, project_dir), "artifact": "flow",
                        "sha256": _sha256(f)})
    return artifacts, package


def _blocked(reason: str, **extra) -> dict:
    return {"status": "blocked", "check": CHECK_ID, "reason": reason, **extra}


def generate(project_dir: Path, specs_dir: Path, workflow_id: str) -> dict:
    domain_dirs = sorted(p.parent for p in specs_dir.glob("domains/*/openapi.yaml"))
    if not domain_dirs:
        return _blocked("no_domains_found", manifest_path=None)

    scope = affected_domains(project_dir, workflow_id)
    block_reasons = _approval_blocked(specs_dir / "_validation", scope)
    if block_reasons:
        return _blocked("approval_blocked", detail=block_reasons, manifest_path=None)

    triage, triage_reason = _read_triage(project_dir, workflow_id)
    htype = _handoff_type(triage)

    domains: list[dict] = []
    backend_package: list[dict] = []
    for d in domain_dirs:
        name = d.name
        openapi = d / "openapi.yaml"
        spec_md = d / f"{name}.spec.md"
        back_md = d / "back" / f"{name}.back.md"
        report = specs_dir / "_validation" / f"{name}-validation.md"
        domains.append({
            "name": name,
            "spec_version": _md_version(spec_md.read_text(encoding="utf-8")) if spec_md.exists() else _DEFAULT_VERSION,
            "back_version": _md_version(back_md.read_text(encoding="utf-8")) if back_md.exists() else _DEFAULT_VERSION,
            "openapi_version": _openapi_version(openapi.read_text(encoding="utf-8")) if openapi.exists() else _DEFAULT_VERSION,
            "compliance_report": _rel(report, project_dir) if report.exists() else _PASS_MSG,
        })
        backend_package.extend(_backend_package(d, project_dir, specs_dir))

    backend_package.extend(_shared_backend_entries(specs_dir, project_dir))

    # FLOW-037: new_domain/major_evolution require openapi + back-spec present.
    present_artifacts = {p["artifact"] for p in backend_package}
    if htype in ("new_domain", "major_evolution"):
        for required in ("openapi", "back-spec"):
            if required not in present_artifacts:
                return _blocked(f"missing_required_backend_artifact:{required}", manifest_path=None)

    frontend_artifacts, frontend_package = _frontend(specs_dir, project_dir)

    # P0-1 guard: if triage declared a front-bearing stack (fullstack|fe) but no
    # front artifacts exist, the front leg was wrongly skipped or silently failed.
    # Fail closed instead of emitting a back-only manifest that hides the gap —
    # this is the downstream half of the fix; the triage classifier is the upstream
    # half. Legacy triage without a `stack` field is exempt (declared_stack None).
    declared_stack = triage.get("stack")
    if declared_stack in ("fullstack", "fe") and frontend_artifacts is None:
        return _blocked("stack_mismatch_front_expected_but_missing",
                        detail={"declared_stack": declared_stack},
                        manifest_path=None)

    now = datetime.now(timezone.utc)
    manifest: dict = {
        "handoff": {
            "id": now.strftime("HANDOFF-%Y%m%d-%H%M%S"),
            "delivered_by": "u-spec-orchestrator",  # const required by FLOW-030
            "delivered_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "layer": "semi-permanent",
            "type": htype,
        },
        "domains": domains,
        "backend_package": backend_package,
    }
    if frontend_artifacts is not None:
        manifest["frontend_artifacts"] = frontend_artifacts
        manifest["frontend_package"] = frontend_package
    if htype != "new_domain":
        manifest["change_summary"] = _change_summary(triage, htype)

    stack_implied = "fullstack" if frontend_package else "be"

    manifest_path = specs_dir / "handoff-manifest.yaml"
    manifest_path.write_text(_to_yaml(manifest), encoding="utf-8")

    return {
        "status": "ok",
        "check": CHECK_ID,
        "manifest_path": str(manifest_path),
        "manifest_id": manifest["handoff"]["id"],
        "domains": [d["name"] for d in domains],
        "stack_implied": stack_implied,
        "reason": triage_reason,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate handoff-manifest.yaml (stdlib only).")
    ap.add_argument("--workflow-id", required=True)
    args = ap.parse_args()

    project_dir = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
    specs_dir = project_dir / os.environ.get("SPECS_DIR", "specs")

    result = generate(project_dir, specs_dir, args.workflow_id)
    print(json.dumps(result))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — fail-closed
        print(json.dumps({"status": "blocked", "check": CHECK_ID,
                          "reason": "internal_error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
