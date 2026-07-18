#!/usr/bin/env python3
"""validate_findings.py — constrain the LLM-produced semantic verdicts.

The semantic layer (u-drift-analyzer) is LLM-produced, so it is clamped exactly
like the code inventory (plan R3). This validator fails closed unless the
drift-verdicts.json is shape-correct (per drift-verdicts.schema.yaml) AND
evidence-real: every non-null code_evidence {file, line} must physically resolve
against code_dir, and every verdict must cite at least one evidence side (P8 —
no unsupported claim). A verdict set that cannot be verified is rejected, never
merged "approximately".

Usage:
    validate_findings.py --verdicts FILE --code-dir DIR

Exit codes: 0 = valid; 1 = invalid (violations listed); 2 = invalid args.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TARGETS = {"endpoint", "business_rule"}
_VERDICTS = {"aligned", "drifted", "missing_in_code", "missing_in_spec", "undecidable"}
_SEVERITIES = {"blocking", "major", "minor"}


def _line_count(path: Path) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def validate(doc: dict, code_dir: Path) -> list[str]:
    v: list[str] = []
    if not isinstance(doc, dict):
        return ["root: drift-verdicts is not a JSON object"]
    if doc.get("generated_by") != "u-drift-analyzer":
        v.append("root.generated_by: must equal 'u-drift-analyzer'")
    if not isinstance(doc.get("code_dir"), str):
        v.append("root.code_dir: required string missing")
    verdicts = doc.get("verdicts")
    if not isinstance(verdicts, list):
        return v + ["root.verdicts: required array missing"]

    line_cache: dict[str, int] = {}

    def check_code_ev(where: str, ev) -> bool:
        if ev is None:
            return False
        if not isinstance(ev, dict) or not isinstance(ev.get("file"), str) or not isinstance(ev.get("line"), int) or isinstance(ev.get("line"), bool):
            v.append(f"{where}.code_evidence: must be null or {{file:str, line:int}}")
            return False
        f, ln = ev["file"], ev["line"]
        if ln < 1:
            v.append(f"{where}.code_evidence.line: {ln} is not >= 1")
            return False
        target = code_dir / f
        if not target.is_file():
            v.append(f"{where}.code_evidence.file: '{f}' does not exist under code_dir")
            return False
        if f not in line_cache:
            try:
                line_cache[f] = _line_count(target)
            except OSError as exc:
                v.append(f"{where}.code_evidence.file: '{f}' unreadable ({exc})")
                return False
        if ln > line_cache[f]:
            v.append(f"{where}.code_evidence.line: {ln} exceeds file length {line_cache[f]} of '{f}'")
            return False
        return True

    for i, vd in enumerate(verdicts):
        w = f"verdicts[{i}]"
        if not isinstance(vd, dict):
            v.append(f"{w}: not an object")
            continue
        if vd.get("target") not in _TARGETS:
            v.append(f"{w}.target: must be one of {sorted(_TARGETS)}")
        if not isinstance(vd.get("ref"), str):
            v.append(f"{w}.ref: required string missing")
        if not isinstance(vd.get("domain"), str):
            v.append(f"{w}.domain: required string missing")
        if vd.get("verdict") not in _VERDICTS:
            v.append(f"{w}.verdict: must be one of {sorted(_VERDICTS)}")
        if vd.get("severity") not in _SEVERITIES:
            v.append(f"{w}.severity: must be one of {sorted(_SEVERITIES)}")
        if not isinstance(vd.get("detail"), str) or not vd.get("detail"):
            v.append(f"{w}.detail: required non-empty string missing")
        code_ok = check_code_ev(w, vd.get("code_evidence"))
        spec_ev = vd.get("spec_evidence")
        spec_ok = isinstance(spec_ev, dict) and isinstance(spec_ev.get("file"), str) and isinstance(spec_ev.get("anchor"), str)
        if spec_ev is not None and not spec_ok:
            v.append(f"{w}.spec_evidence: must be null or {{file:str, anchor:str}}")
        if not code_ok and not spec_ok:
            v.append(f"{w}: at least one of spec_evidence/code_evidence must be present and valid (P8)")

    return v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--code-dir", required=True)
    args = ap.parse_args(argv)

    code_dir = Path(args.code_dir)
    if not code_dir.is_dir():
        print(json.dumps({"status": "invalid", "violations": [f"code_dir not found: {code_dir}"]}))
        return 1
    try:
        doc = json.loads(Path(args.verdicts).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid", "violations": [f"verdicts unreadable: {exc}"]}))
        return 1

    violations = validate(doc, code_dir)
    if violations:
        print(json.dumps({"status": "invalid", "violation_count": len(violations), "violations": violations[:200]}, indent=2))
        return 1
    print(json.dumps({"status": "valid", "verdicts": len(doc.get("verdicts", []))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
