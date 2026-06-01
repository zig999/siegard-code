#!/usr/bin/env python3
"""Deterministic handoff-manifest validator (prod-hardening task 03b).

Loads a handoff-manifest.yaml (via the stdlib minimal_yaml loader — no external
deps), evaluates the 13 declared rules (FLOW-030..037, HDF-010/020/021/030/040)
including sha256 content integrity, emits a handoff-validation-envelope to stdout,
and exits non-zero on any blocking error. Replaces the prompt-trusted skill
(A3-F1) and gives the SDD->dev gate a real fail-closed check (C3/C4).

FLOW-060..063 (chain consistency vs validation-result) are intentionally out of
scope here — this validates a single manifest, not the spec->handoff chain.

Usage:
    validate.py --manifest <path> --specs-dir <dir> [--caller u-spec-orchestrator]

Exit codes: 0 = valid, 1 = invalid OR internal error (fail-closed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
sys.path.insert(0, str(_LIB))
from minimal_yaml import load  # noqa: E402

_HANDOFF_TYPES = {"new_domain", "major_evolution", "fast_track", "reverse_eng"}
_SUMMARY_TYPE_MAP = {
    "major_evolution": ["major"],
    "fast_track": ["patch", "minor"],
    "reverse_eng": ["patch", "minor", "major"],
}
_REQUIRED_BE_ARTIFACTS = ["openapi", "back-spec"]
_VALID_DEV_IMPACT = {None, "no_action", "reevaluate_task_contracts", "stop_domain_task_contracts"}


def _sha256_errors(pkgs: list, specs_dir: Path, code: str) -> list[str]:
    errs: list[str] = []
    for p in pkgs:
        if not isinstance(p, dict):
            errs.append(f"{code}: package entry is not a mapping")
            continue
        path = p.get("path")
        pinned = p.get("sha256")
        if not path:
            errs.append(f"{code}: package entry missing 'path'")
            continue
        if pinned is None:
            continue  # no pinned hash on this entry — nothing to verify
        target = specs_dir / path
        if not target.exists():
            errs.append(f"{code}: file not found for sha256 verification: {path}")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != pinned:
            errs.append(
                f"{code}: sha256 mismatch for {path} "
                f"(pinned {str(pinned)[:12]}…, actual {actual[:12]}…)"
            )
    return errs


def validate(manifest: dict, specs_dir: Path, caller: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    halt_signal = False

    if not isinstance(manifest, dict):
        return {
            "status": "invalid", "errors": ["manifest is not a mapping"],
            "warnings": [], "halt_signal": False,
            "validated_by": "u-handoff-validator", "caller": caller,
        }

    handoff = manifest.get("handoff") or {}
    htype = handoff.get("type")
    domains = manifest.get("domains") or []
    backend = manifest.get("backend_package") or []
    frontend = manifest.get("frontend_package") or []
    change = manifest.get("change_summary")

    # FLOW-030 — sender authorization
    if handoff.get("delivered_by") != "u-spec-orchestrator":
        errors.append(f'FLOW-030: delivered_by must be "u-spec-orchestrator", got "{handoff.get("delivered_by")}"')
    # HDF-010 — handoff type enum
    if htype not in _HANDOFF_TYPES:
        errors.append(f'HDF-010: handoff.type "{htype}" not in {sorted(_HANDOFF_TYPES)}')
    # FLOW-031 — at least one domain
    if not domains:
        errors.append("FLOW-031: handoff must contain at least one domain")
    # FLOW-032 — at least one backend_package entry
    if not backend:
        errors.append("FLOW-032: handoff must include at least one backend_package entry")
    # FLOW-033 — new_domain must NOT carry change_summary
    if htype == "new_domain" and change is not None:
        errors.append("FLOW-033: new_domain handoff must not include change_summary")
    # FLOW-034 — major_evolution/fast_track/reverse_eng MUST carry change_summary
    if htype in ("major_evolution", "fast_track", "reverse_eng") and not change:
        errors.append(f"FLOW-034: {htype} handoff requires change_summary")
    # FLOW-035 — dev_impact enum
    if isinstance(change, dict) and change.get("dev_impact") not in _VALID_DEV_IMPACT:
        errors.append(f'FLOW-035: change_summary.dev_impact "{change.get("dev_impact")}" is not valid')
    # FLOW-036 — change_summary.type conditional on handoff.type
    if isinstance(change, dict) and htype in _SUMMARY_TYPE_MAP:
        allowed = _SUMMARY_TYPE_MAP[htype]
        if change.get("type") not in allowed:
            errors.append(f'FLOW-036: {htype} requires change_summary.type in {allowed}, got "{change.get("type")}"')
    # FLOW-037 — backend_package completeness for new_domain/major_evolution
    if backend and htype in ("new_domain", "major_evolution"):
        present = [p.get("artifact") for p in backend if isinstance(p, dict)]
        for required in _REQUIRED_BE_ARTIFACTS:
            if required not in present:
                errors.append(f'FLOW-037: backend_package missing required artifact "{required}" for {htype}')
    # HDF-030 — halt signal (not an error; flow control for the caller)
    if isinstance(change, dict) and change.get("dev_impact") == "stop_domain_task_contracts":
        halt_signal = True
    # HDF-040 — frontend_artifacts required subfields when present
    fa = manifest.get("frontend_artifacts")
    if isinstance(fa, dict):
        for required in ("front_md_version", "features", "flows"):
            if required not in fa:
                errors.append(f'HDF-040: frontend_artifacts present but missing "{required}"')
    # HDF-020 / HDF-021 — sha256 content integrity
    errors += _sha256_errors(backend, specs_dir, "HDF-020")
    if frontend:
        errors += _sha256_errors(frontend, specs_dir, "HDF-021")

    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
        "halt_signal": halt_signal,
        "validated_by": "u-handoff-validator",
        "caller": caller,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a handoff-manifest.yaml (stdlib only).")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--specs-dir", required=True)
    ap.add_argument("--caller", default="u-spec-orchestrator")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(json.dumps({
            "status": "invalid", "errors": [f"manifest not found: {args.manifest}"],
            "warnings": [], "halt_signal": False,
            "validated_by": "u-handoff-validator", "caller": args.caller,
        }))
        return 1

    try:
        manifest = load(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — fail-closed on any parse error
        print(json.dumps({
            "status": "invalid", "errors": [f"manifest_unparseable: {exc}"],
            "warnings": [], "halt_signal": False,
            "validated_by": "u-handoff-validator", "caller": args.caller,
        }))
        return 1

    result = validate(manifest, Path(args.specs_dir), args.caller)
    print(json.dumps(result))
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "invalid", "errors": [f"internal_error: {exc}"],
                          "warnings": [], "halt_signal": False,
                          "validated_by": "u-handoff-validator", "caller": "unknown"}))
        sys.exit(1)
