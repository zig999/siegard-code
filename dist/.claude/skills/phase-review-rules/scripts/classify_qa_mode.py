#!/usr/bin/env python3
"""
classify_qa_mode.py — Classify a review task into a qa_mode based on signals
already available to orchestrator-review at task creation.

The qa_mode controls:
  - which Phase 1/2/3 steps the QA worker runs
  - how many tasks of this kind the orchestrator dispatches concurrently
  - whether the auto-approval gate (Step 5.0) can fire

Decision tree (highest precedence first):
  full      if has_nfr OR touches_security OR touches_public_api
  micro     if workflow_type == improve AND dev_impact == narrow
            AND changed_files_count <= 2 AND tc_type in (Bugfix, Refactoring)
  standard  otherwise

Concurrency hints by mode: micro=5, standard=3, full=2.

Usage:
    python3 classify_qa_mode.py \
      --workflow-type improve|standard|reverse-spec|unknown \
      --dev-impact narrow|moderate|wide|unknown \
      [--changed-files-count <int>] \
      [--tc-type Bugfix|Refactoring|Enhancement|NewFeature|unknown] \
      --delivery-path <rel path under project-dir> \
      [--project-dir <abs path>]

Output (stdout, exit 0):
    {
      "qa_mode": "micro"|"standard"|"full",
      "concurrency_hint": int,
      "rationale": "<one-line decision trace>",
      "signals": {
        "workflow_type": "...",
        "dev_impact": "...",
        "tc_type": "...",
        "changed_files_count": int,
        "has_nfr": bool,
        "touches_security": bool,
        "touches_public_api": bool,
        "matched_security_paths": [...],
        "matched_public_api_paths": [...]
      }
    }

Output (exit 1, stderr):
    {"status": "error", "reason": "<code>", "detail": "..."}
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


# ── Delivery YAML extraction (kept minimal; mirrors attribute_failures.py) ─────

_YAML_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


def _extract_yaml_block(content: str, marker: str) -> str:
    for match in _YAML_FENCE_RE.finditer(content):
        block = match.group(1)
        first = next((ln for ln in block.splitlines() if ln.strip()), "").strip()
        if first.startswith(f"# {marker}"):
            return block
    return ""


def _extract_list_field(yaml_text: str, section: str, key: str) -> list[str]:
    out: list[str] = []
    in_section = False
    section_indent = -1
    item_indent = -1
    for raw_line in yaml_text.splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if in_section and indent <= section_indent and not stripped.startswith("- "):
            in_section = False
            section_indent = -1
            item_indent = -1
        if not in_section:
            if stripped.startswith(f"{section}:"):
                rest = stripped[len(section) + 1:].strip()
                if rest in ("", "|", ">"):
                    in_section = True
                    section_indent = indent
                    item_indent = -1
            continue
        if stripped.startswith("- "):
            inner = stripped[2:].strip()
            item_indent = indent
            if inner.startswith(f"{key}:"):
                value = inner[len(key) + 1:].strip().strip('"').strip("'")
                if value:
                    out.append(value)
            continue
        if item_indent >= 0 and indent > item_indent and stripped.startswith(f"{key}:"):
            value = stripped[len(key) + 1:].strip().strip('"').strip("'")
            if value:
                out.append(value)
    return out


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("./") if p else ""


# ── Scope detectors ───────────────────────────────────────────────────────────

# Case-insensitive substring matches on the normalized path.
_SECURITY_HINTS = (
    "auth", "security", "credential", "token", "permission",
    "acl", "rbac", "session", "oauth", "saml", "jwt",
)

_PUBLIC_API_HINTS = (
    "controller", "route", "router", "handler",
    "openapi", "swagger", "api/",
)

_NFR_GATE_RE = re.compile(r"^\s*nfr_results\s*:", re.MULTILINE)


def _has_nfr(delivery_text: str) -> bool:
    """A non-commented `nfr_results:` field in either YAML block indicates the
    Developer measured at least one NFR — i.e., the TC has NFR scope."""
    # Strip commented lines first so we don't false-positive on
    # `# nfr_results:` template hints.
    stripped = "\n".join(
        ln for ln in delivery_text.splitlines() if not ln.lstrip().startswith("#")
    )
    return bool(_NFR_GATE_RE.search(stripped))


def _matches(path: str, hints: tuple[str, ...]) -> bool:
    pl = path.lower()
    return any(h in pl for h in hints)


def _scan_paths(paths: list[str], hints: tuple[str, ...]) -> list[str]:
    return [p for p in paths if _matches(p, hints)]


# ── Decision ──────────────────────────────────────────────────────────────────

CONCURRENCY = {"micro": 5, "standard": 3, "full": 2}


def classify(workflow_type: str, dev_impact: str, tc_type: str,
             changed_files_count: int, delivery_text: str) -> dict:
    body = _extract_yaml_block(delivery_text, "delivery-body")
    files_created = [_normalize_path(p) for p in _extract_list_field(body, "files_created", "path")]
    files_modified = [_normalize_path(p) for p in _extract_list_field(body, "files_modified", "path")]
    all_paths = files_created + files_modified

    if changed_files_count < 0:
        changed_files_count = len(all_paths)

    has_nfr = _has_nfr(delivery_text)
    sec_matches = _scan_paths(all_paths, _SECURITY_HINTS)
    api_matches = _scan_paths(all_paths, _PUBLIC_API_HINTS)
    touches_security = bool(sec_matches)
    touches_public_api = bool(api_matches)

    signals = {
        "workflow_type": workflow_type,
        "dev_impact": dev_impact,
        "tc_type": tc_type,
        "changed_files_count": changed_files_count,
        "has_nfr": has_nfr,
        "touches_security": touches_security,
        "touches_public_api": touches_public_api,
        "matched_security_paths": sec_matches,
        "matched_public_api_paths": api_matches,
    }

    # Highest-precedence: anything that warrants `full`.
    if has_nfr or touches_security or touches_public_api:
        reasons = []
        if has_nfr:
            reasons.append("has_nfr")
        if touches_security:
            reasons.append(f"touches_security({len(sec_matches)})")
        if touches_public_api:
            reasons.append(f"touches_public_api({len(api_matches)})")
        return {
            "qa_mode": "full",
            "concurrency_hint": CONCURRENCY["full"],
            "rationale": "full: " + ", ".join(reasons),
            "signals": signals,
        }

    # Micro path requires every condition to hold.
    micro_eligible = (
        workflow_type == "improve"
        and dev_impact == "narrow"
        and changed_files_count <= 2
        and tc_type in ("Bugfix", "Refactoring")
    )
    if micro_eligible:
        return {
            "qa_mode": "micro",
            "concurrency_hint": CONCURRENCY["micro"],
            "rationale": (
                "micro: improve flow, narrow impact, "
                f"{changed_files_count} files, type={tc_type}"
            ),
            "signals": signals,
        }

    # Default.
    fail_reasons = []
    if workflow_type != "improve":
        fail_reasons.append(f"workflow={workflow_type}")
    if dev_impact != "narrow":
        fail_reasons.append(f"impact={dev_impact}")
    if changed_files_count > 2:
        fail_reasons.append(f"files={changed_files_count}")
    if tc_type not in ("Bugfix", "Refactoring"):
        fail_reasons.append(f"type={tc_type}")
    return {
        "qa_mode": "standard",
        "concurrency_hint": CONCURRENCY["standard"],
        "rationale": "standard: micro path failed (" + ", ".join(fail_reasons) + ")",
        "signals": signals,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-type", default="unknown",
                    choices=["improve", "standard", "reverse-spec", "unknown"])
    ap.add_argument("--dev-impact", default="unknown",
                    choices=["narrow", "moderate", "wide", "unknown"])
    ap.add_argument("--changed-files-count", type=int, default=-1)
    ap.add_argument("--tc-type", default="unknown",
                    choices=["Bugfix", "Refactoring", "Enhancement",
                             "NewFeature", "unknown"])
    ap.add_argument("--delivery-path", required=True)
    ap.add_argument("--project-dir",
                    default=os.environ.get("ORCH_PROJECT_DIR", "."))
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    delivery_abs = (project_dir / args.delivery_path).resolve()

    if not delivery_abs.exists():
        print(json.dumps({
            "status": "error",
            "reason": "delivery_not_found",
            "detail": str(delivery_abs),
        }), file=sys.stderr)
        sys.exit(1)

    delivery_text = delivery_abs.read_text(encoding="utf-8", errors="replace")
    result = classify(
        workflow_type=args.workflow_type,
        dev_impact=args.dev_impact,
        tc_type=args.tc_type,
        changed_files_count=args.changed_files_count,
        delivery_text=delivery_text,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
