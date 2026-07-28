#!/usr/bin/env python3
"""Deterministic handoff-manifest validator (prod-hardening task 03b).

Loads a handoff-manifest.yaml (via the stdlib minimal_yaml loader — no external
deps), evaluates the 13 declared rules (FLOW-030..037, HDF-010/020/021/030/040)
including sha256 content integrity, emits a handoff-validation-envelope to stdout,
and exits non-zero on any blocking error. Replaces the prompt-trusted skill
(A3-F1) and gives the SDD->dev gate a real fail-closed check (C3/C4).

PROV rules (v2.35.0 — provenance, not just integrity). HDF-020/021 prove the
manifest matches the FILES; they cannot prove the files came from the PIPELINE
— a freelance edit followed by manifest regeneration passes every integrity
gate. PROV closes that: the append-only, hash-chained log acts as a notary
(worker task_completed events carry artifacts_sha256 computed by emit.py; the
sdd phase records a spec_baseline_recorded snapshot at entry; the generator
appends handoff_manifest_generated), and PROV verifies the manifest against
the log — which does not rewrite.

  PROV-010  every pinned artifact sha256 equals the latest log-notarized hash
            for that path (worker terminal after the baseline, latest seq wins)
            OR the baseline hash (file untouched during the workflow)
  PROV-020  the manifest file's own sha256 equals the hash recorded by the
            latest handoff_manifest_generated event for this workflow.
            Scope note: this proves the manifest is the generator's output
            (freshness/derivation), not WHO ran the generator — content
            authorship is PROV-010's job
  PROV-030  a handoff_manifest_generated event exists for this workflow —
            delivered_by is backed by generation evidence (P8), not by the
            self-asserted const string alone

Degradation (A6', migration): PROV runs only when a spec_baseline_recorded
event exists for the workflow. No baseline (pre-2.35 workflow, or log absent)
-> PROV checks are emitted as warnings, never errors — upgrading mid-flight
targets must not break.

FLOW-060..063 (chain consistency vs validation-result) are intentionally out of
scope here — this validates a single manifest, not the spec->handoff chain.

Usage:
    validate.py --manifest <path> --specs-dir <dir> [--caller u-spec-orchestrator]
                [--project-dir <dir>] [--workflow-id <wid>]

--workflow-id omitted -> derived from the newest spec_baseline_recorded event
(single-active-workflow heuristic; concurrent workflows in one project should
always pass it explicitly).

Exit codes: 0 = valid, 1 = invalid OR internal error (fail-closed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def _load_event_data(event) -> dict:
    """Event data with blob refs resolved (baselines can be externalized)."""
    from orch_core import is_blob_ref, load_blob_data
    data = event.data
    if is_blob_ref(data):
        try:
            return load_blob_data(event)
        except Exception:  # noqa: BLE001
            return {}
    return data


def _provenance_errors(
    manifest: dict, manifest_path: Path, specs_dir: Path,
    project_dir: Path, workflow_id: str | None,
) -> tuple[list[str], list[str]]:
    """PROV-010/020/030 — returns (errors, warnings). See module docstring."""
    try:
        import orch_core
        from orch_core import EventType, read_events
        # orch_core resolves its path globals from ORCH_PROJECT_DIR at import
        # time; honor the explicit --project-dir regardless of import order.
        base = project_dir / ".orch"
        orch_core.ORCH_DIR = base
        orch_core.LOG_PATH = base / "log.jsonl"
        orch_core.BLOBS_DIR = base / "blobs"
        events = list(read_events())
    except Exception as exc:  # noqa: BLE001
        return [], [f"PROV: skipped — log unreadable ({exc})"]
    if not events:
        return [], ["PROV: skipped — no orchestration log"]

    # Locate the workflow's baseline (latest one for the id; without an id,
    # the newest baseline overall — single-active-workflow heuristic).
    baseline_event = None
    for event in events:
        if event.event_type != EventType.SPEC_BASELINE_RECORDED.value:
            continue
        data = _load_event_data(event)
        if workflow_id is None or data.get("workflow_id") == workflow_id:
            baseline_event = (event.seq, data)
    if baseline_event is None:
        return [], [
            "PROV: skipped — no spec_baseline_recorded for this workflow "
            "(pre-2.35 workflow); provenance not enforced (A6' migration)"
        ]
    baseline_seq, baseline_data = baseline_event
    wid = workflow_id or baseline_data.get("workflow_id")
    baseline = baseline_data.get("artifacts") or {}

    # v2.35.1 diagnostic degradation: a baseline recorded against the WRONG
    # specs_dir (the mwoassistant field incident — env-default "specs" while
    # CLAUDE.md declared docs/specs) cannot anchor provenance: every untouched
    # pinned file would false-positive PROV-010 and the once-per-workflow
    # idempotency blocks re-recording. Detect the mismatch deterministically
    # and degrade to a diagnosed warning instead of failing the handoff.
    try:
        from orch_core import claude_md_specs_dir
        declared = claude_md_specs_dir(project_dir)
    except Exception:  # noqa: BLE001
        declared = None
    recorded = (baseline_data.get("specs_dir") or "").replace("\\", "/").strip("/")
    if declared and recorded and recorded != declared:
        return [], [
            f"PROV: skipped — baseline (seq {baseline_seq}) was recorded against "
            f"specs_dir {recorded!r} but CLAUDE.md declares {declared!r}; an empty/"
            "misdirected baseline cannot anchor provenance for this workflow. "
            "Provenance not enforced (diagnostic degradation, v2.35.1) — the next "
            "workflow records a correct baseline via the shared resolver."
        ]

    # Latest worker-notarized hash per path since the baseline (seq order —
    # read_events yields ascending seq, so plain assignment keeps the latest).
    notarized: dict[str, str] = {}
    generated = None
    for event in events:
        if event.seq <= baseline_seq:
            continue
        if event.event_type == EventType.TASK_COMPLETED.value:
            data = _load_event_data(event)
            for path, digest in (data.get("artifacts_sha256") or {}).items():
                notarized[path.replace("\\", "/")] = digest
        elif event.event_type == EventType.HANDOFF_MANIFEST_GENERATED.value:
            data = _load_event_data(event)
            if data.get("workflow_id") == wid:
                generated = data

    errors: list[str] = []
    warnings: list[str] = []

    # PROV-010 — pinned hashes must be log-notarized (worker) or baseline (untouched)
    project_res = project_dir.resolve()
    for code, pkgs in (("backend_package", manifest.get("backend_package") or []),
                       ("frontend_package", manifest.get("frontend_package") or [])):
        for p in pkgs:
            if not isinstance(p, dict) or not p.get("path") or p.get("sha256") is None:
                continue  # structural problems are HDF-020/021's job
            rel = p["path"]
            try:
                key = (specs_dir / rel).resolve().relative_to(project_res).as_posix()
            except (ValueError, OSError):
                key = str(rel).replace("\\", "/")
            pinned = p["sha256"]
            worker_hash = notarized.get(key)
            baseline_hash = baseline.get(key)
            if pinned == worker_hash:
                continue  # produced by a pipeline worker during this workflow
            if worker_hash is None and pinned == baseline_hash:
                continue  # untouched since adoption baseline
            errors.append(
                f"PROV-010: {key} ({code}) has no provenance — pinned "
                f"{str(pinned)[:12]}… matches neither a worker-notarized hash "
                f"({str(worker_hash)[:12] + '…' if worker_hash else 'none'}) nor the "
                f"adoption baseline ({str(baseline_hash)[:12] + '…' if baseline_hash else 'absent'}). "
                "The file was modified outside the pipeline after the baseline."
            )

    # PROV-020 / PROV-030 — manifest backed by generation evidence
    if generated is None:
        errors.append(
            "PROV-030: no handoff_manifest_generated event for this workflow — "
            "delivered_by has no generation evidence in the log (P8)"
        )
    else:
        actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        recorded = generated.get("manifest_sha256")
        if actual != recorded:
            errors.append(
                f"PROV-020: manifest sha256 {actual[:12]}… differs from the hash "
                f"recorded at generation ({str(recorded)[:12]}…) — the manifest on "
                "disk is not the generator's output"
            )

    return errors, warnings


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
    ap.add_argument("--project-dir", default=os.environ.get("ORCH_PROJECT_DIR", "."),
                    help="project root for provenance log lookup (PROV rules)")
    ap.add_argument("--workflow-id", default=os.environ.get("WORKFLOW_ID") or None,
                    help="workflow to scope PROV against; derived from the newest baseline when omitted")
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

    # PROV (v2.35.0) — provenance against the log; fail-soft on internal errors
    # (a broken PROV lookup must not mask the 13 structural rules' verdict).
    try:
        prov_errors, prov_warnings = _provenance_errors(
            manifest, manifest_path, Path(args.specs_dir),
            Path(args.project_dir), args.workflow_id,
        )
        result["errors"].extend(prov_errors)
        result["warnings"].extend(prov_warnings)
        if prov_errors:
            result["status"] = "invalid"
    except Exception as exc:  # noqa: BLE001
        result["warnings"].append(f"PROV: internal error, provenance not evaluated ({exc})")

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
