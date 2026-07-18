#!/usr/bin/env python3
"""validate_inventory.py — constrain the LLM-produced code-inventory.json.

The code inventory is the one pipeline stage extracted by an LLM, so it is the
one stage that can drift from the contract. This validator is the determinism
guard (plan R3): it fails closed unless the inventory is BOTH shape-correct
(required keys, types, enum values per code-inventory.schema.yaml) AND
evidence-real — every {file, line} anchor must physically resolve against
code_dir (the file exists and the line number is within the file). An inventory
that cannot be verified is rejected, never trusted "approximately".

Zero external deps — the schema shape is checked in code (no jsonschema at
runtime, matching the u-handoff-validator precedent).

Usage:
    validate_inventory.py --code-inventory FILE --code-dir DIR

Exit codes: 0 = valid; 1 = invalid (violations listed); 2 = invalid args.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drift_common import METHODS  # noqa: E402

_ARTIFACT_ARRAYS = ("endpoints", "error_codes", "entities", "state_machines", "events", "business_rules")


def _line_count(path: Path) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def validate(inv: dict, code_dir: Path) -> list[str]:
    v: list[str] = []

    if not isinstance(inv, dict):
        return ["root: code-inventory is not a JSON object"]
    if inv.get("generated_by") != "u-reverse-spec-analyzer":
        v.append("root.generated_by: must equal 'u-reverse-spec-analyzer'")
    for key in ("code_dir", "commit_sha", "base_path"):
        if not isinstance(inv.get(key), str):
            v.append(f"root.{key}: required string missing")
    modules = inv.get("modules")
    if not isinstance(modules, list):
        return v + ["root.modules: required array missing"]

    line_cache: dict[str, int] = {}
    evidence_checked = 0

    def check_evidence(where: str, ev) -> None:
        nonlocal evidence_checked
        if not isinstance(ev, dict) or "file" not in ev or "line" not in ev:
            v.append(f"{where}.evidence: must be an object with file and line")
            return
        f, ln = ev.get("file"), ev.get("line")
        if not isinstance(f, str) or not isinstance(ln, int) or isinstance(ln, bool):
            v.append(f"{where}.evidence: file must be string and line must be integer")
            return
        if ln < 1:
            v.append(f"{where}.evidence.line: {ln} is not >= 1")
            return
        target = (code_dir / f)
        if not target.is_file():
            v.append(f"{where}.evidence.file: '{f}' does not exist under code_dir")
            return
        if f not in line_cache:
            try:
                line_cache[f] = _line_count(target)
            except OSError as exc:
                v.append(f"{where}.evidence.file: '{f}' unreadable ({exc})")
                return
        if ln > line_cache[f]:
            v.append(f"{where}.evidence.line: {ln} exceeds file length {line_cache[f]} of '{f}'")
            return
        evidence_checked += 1

    for mi, mod in enumerate(modules):
        mp = f"modules[{mi}]"
        if not isinstance(mod, dict):
            v.append(f"{mp}: not an object")
            continue
        if not isinstance(mod.get("id"), str):
            v.append(f"{mp}.id: required string missing")
        for arr_name in _ARTIFACT_ARRAYS:
            arr = mod.get(arr_name)
            if not isinstance(arr, list):
                v.append(f"{mp}.{arr_name}: required array missing")
                continue
            for ii, item in enumerate(arr):
                ip = f"{mp}.{arr_name}[{ii}]"
                if not isinstance(item, dict):
                    v.append(f"{ip}: not an object")
                    continue
                if arr_name == "endpoints":
                    if str(item.get("method", "")).lower() not in METHODS:
                        v.append(f"{ip}.method: '{item.get('method')}' is not a valid HTTP method")
                    if not isinstance(item.get("path"), str):
                        v.append(f"{ip}.path: required string missing")
                    if not isinstance(item.get("operation_id"), str):
                        v.append(f"{ip}.operation_id: required string missing")
                    sc = item.get("status_codes")
                    if not isinstance(sc, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in sc):
                        v.append(f"{ip}.status_codes: must be an array of integers")
                elif arr_name == "error_codes":
                    if not isinstance(item.get("code"), str):
                        v.append(f"{ip}.code: required string missing")
                    if not isinstance(item.get("http_status"), int) or isinstance(item.get("http_status"), bool):
                        v.append(f"{ip}.http_status: required integer missing")
                elif arr_name == "entities":
                    if not isinstance(item.get("name"), str):
                        v.append(f"{ip}.name: required string missing")
                    if not isinstance(item.get("fields"), list):
                        v.append(f"{ip}.fields: required array missing")
                elif arr_name == "state_machines":
                    if not isinstance(item.get("entity"), str):
                        v.append(f"{ip}.entity: required string missing")
                    if not isinstance(item.get("states"), list):
                        v.append(f"{ip}.states: required array missing")
                elif arr_name == "events":
                    if not isinstance(item.get("name"), str):
                        v.append(f"{ip}.name: required string missing")
                elif arr_name == "business_rules":
                    if not isinstance(item.get("description"), str):
                        v.append(f"{ip}.description: required string missing")
                check_evidence(ip, item.get("evidence"))

    if evidence_checked == 0 and not v:
        v.append("root: inventory contains no verifiable evidence anchors (empty inventory?)")
    return v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--code-inventory", required=True)
    ap.add_argument("--code-dir", required=True)
    args = ap.parse_args(argv)

    code_dir = Path(args.code_dir)
    if not code_dir.is_dir():
        print(json.dumps({"status": "invalid", "violations": [f"code_dir not found: {code_dir}"]}))
        return 1
    try:
        inv = json.loads(Path(args.code_inventory).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid", "violations": [f"code-inventory unreadable: {exc}"]}))
        return 1

    violations = validate(inv, code_dir)
    if violations:
        print(json.dumps({"status": "invalid", "violation_count": len(violations), "violations": violations[:200]}, indent=2))
        return 1
    print(json.dumps({"status": "valid", "modules": len(inv.get("modules", []))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
