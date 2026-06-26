#!/usr/bin/env python3
"""
attribute_failures.py — Map suite-run failures to Task Contracts.

Reads:
  - <suite-run-dir>/manifest.json  (produced by run_suite.py with build + tests
    sections; attribution section may be absent or "pending")
  - For each TC: <project-dir>/<delivery_path> — the tc-XX-delivery.md whose
    `delivery-body` YAML block lists files_created[].path, files_modified[].path,
    and tests[].file.

Writes:
  - <suite-run-dir>/by-tc/<task_id>.json  (per-TC attribution slice)
  - Updates <suite-run-dir>/manifest.json `attribution` field in-place

Attribution stages:
  A. test_in_tests_written      — failing test_file appears in some TC's tests[].file
  B. regression_via_import      — failing test imports a module owned by a TC
                                  (files_created/files_modified path match)
  C. unattributed               — surfaces in manifest.attribution.unattributed_failures;
                                  every active TC gets test_gate_result =
                                  "blocked_by_unattributed_failure"

Build-error attribution: each build error's `file` is matched against
files_created/files_modified across all TCs. Errors not matched are surfaced as
unattributed; if any build error exists, every TC is marked blocked_by_build.

Usage:
    python3 attribute_failures.py \
      --suite-run-dir <abs path to qa/_suite-run/sr-N> \
      --project-dir <abs path> \
      --deliveries '<JSON list: [{"task_id":"...", "delivery_path":"..."}, ...]>'

Output (stdout, exit 0):
    {"status": "ok", "manifest": "<path>", "by_tc_count": int,
     "unattributed_test_failures": int, "unattributed_build_errors": int}

Output (exit 1, stderr):
    {"status": "error", "reason": "<code>", "detail": "..."}
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


# ── Delivery YAML extraction (no PyYAML — stdlib only) ─────────────────────────

_YAML_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


def _extract_yaml_block(content: str, marker: str) -> str:
    """Return the body of the ```yaml fenced block whose first non-empty line
    starts with `# {marker}`. Returns "" if no such block is found."""
    for match in _YAML_FENCE_RE.finditer(content):
        block = match.group(1)
        first = next((ln for ln in block.splitlines() if ln.strip()), "").strip()
        if first.startswith(f"# {marker}"):
            return block
    return ""


def _extract_list_field(yaml_text: str, section: str, key: str) -> list[str]:
    """
    Extract every `{key}: <value>` from list items under `{section}:`.

    Supports the shape used in tc-XX-delivery.md:

        section:
          - key: "value-1"
            other: ...
          - key: "value-2"

    Returns [] if section is empty (`section: []`) or absent.
    """
    out: list[str] = []
    lines = yaml_text.splitlines()
    in_section = False
    section_indent = -1
    item_indent = -1

    for raw_line in lines:
        # strip trailing newline; preserve leading whitespace for indent calc
        line = raw_line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Leaving the section: a sibling key at <= section_indent that is not a list item.
        if in_section and indent <= section_indent and not stripped.startswith("- "):
            in_section = False
            section_indent = -1
            item_indent = -1
            # fall through to allow this line to start a new section if it matches

        if not in_section:
            if stripped.startswith(f"{section}:"):
                # `section: []` inline empty list → stays not-in-section
                rest = stripped[len(section) + 1:].strip()
                if rest in ("", "|", ">"):
                    in_section = True
                    section_indent = indent
                    item_indent = -1
                # rest like "[]" → no entries; do not enter
            continue

        # Inside the section
        if stripped.startswith("- "):
            inner = stripped[2:].strip()
            item_indent = indent
            if inner.startswith(f"{key}:"):
                value = inner[len(key) + 1:].strip().strip('"').strip("'")
                if value:
                    out.append(value)
            continue

        # Continuation field of the current list item
        if item_indent >= 0 and indent > item_indent and stripped.startswith(f"{key}:"):
            value = stripped[len(key) + 1:].strip().strip('"').strip("'")
            if value:
                out.append(value)

    return out


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./") if path else ""


def parse_delivery(delivery_text: str) -> dict:
    """Return {files_created, files_modified, tests_written} (each a list of
    normalized paths). Empty lists when fields are absent."""
    body = _extract_yaml_block(delivery_text, "delivery-body")
    if not body:
        return {"files_created": [], "files_modified": [], "tests_written": []}
    return {
        "files_created":  [_normalize(p) for p in _extract_list_field(body, "files_created", "path")],
        "files_modified": [_normalize(p) for p in _extract_list_field(body, "files_modified", "path")],
        "tests_written":  [_normalize(p) for p in _extract_list_field(body, "tests", "file")],
    }


# ── Diagnosis heuristics ───────────────────────────────────────────────────────

_BUILD_ERR_HINTS = (
    "syntaxerror", "cannot find module", "cannot find name",
    "ts1", "ts2", "ts5", "ts7",
    "is not assignable to type",
)
_SETUP_ERR_HINTS = (
    "econnrefused", "etimedout", "timeout", "before all", "beforeall",
    "fixture", "connection refused", "database", "afterall",
)
_CODE_ERR_HINTS = (
    "expected", "tobe", "toequal", "tomatch", "assertionerror", "tothrow",
)


def diagnose(failure: dict) -> dict:
    err_cls = (failure.get("error_class") or "").lower()
    err_msg = (failure.get("error_message") or "").lower()
    haystack = f"{err_cls} {err_msg}"

    if any(h in haystack for h in _BUILD_ERR_HINTS):
        cause = "build"
    elif any(h in haystack for h in _SETUP_ERR_HINTS):
        cause = "setup"
    elif any(h in haystack for h in _CODE_ERR_HINTS):
        cause = "code"
    else:
        cause = "code"

    return {
        "probable_cause": cause,
        "suggested_action": (failure.get("error_message") or "")[:240],
    }


# ── Regression-via-import (Stage B) ────────────────────────────────────────────

_IMPORT_RE = re.compile(r"""(?:from|import|require)\s*\(?['"]([^'"]+)['"]""")


def _collect_imports(test_file_abs: Path) -> set[str]:
    if not test_file_abs.exists() or not test_file_abs.is_file():
        return set()
    try:
        content = test_file_abs.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return {m.group(1) for m in _IMPORT_RE.finditer(content)}


def _import_resolves_to(import_spec: str, candidate: str) -> bool:
    """Heuristic: import "../users/service" matches candidate "src/users/service.ts"."""
    if not import_spec or not candidate:
        return False
    # strip extension and leading ./ ../
    spec = import_spec.replace("\\", "/")
    spec_tail = spec.rsplit("/", 1)[-1]
    cand = candidate.replace("\\", "/")
    cand_no_ext = re.sub(r"\.(ts|tsx|js|jsx|mjs|cjs)$", "", cand)
    cand_tail = cand_no_ext.rsplit("/", 1)[-1]
    return spec_tail == cand_tail and (spec.endswith(cand_no_ext) or cand_no_ext.endswith(spec.lstrip("./")))


# ── Main attribution ──────────────────────────────────────────────────────────

def attribute(manifest: dict, deliveries: list[dict], project_dir: Path,
              suite_run_dir: Path) -> tuple[dict, dict]:
    """
    Returns (updated_manifest, by_tc_slices_dict).
    by_tc_slices_dict: {task_id: slice_dict}
    """
    # Parse all delivery files once
    tc_info: dict[str, dict] = {}
    for entry in deliveries:
        tid = entry["task_id"]
        delivery_rel = entry["delivery_path"]
        delivery_abs = project_dir / delivery_rel
        if not delivery_abs.exists():
            tc_info[tid] = {
                "delivery_path": delivery_rel,
                "files_created": [],
                "files_modified": [],
                "tests_written": [],
                "_warning": "delivery_file_not_found",
            }
            continue
        try:
            text = delivery_abs.read_text(encoding="utf-8")
        except OSError as exc:
            tc_info[tid] = {
                "delivery_path": delivery_rel,
                "files_created": [],
                "files_modified": [],
                "tests_written": [],
                "_warning": f"unreadable: {exc}",
            }
            continue
        parsed = parse_delivery(text)
        parsed["delivery_path"] = delivery_rel
        tc_info[tid] = parsed

    # Reverse maps
    tests_written_index: dict[str, list[str]] = {}
    sources_index: dict[str, list[str]] = {}
    for tid, info in tc_info.items():
        for tw in info["tests_written"]:
            tests_written_index.setdefault(tw, []).append(tid)
        for src in info["files_created"] + info["files_modified"]:
            sources_index.setdefault(src, []).append(tid)

    # ── Build error attribution ──
    build = manifest.get("build") or {}
    build_errors = build.get("errors") or []
    build_attribution: dict[str, list[dict]] = {tid: [] for tid in tc_info}
    unattributed_build_errors: list[dict] = []

    for err in build_errors:
        err_file = _normalize(err.get("file") or "")
        owners = sources_index.get(err_file, [])
        if not owners:
            # try suffix match
            for src, src_owners in sources_index.items():
                if err_file and (err_file.endswith(src) or src.endswith(err_file)):
                    owners = src_owners
                    break
        if owners:
            for tid in owners:
                build_attribution[tid].append(err)
        else:
            unattributed_build_errors.append(err)

    build_failed = (build.get("result") == "failed")

    # ── Test failure attribution ──
    tests = manifest.get("tests") or {}
    failures = tests.get("failures") or []
    executed_test_files = set(tests.get("executed_test_files") or [])
    test_attribution: dict[str, list[dict]] = {tid: [] for tid in tc_info}
    unattributed_failures: list[dict] = []

    for failure in failures:
        test_file = _normalize(failure.get("test_file") or "")
        owners = tests_written_index.get(test_file, [])

        # Stage A — direct match (also try suffix match for resilience)
        attribution_reason = None
        if owners:
            attribution_reason = "test_in_tests_written"
        else:
            for tw, tw_owners in tests_written_index.items():
                if test_file and (test_file.endswith(tw) or tw.endswith(test_file)):
                    owners = tw_owners
                    attribution_reason = "test_in_tests_written"
                    break

        # Stage B — regression via import
        if not owners and test_file:
            test_abs = project_dir / test_file
            imports = _collect_imports(test_abs)
            stage_b_owners: set[str] = set()
            for imp in imports:
                for src, src_owners in sources_index.items():
                    if _import_resolves_to(imp, src):
                        for o in src_owners:
                            stage_b_owners.add(o)
            if stage_b_owners:
                owners = sorted(stage_b_owners)
                attribution_reason = "regression_via_import"

        diag = diagnose(failure)
        record = {
            "test_file": test_file,
            "test_name": failure.get("test_name", ""),
            "line": failure.get("line"),
            "error_class": failure.get("error_class"),
            "error_message": failure.get("error_message"),
            "attribution_reason": attribution_reason,
            "diagnosis": diag,
        }

        if owners:
            for tid in owners:
                test_attribution[tid].append(record)
        else:
            # Stage C — unattributed
            unattributed_failures.append({
                "test_file": test_file,
                "test_name": failure.get("test_name", ""),
                "error_class": failure.get("error_class"),
                "error_message": failure.get("error_message"),
                "diagnosis": diag,
            })

    has_unattributed = len(unattributed_failures) > 0

    # ── test_not_executed detection ──
    not_executed_per_tc: dict[str, list[str]] = {}
    if executed_test_files:
        for tid, info in tc_info.items():
            missing = [tw for tw in info["tests_written"] if tw and tw not in executed_test_files]
            # Try suffix match before flagging
            confirmed_missing = []
            for tw in missing:
                if any(ex.endswith(tw) or tw.endswith(ex) for ex in executed_test_files):
                    continue
                confirmed_missing.append(tw)
            if confirmed_missing:
                not_executed_per_tc[tid] = confirmed_missing

    # ── Build by-tc slices ──
    suite_run_id = manifest.get("suite_run_id", "")
    round_n = manifest.get("round", 1)
    by_tc_slices: dict[str, dict] = {}

    for tid, info in tc_info.items():
        my_build_errors = build_attribution.get(tid, [])
        my_failures = test_attribution.get(tid, [])
        my_not_executed = not_executed_per_tc.get(tid, [])

        # Determine test_gate_result
        if my_build_errors or build_failed:
            gate_result = "failed"
            cause = "build"
        elif has_unattributed:
            gate_result = "blocked_by_unattributed_failure"
            cause = "shared_environment"
        elif my_not_executed:
            gate_result = "failed"
            cause = "setup"
        elif my_failures:
            gate_result = "failed"
            cause = "code"
        else:
            gate_result = "passed"
            cause = None

        slice_doc = {
            "schema_version": "1",
            "suite_run_id": suite_run_id,
            "task_id": tid,
            "delivery_path": info.get("delivery_path", ""),
            "build_attribution": {
                "blocked_by_build": build_failed,
                "build_errors_in_my_files": my_build_errors,
            },
            "test_attribution": {
                "tests_written": info["tests_written"],
                "files_modified": info["files_modified"],
                "files_created": info["files_created"],
                "failures_attributed": my_failures,
                "tests_declared_but_not_executed": my_not_executed,
            },
            "test_gate_result": gate_result,
            "test_gate_cause": cause,
            "test_gate_round": round_n,
        }
        if "_warning" in info:
            slice_doc["_warning"] = info["_warning"]

        by_tc_slices[tid] = slice_doc

    # ── Update manifest attribution section ──
    manifest["attribution"] = {
        "method": "tests_written + files_modified + regression_via_import",
        "by_tc": {
            tid: f"by-tc/{tid}.json"
            for tid in tc_info
        },
        "unattributed_failures": unattributed_failures,
        "unattributed_build_errors": unattributed_build_errors,
        "shared_failures": [],
    }

    return manifest, by_tc_slices


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite-run-dir", required=True)
    ap.add_argument("--project-dir", default=os.environ.get("ORCH_PROJECT_DIR", "."))
    ap.add_argument("--deliveries", required=True,
                    help='JSON list: [{"task_id": "...", "delivery_path": "..."}, ...]')
    args = ap.parse_args()

    suite_run_dir = Path(args.suite_run_dir).resolve()
    project_dir = Path(args.project_dir).resolve()
    manifest_path = suite_run_dir / "manifest.json"

    if not manifest_path.exists():
        print(json.dumps({
            "status": "error", "reason": "manifest_not_found",
            "detail": str(manifest_path),
        }), file=sys.stderr)
        sys.exit(1)

    try:
        deliveries = json.loads(args.deliveries)
        if not isinstance(deliveries, list):
            raise ValueError("deliveries must be a JSON list")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "status": "error", "reason": "bad_deliveries",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    updated, by_tc = attribute(manifest, deliveries, project_dir, suite_run_dir)

    by_tc_dir = suite_run_dir / "by-tc"
    by_tc_dir.mkdir(parents=True, exist_ok=True)
    for tid, slice_doc in by_tc.items():
        (by_tc_dir / f"{tid}.json").write_text(
            json.dumps(slice_doc, indent=2) + "\n", encoding="utf-8")

    manifest_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "manifest": str(manifest_path),
        "by_tc_count": len(by_tc),
        "unattributed_test_failures": len(updated["attribution"]["unattributed_failures"]),
        "unattributed_build_errors": len(updated["attribution"]["unattributed_build_errors"]),
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "error", "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
