#!/usr/bin/env python3
"""spec_inventory.py — deterministic inventory of approved backend specs.

Walks a specs directory, extracts the code-derivable artifacts (endpoints,
error codes, entities/fields, state-machine states, events, business rules)
from every `Status: approved` backend domain, and emits a spec-inventory.json
(schema: u-shared-templates/spec-inventory.schema.yaml).

Deterministic: same specs -> byte-identical JSON (domains, arrays, and keys are
all sorted). Zero external dependencies — stdlib plus the bundled minimal_yaml
loader. Draft/review domains are excluded from the inventory and reported to the
optional --skipped-out sidecar as {domain, reason: draft_status}.

Scope: BACKEND domains only (openapi.yaml + *.back.md). Frontend feature-spec
drift is out of scope for this release.

Usage:
    spec_inventory.py --specs-dir DIR [--out FILE] [--skipped-out FILE]

Exit codes:
    0  Inventory written (>= 1 approved backend domain found).
    2  Invalid arguments.
    3  No approved backend specs found (caller maps to E_no_approved_specs).
    1  Internal error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drift_common import (  # noqa: E402
    IGNORED_DIR_PARTS,
    METHODS,
    coerce_status_code,
    extract_status,
    normalize_path,
    parse_markdown_tables,
    section_lines,
    sha256_of_files,
)

_LIB = Path(__file__).resolve().parents[3] / "lib"
sys.path.insert(0, str(_LIB))
import minimal_yaml  # noqa: E402


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIR_PARTS for part in path.parts)


def _find_backend_domains(specs_dir: Path) -> list[dict]:
    """Discover backend domains: each directory holding an openapi.yaml. Returns
    dicts with domain id, the openapi path, and sibling back/business spec paths,
    sorted by domain id for determinism."""
    domains: list[dict] = []
    for oa in sorted(specs_dir.rglob("openapi.yaml"), key=lambda p: str(p)):
        if _is_ignored(oa.relative_to(specs_dir)):
            continue
        ddir = oa.parent
        backs = [
            p for p in sorted(ddir.rglob("*.back.md"), key=lambda p: str(p))
            if not _is_ignored(p.relative_to(specs_dir))
        ]
        specs = [
            p for p in sorted(ddir.rglob("*.spec.md"), key=lambda p: str(p))
            if not p.name.endswith((".feature.spec.md", ".component.spec.md"))
            and not _is_ignored(p.relative_to(specs_dir))
        ]
        domains.append(
            {
                "id": ddir.name,
                "dir": ddir,
                "openapi": oa,
                "back": backs[0] if backs else None,
                "spec": specs[0] if specs else None,
            }
        )
    return domains


def _rel(path: Path, specs_dir: Path) -> str:
    try:
        return str(path.relative_to(specs_dir)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _extract_endpoints(openapi_path: Path, specs_dir: Path, diagnostics: list[str], domain_id: str) -> tuple[list[dict], bool]:
    """Returns (endpoints, parse_failed). On parse failure the domain is later
    excluded from the inventory (fail loud) rather than emitted with zero
    endpoints, which would fabricate drift for every real route."""
    try:
        data = minimal_yaml.load(openapi_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        diagnostics.append(f"{domain_id}: openapi parse failed ({type(exc).__name__}: {exc})")
        return [], True
    if not isinstance(data, dict):
        diagnostics.append(f"{domain_id}: openapi root is not a mapping")
        return [], True
    paths = data.get("paths") or {}
    rel = _rel(openapi_path, specs_dir)
    endpoints: list[dict] = []
    for raw_path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if str(method).lower() not in METHODS:
                continue
            op = op if isinstance(op, dict) else {}
            opid = op.get("operationId") or f"{method.lower()}_{raw_path}"
            responses = op.get("responses") or {}
            codes = sorted(
                {c for c in (coerce_status_code(k) for k in responses) if c is not None}
            )
            endpoints.append(
                {
                    "operation_id": str(opid),
                    "method": str(method).lower(),
                    "path": normalize_path(str(raw_path)),
                    "status_codes": codes,
                    "spec_anchor": f"{rel}#{opid}",
                }
            )
    endpoints.sort(key=lambda e: (e["method"], e["path"], e["operation_id"]))
    return endpoints, False


def _extract_from_back(back_path: Path | None, specs_dir: Path) -> dict:
    """Extract error_codes, entities, state_machines, events, business_rules
    from a *.back.md file following TEMPLATE.back.md structure."""
    out = {"error_codes": [], "entities": [], "state_machines": [], "events": [], "business_rules": []}
    if back_path is None:
        return out
    text = back_path.read_text(encoding="utf-8")
    rel = _rel(back_path, specs_dir)

    # --- Business rules + error codes (Section 3) ---
    br_blocks = re.split(r"(?m)^###\s+(BR-\d+)", text)
    # br_blocks = [pre, id1, body1, id2, body2, ...]
    error_codes: dict[str, int] = {}
    for i in range(1, len(br_blocks), 2):
        br_id = br_blocks[i].strip()
        body = br_blocks[i + 1] if i + 1 < len(br_blocks) else ""
        uc = re.search(r"\*\*Related UC:\*\*\s*(UC-\d+)", body)
        desc = re.search(r"\*\*Description:\*\*\s*(.+)", body)
        out["business_rules"].append(
            {
                "id": br_id,
                "uc_ref": uc.group(1) if uc else "",
                "description": (desc.group(1).strip() if desc else ""),
                "spec_anchor": f"{rel}#{br_id}",
            }
        )
        err = re.search(r"error\.code:\s*`?([A-Z0-9_]+)`?", body)
        status = re.search(r"HTTP\s*(\d{3})", body)
        if err:
            code = err.group(1)
            error_codes.setdefault(code, int(status.group(1)) if status else 0)
    for code in sorted(error_codes):
        out["error_codes"].append(
            {"code": code, "http_status": error_codes[code], "spec_anchor": f"{rel}#error-codes"}
        )

    # --- Entities (Section 2 — Data Model, "### Table: {name}") ---
    dm_lines = section_lines(text, r"Data Model")
    dm_text = "\n".join(dm_lines)
    table_blocks = re.split(r"(?m)^###\s+Table:\s*(.+)$", dm_text)
    for i in range(1, len(table_blocks), 2):
        name = table_blocks[i].strip()
        body = table_blocks[i + 1] if i + 1 < len(table_blocks) else ""
        tables = parse_markdown_tables(body.splitlines())
        fields: list[dict] = []
        for tbl in tables:
            if not tbl:
                continue
            header = [h.lower() for h in tbl[0]]
            if "field" not in header or "type" not in header:
                continue
            fi, ti = header.index("field"), header.index("type")
            for row in tbl[1:]:
                if len(row) <= max(fi, ti):
                    continue
                fname = row[fi].strip().strip("`")
                ftype = row[ti].strip().strip("`")
                if fname:
                    fields.append({"name": fname, "type": ftype})
            break  # first Field/Type table under this entity
        out["entities"].append(
            {"name": name, "fields": fields, "spec_anchor": f"{rel}#data-model"}
        )

    # --- State machines (Section 4 — "### ST-01 -- {Entity}") ---
    st_lines = section_lines(text, r"State Machine")
    st_text = "\n".join(st_lines)
    st_blocks = re.split(r"(?m)^###\s+(ST-\d+)\s*--\s*(.+)$", st_text)
    # groups: [pre, id, entity, body, id, entity, body, ...]
    for i in range(1, len(st_blocks), 3):
        st_id = st_blocks[i].strip()
        entity = st_blocks[i + 1].strip()
        body = st_blocks[i + 2] if i + 2 < len(st_blocks) else ""
        states: set[str] = set()
        for tbl in parse_markdown_tables(body.splitlines()):
            if not tbl:
                continue
            header = [h.lower() for h in tbl[0]]
            if "from" not in header or "to" not in header:
                continue
            fi, ti = header.index("from"), header.index("to")
            for row in tbl[1:]:
                for idx in (fi, ti):
                    if idx < len(row):
                        val = row[idx].strip().strip("`")
                        if val and val not in {"-", "--"}:
                            states.add(val)
        out["state_machines"].append(
            {
                "id": st_id,
                "entity": entity,
                "states": sorted(states),
                "spec_anchor": f"{rel}#{st_id}",
            }
        )

    # --- Events (Section 5 — "### EV-01 -- {event.name}") ---
    ev_lines = section_lines(text, r"Domain Events")
    for m in re.finditer(r"(?m)^###\s+(EV-\d+)\s*--\s*(.+)$", "\n".join(ev_lines)):
        out["events"].append(
            {"id": m.group(1).strip(), "name": m.group(2).strip(), "spec_anchor": f"{rel}#{m.group(1).strip()}"}
        )

    return out


def build_inventory(specs_dir: Path) -> tuple[dict, list[dict], list[str]]:
    domains_meta = _find_backend_domains(specs_dir)
    diagnostics: list[str] = []
    approved: list[dict] = []
    skipped: list[dict] = []
    approved_files: list[Path] = []

    for dm in domains_meta:
        # QA-6: approval is derived from the business spec (.spec.md) as the primary
        # signal, but a back-spec explicitly marked draft/review while the business
        # spec is approved is a real inconsistency — extracting from a draft back-spec
        # would audit unapproved content. Treat the domain as not approved and flag it.
        spec_status = extract_status(dm["spec"].read_text(encoding="utf-8")) if dm["spec"] else None
        back_status = extract_status(dm["back"].read_text(encoding="utf-8")) if dm["back"] else None
        primary = spec_status if spec_status is not None else back_status
        is_approved = primary == "approved"
        if is_approved and back_status in ("draft", "review"):
            diagnostics.append(
                f"{dm['id']}: business spec approved but back-spec status is '{back_status}' "
                "— treated as not approved (status inconsistency)"
            )
            is_approved = False
        if not is_approved:
            skipped.append({"domain": dm["id"], "reason": "draft_status"})
            continue
        endpoints, parse_failed = _extract_endpoints(dm["openapi"], specs_dir, diagnostics, dm["id"])
        if parse_failed:
            # Fail loud: exclude the domain rather than fabricate drift for every
            # real route. Surfaced in the report as skipped/parse_failed.
            skipped.append({"domain": dm["id"], "reason": "parse_failed"})
            continue
        back = _extract_from_back(dm["back"], specs_dir)
        approved_files.append(dm["openapi"])
        if dm["back"]:
            approved_files.append(dm["back"])
        if dm["spec"]:
            approved_files.append(dm["spec"])
        approved.append(
            {
                "id": dm["id"],
                "title": dm["id"],
                "status": "approved",
                "endpoints": endpoints,
                "error_codes": back["error_codes"],
                "entities": sorted(back["entities"], key=lambda e: e["name"].lower()),
                "state_machines": sorted(back["state_machines"], key=lambda s: s["entity"].lower()),
                "events": sorted(back["events"], key=lambda e: e["name"]),
                "business_rules": sorted(back["business_rules"], key=lambda b: b["id"]),
            }
        )

    approved.sort(key=lambda d: d["id"])
    skipped.sort(key=lambda s: s["domain"])
    inventory = {
        "generated_by": "spec_inventory.py",
        "specs_dir": str(specs_dir).replace("\\", "/"),
        "spec_content_hash": sha256_of_files(approved_files, base_dir=specs_dir),
        "domains": approved,
    }
    return inventory, skipped, diagnostics


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--specs-dir", required=True)
    ap.add_argument("--out", help="Write inventory JSON here (default: stdout).")
    ap.add_argument("--skipped-out", help="Write the draft-skipped domains list here.")
    args = ap.parse_args(argv)

    specs_dir = Path(args.specs_dir)
    if not specs_dir.is_dir():
        print(json.dumps({"status": "error", "reason": "specs_dir_not_found", "detail": str(specs_dir)}))
        return 2

    try:
        inventory, skipped, diagnostics = build_inventory(specs_dir)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}))
        return 1

    payload = json.dumps(inventory, indent=2, sort_keys=False)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    if args.skipped_out:
        Path(args.skipped_out).write_text(json.dumps(skipped, indent=2) + "\n", encoding="utf-8")

    summary = {
        "status": "ok",
        "approved_domains": len(inventory["domains"]),
        "skipped_draft": len(skipped),
        "diagnostics": diagnostics,
    }
    print(json.dumps(summary), file=sys.stderr)

    if not inventory["domains"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
