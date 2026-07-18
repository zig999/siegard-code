#!/usr/bin/env python3
"""merge_semantic.py — fold semantic verdicts into the structural drift report.

Deterministic (plan R3): given a drift-report.json and a validated
drift-verdicts.json, it produces a new drift-report.json where:
  - an endpoint the semantic layer judged `drifted`/`undecidable` is removed from
    aligned[] and added to findings[] (needs_human, with fix_spec/fix_code);
  - a business_rule verdict becomes a finding (drifted/undecidable/missing → the
    matching status+action) or an aligned[] entry when `aligned`;
  - findings are re-sorted and re-numbered, and the summary is recomputed.

Verdicts must have passed validate_findings.py first. Runs no LLM and makes no
judgement — it only relocates verdicts into the report structure.

Usage:
    merge_semantic.py --report FILE --verdicts FILE [--out FILE]

Exit codes: 0 = merged; 2 = invalid args / unreadable input; 1 = internal error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drift_common import finalize_findings, finding_key, recount  # noqa: E402

_NEEDS_HUMAN = {"drifted", "undecidable"}


def _action(verdict: str) -> str:
    if verdict in _NEEDS_HUMAN:
        return "needs_human"
    if verdict == "missing_in_code":
        return "create_implementation_cr"
    return "update_spec"


def _handoff(vd: dict, domain: str, ref: str) -> dict:
    verdict = vd["verdict"]
    if verdict in _NEEDS_HUMAN:
        h = {"kind": "human_triage", "summary": f"Reconcile {ref} between spec and code."}
        if vd.get("fix_spec"):
            h["fix_spec"] = vd["fix_spec"]
        if vd.get("fix_code"):
            h["fix_code"] = vd["fix_code"]
        return h
    if verdict == "missing_in_code":
        return {"kind": "implementation_cr", "target_command": "/u-dev",
                "summary": f"Implement {ref} per the {domain} spec."}
    return {"kind": "improve_scope", "target_command": "/u-improve",
            "summary": f"Document {ref} in the {domain} spec."}


def _finding_from_verdict(vd: dict) -> dict:
    domain, ref, verdict = vd["domain"], vd["ref"], vd["verdict"]
    artifact_type = "endpoint" if vd["target"] == "endpoint" else "business_rule"
    return {
        "domain": domain,
        "status": verdict,
        "artifact_type": artifact_type,
        "artifact_ref": ref,
        "severity": vd["severity"],
        "default_action": _action(verdict),
        "detail": vd["detail"],
        "spec_evidence": vd.get("spec_evidence"),
        "code_evidence": vd.get("code_evidence"),
        "handoff": _handoff(vd, domain, ref),
    }


def merge(report: dict, verdicts_doc: dict) -> tuple[dict, list]:
    findings = [dict(f) for f in report.get("findings", [])]
    aligned = [dict(a) for a in report.get("aligned", [])]
    skipped = report.get("skipped", [])

    existing = {finding_key(f) for f in findings}
    aligned_index = {(a["domain"], a["artifact_type"], a["artifact_ref"]): a for a in aligned}
    # Snapshot the structurally-aligned endpoints BEFORE mutation. The semantic
    # worker's contract is to judge only aligned endpoints; an endpoint verdict
    # outside that set is out of contract (the endpoint's presence/absence was
    # already decided structurally) and is ignored rather than merged into a
    # contradictory finding. Business rules have no structural match, so they are
    # always accepted.
    original_aligned_ep = {
        (a["domain"], a["artifact_ref"])
        for a in report.get("aligned", [])
        if a["artifact_type"] == "endpoint"
    }
    ignored: list = []

    for vd in verdicts_doc.get("verdicts", []):
        domain, ref, verdict = vd["domain"], vd["ref"], vd["verdict"]
        artifact_type = "endpoint" if vd["target"] == "endpoint" else "business_rule"

        if artifact_type == "endpoint" and (domain, ref) not in original_aligned_ep:
            ignored.append({"domain": domain, "ref": ref, "verdict": verdict,
                            "reason": "endpoint not in structural aligned set"})
            continue

        if verdict == "aligned":
            akey = (domain, artifact_type, ref)
            if akey not in aligned_index:
                entry = {"domain": domain, "artifact_type": artifact_type, "artifact_ref": ref}
                aligned.append(entry)
                aligned_index[akey] = entry
            continue

        # non-aligned verdict → a finding. Remove any structural aligned entry it supersedes.
        akey = (domain, artifact_type, ref)
        if akey in aligned_index:
            aligned = [a for a in aligned if (a["domain"], a["artifact_type"], a["artifact_ref"]) != akey]
            del aligned_index[akey]

        finding = _finding_from_verdict(vd)
        if finding_key(finding) not in existing:
            findings.append(finding)
            existing.add(finding_key(finding))

    findings = finalize_findings(findings)
    aligned.sort(key=lambda x: (x["domain"], x["artifact_type"], x["artifact_ref"]))
    domains_analyzed = report.get("summary", {}).get("domains_analyzed", 0)

    merged = dict(report)
    merged["findings"] = findings
    merged["aligned"] = aligned
    merged["summary"] = recount(findings, aligned, skipped, domains_analyzed)
    return merged, ignored


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True)
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--out", help="Write merged drift-report.json here (default: stdout).")
    args = ap.parse_args(argv)

    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        verdicts_doc = json.loads(Path(args.verdicts).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "reason": "input_read_failed", "detail": str(exc)}))
        return 2

    try:
        merged, ignored = merge(report, verdicts_doc)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    payload = json.dumps(merged, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "ignored_out_of_contract": len(ignored), **merged["summary"]}))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
