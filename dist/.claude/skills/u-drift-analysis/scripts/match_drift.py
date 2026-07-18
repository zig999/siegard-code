#!/usr/bin/env python3
"""match_drift.py — deterministic spec<->code drift matcher.

Joins a spec-inventory.json and a code-inventory.json by exact keys and emits a
drift-report.json (schema: u-shared-templates/drift-report.schema.yaml). Every
artifact class reduces to presence/absence of a canonical key:

    endpoint       -> "{method} {normalized_path}"
    error_code     -> code string
    entity         -> entity name (lowercased)     [field-level diff when both sides present]
    state_machine  -> entity name (lowercased)
    event          -> event name

spec-only key -> missing_in_code (spec is the truth: create_implementation_cr)
code-only key -> missing_in_spec (document the code: update_spec)
both present  -> aligned (structural). Within-item drift (status codes, http
                 status, state set, BR behavior) is deferred to the semantic
                 layer (Release B) and is NOT decided here.

When a matched domain has spec endpoints AND code endpoints but ZERO endpoint
keys intersect, a single base_path_mismatch_suspected finding is emitted
instead of flooding the report with N missing_in_code + M missing_in_spec
endpoints (plan R6). No heuristic fallback ever pairs unrelated endpoints.

Deterministic: same two inventories -> byte-identical report. Zero external deps.

Usage:
    match_drift.py --spec-inventory FILE --code-inventory FILE
                   [--skipped FILE] [--out FILE]

Exit codes: 0 = report written; 2 = invalid args; 1 = internal error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drift_common import endpoint_key, finalize_findings, recount  # noqa: E402

# (status, artifact_type, level) -> severity
_ITEM = "item"
_FIELD = "field"


def _severity(status: str, artifact_type: str, level: str) -> str:
    if artifact_type == "endpoint":
        return "blocking" if status == "missing_in_code" else "major"
    if artifact_type == "error_code":
        return "minor"
    if artifact_type == "entity_field":
        if level == _FIELD:
            return "minor"
        return "major"  # entity-level presence
    if artifact_type == "state_machine":
        return "major" if status == "missing_in_code" else "minor"
    if artifact_type == "event":
        return "major" if status == "missing_in_code" else "minor"
    return "major"


def _action(status: str) -> str:
    return "create_implementation_cr" if status == "missing_in_code" else "update_spec"


def _split_anchor(spec_anchor: str) -> dict:
    if "#" in spec_anchor:
        file_, anchor = spec_anchor.rsplit("#", 1)
    else:
        file_, anchor = spec_anchor, ""
    return {"file": file_, "anchor": anchor}


def _handoff(status: str, domain: str, artifact_type: str, ref: str) -> dict:
    if status == "missing_in_code":
        return {
            "kind": "implementation_cr",
            "target_command": "/u-dev",
            "summary": f"Implement {ref} per the {domain} spec.",
        }
    return {
        "kind": "improve_scope",
        "target_command": "/u-improve",
        "summary": f"Document {ref} ({artifact_type}) in the {domain} spec.",
    }


def _make_finding(domain, status, artifact_type, ref, level, spec_item, code_item) -> dict:
    spec_ev = _split_anchor(spec_item["spec_anchor"]) if (spec_item and status == "missing_in_code") else None
    code_ev = (
        {"file": code_item["evidence"]["file"], "line": code_item["evidence"]["line"]}
        if (code_item and status == "missing_in_spec")
        else None
    )
    if status == "missing_in_code":
        subject, verb, side = "Spec", "declares", "no matching implementation exists in code"
    else:
        subject, verb, side = "Code", "implements", "no corresponding spec artifact exists"
    return {
        "domain": domain,
        "status": status,
        "artifact_type": artifact_type,
        "artifact_ref": ref,
        "severity": _severity(status, artifact_type, level),
        "default_action": _action(status),
        "detail": f"{subject} {verb} {artifact_type} {ref} but {side}.",
        "spec_evidence": spec_ev,
        "code_evidence": code_ev,
        "handoff": _handoff(status, domain, artifact_type, ref),
    }


def _index(items: list, key_fn) -> dict:
    out: dict = {}
    for it in items:
        out.setdefault(key_fn(it), it)
    return out


def _diff_presence(spec_index, code_index, domain, artifact_type, ref_fn, level=_ITEM):
    """Emit missing_in_code / missing_in_spec findings and aligned refs for a
    presence-keyed artifact class."""
    findings, aligned = [], []
    for key in sorted(set(spec_index) | set(code_index)):
        s, c = spec_index.get(key), code_index.get(key)
        if s and not c:
            findings.append(_make_finding(domain, "missing_in_code", artifact_type, ref_fn(key, s, c), level, s, c))
        elif c and not s:
            findings.append(_make_finding(domain, "missing_in_spec", artifact_type, ref_fn(key, s, c), level, s, c))
        else:
            aligned.append({"domain": domain, "artifact_type": artifact_type, "artifact_ref": ref_fn(key, s, c)})
    return findings, aligned


def _match_domain(spec_dom: dict, code_mod: dict) -> tuple[list, list]:
    domain = spec_dom["id"]
    findings: list = []
    aligned: list = []

    # --- endpoints (with base_path guard) ---
    s_ep = _index(spec_dom["endpoints"], lambda e: endpoint_key(e["method"], e["path"]))
    c_ep = _index(code_mod["endpoints"], lambda e: endpoint_key(e["method"], e["path"]))
    if s_ep and c_ep and not (set(s_ep) & set(c_ep)):
        first_s = spec_dom["endpoints"][0]
        first_c = code_mod["endpoints"][0]
        findings.append(
            {
                "domain": domain,
                "status": "undecidable",
                "artifact_type": "base_path",
                "artifact_ref": f"{len(s_ep)} spec / {len(c_ep)} code endpoints",
                "severity": "blocking",
                "default_action": "needs_human",
                "detail": (
                    f"{len(s_ep)} spec endpoints and {len(c_ep)} code endpoints but zero path "
                    "matches — likely a base_path or routing-prefix mismatch, not real drift."
                ),
                "spec_evidence": _split_anchor(first_s["spec_anchor"]),
                "code_evidence": {"file": first_c["evidence"]["file"], "line": first_c["evidence"]["line"]},
                "handoff": {
                    "kind": "human_triage",
                    "summary": "Confirm the router base_path so endpoints can be matched.",
                    "fix_spec": "Ensure spec paths are authored relative to the same base as the code.",
                    "fix_code": "Set code-inventory base_path to the real router prefix and re-run.",
                },
            }
        )
    else:
        f, a = _diff_presence(s_ep, c_ep, domain, "endpoint", lambda k, s, c: k)
        findings += f
        aligned += a

    # --- error codes ---
    f, a = _diff_presence(
        _index(spec_dom["error_codes"], lambda e: e["code"]),
        _index(code_mod["error_codes"], lambda e: e["code"]),
        domain, "error_code", lambda k, s, c: k,
    )
    findings += f
    aligned += a

    # --- entities (entity-level presence + field-level diff when both present) ---
    s_ent = _index(spec_dom["entities"], lambda e: e["name"].lower())
    c_ent = _index(code_mod["entities"], lambda e: e["name"].lower())
    for key in sorted(set(s_ent) | set(c_ent)):
        s, c = s_ent.get(key), c_ent.get(key)
        if s and not c:
            findings.append(_make_finding(domain, "missing_in_code", "entity_field", s["name"], _ITEM, s, c))
        elif c and not s:
            findings.append(_make_finding(domain, "missing_in_spec", "entity_field", c["name"], _ITEM, s, c))
        else:
            aligned.append({"domain": domain, "artifact_type": "entity_field", "artifact_ref": s["name"]})
            s_fields = _index(s["fields"], lambda fl: fl["name"].lower())
            c_fields = _index(c["fields"], lambda fl: fl["name"].lower())
            for fk in sorted(set(s_fields) | set(c_fields)):
                sf, cf = s_fields.get(fk), c_fields.get(fk)
                ref = f"{s['name']}.{(sf or cf)['name']}"
                if sf and not cf:
                    findings.append(_make_finding(domain, "missing_in_code", "entity_field", ref, _FIELD, s, c))
                elif cf and not sf:
                    findings.append(_make_finding(domain, "missing_in_spec", "entity_field", ref, _FIELD, s, c))

    # --- state machines (entity-level presence) ---
    f, a = _diff_presence(
        _index(spec_dom["state_machines"], lambda s: s["entity"].lower()),
        _index(code_mod["state_machines"], lambda s: s["entity"].lower()),
        domain, "state_machine", lambda k, s, c: f"ST {(s or c)['entity']}",
    )
    findings += f
    aligned += a

    # --- events (name presence) ---
    f, a = _diff_presence(
        _index(spec_dom["events"], lambda e: e["name"]),
        _index(code_mod["events"], lambda e: e["name"]),
        domain, "event", lambda k, s, c: k,
    )
    findings += f
    aligned += a

    return findings, aligned


def build_report(spec_inv: dict, code_inv: dict, skipped_in: list) -> dict:
    spec_domains = {d["id"].lower(): d for d in spec_inv.get("domains", [])}
    code_modules = {m["id"].lower(): m for m in code_inv.get("modules", [])}

    findings: list = []
    aligned: list = []
    skipped: list = list(skipped_in)

    matched_keys = sorted(set(spec_domains) & set(code_modules))
    for key in matched_keys:
        f, a = _match_domain(spec_domains[key], code_modules[key])
        findings += f
        aligned += a

    for key in sorted(set(spec_domains) - set(code_modules)):
        skipped.append({"domain": spec_domains[key]["id"], "reason": "no_code_module"})
    for key in sorted(set(code_modules) - set(spec_domains)):
        skipped.append({"domain": code_modules[key]["id"], "reason": "no_spec_domain"})

    # Deterministic ordering + stable DRIFT ids.
    findings = finalize_findings(findings)
    aligned.sort(key=lambda x: (x["domain"], x["artifact_type"], x["artifact_ref"]))
    # dedupe skipped (a domain could be both draft and unmatched — draft wins)
    seen: dict = {}
    for s in skipped:
        seen.setdefault(s["domain"], s)
    skipped = sorted(seen.values(), key=lambda s: s["domain"])

    counts = recount(findings, aligned, skipped, len(matched_keys))

    return {
        "generated_by": "match_drift.py",
        "specs_dir": spec_inv.get("specs_dir", ""),
        "code_dir": code_inv.get("code_dir", ""),
        "spec_content_hash": spec_inv.get("spec_content_hash", ""),
        "code_commit_sha": code_inv.get("commit_sha", ""),
        "summary": counts,
        "findings": findings,
        "aligned": aligned,
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec-inventory", required=True)
    ap.add_argument("--code-inventory", required=True)
    ap.add_argument("--skipped", help="JSON list of already-skipped domains (draft_status).")
    ap.add_argument("--generated-at", help="ISO-8601 UTC timestamp to stamp into the report (scripts have no clock).")
    ap.add_argument("--out", help="Write drift-report.json here (default: stdout).")
    args = ap.parse_args(argv)

    try:
        spec_inv = json.loads(Path(args.spec_inventory).read_text(encoding="utf-8"))
        code_inv = json.loads(Path(args.code_inventory).read_text(encoding="utf-8"))
        skipped_in = json.loads(Path(args.skipped).read_text(encoding="utf-8")) if args.skipped else []
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "reason": "input_read_failed", "detail": str(exc)}))
        return 2

    try:
        report = build_report(spec_inv, code_inv, skipped_in)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    if args.generated_at:
        # Insert generated_at right after generated_by for readability.
        stamped = {"generated_by": report["generated_by"], "generated_at": args.generated_at}
        stamped.update({k: v for k, v in report.items() if k != "generated_by"})
        report = stamped

    payload = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", **report["summary"]}), file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
