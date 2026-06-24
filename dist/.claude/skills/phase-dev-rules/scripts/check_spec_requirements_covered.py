#!/usr/bin/env python3
"""
check_spec_requirements_covered.py — Exit criterion: dev / spec_requirements_covered.

Rec A (SIEGARD "incomplete requirements" remediation). Closes the upstream leak
the field analysis identified: there is no gate verifying that every requirement
captured in the specs is actually decomposed into a Task Contract. The planner can
silently under-scope — a UC or feature defined in an in-play spec ends up owned by
no TC — and nothing downstream notices until the feature ships incomplete.

This gate blocks the dev→review transition while any requirement DEFINED in a spec
that the backlog references is NOT covered by any Task Contract.

Coverage model (deterministic, low false-positive):
  - Required IDs = `UC-NN` defined in referenced `*.spec.md` + `FEAT-NN` defined in
    referenced `*.feature.spec.md`. Only specs the backlog's TCs actually reference
    are in scope (a UC in an in-play spec that no TC covers is the real gap).
  - An ID is COVERED when it appears anywhere in the backlog (a TC's `origin`,
    `bdd_ref`, objective, or references). Lenient on purpose: a UC folded into a
    sibling TC is fine; the gate only fires on a requirement NO TC mentions at all.
  - `BR-NN` is reported informationally (it lives in TC prose, not a structured
    field — too fragile to block on), surfaced as evidence.br_not_referenced.

Applicability: ENFORCED only for standard/greenfield flows. Improve flows and
synthesized backlogs intentionally scope to a subset of a spec's requirements, so
full-spec UC coverage is the wrong denominator — the gate returns met=true with an
explanatory reason for those.

Fail-open when there is nothing to verify (no backlog, no referenced specs) — the
gate is additive and must never break a pipeline that has no plan to check.

Output schema (per GATE_SCHEMA_UNIFORMITY): always {status, check, timestamp};
legacy {criterion, met, evidence} preserved for orchestrator-dev compatibility.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_CLAUDE_DIR = Path(__file__).resolve().parents[3]
_LIB = _CLAUDE_DIR / "lib"
sys.path.insert(0, str(_LIB))

try:
    from orch_core import TaskStatus, reduce_all
except ImportError as exc:
    print(json.dumps({
        "status": "error",
        "reason": "internal_error",
        "detail": f"cannot import orch_core: {exc}",
    }), file=sys.stderr)
    sys.exit(1)

CRITERION_ID = "spec_requirements_covered"
PHASE_NAME = "dev"
_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_SPECS_DIR = os.environ.get("SPECS_DIR", "specs")

_UC_RE = re.compile(r"\bUC-\d+\b")
_FEAT_RE = re.compile(r"\bFEAT-\d+\b")
_BR_RE = re.compile(r"\bBR-\d+\b")
_SPEC_PATH_RE = re.compile(r"[^\s\"']+\.(?:feature\.spec|spec|back)\.md")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _result(met: bool, evidence: dict) -> dict:
    return {
        "status": "ok" if met else "blocked",
        "check": CRITERION_ID,
        "timestamp": _now(),
        "criterion": CRITERION_ID,
        "met": met,
        "evidence": evidence,
    }


def _find_backlog(state) -> Path | None:
    """Locate the merged backlog.json via a completed dev planning task's artifacts.

    Prefer an artifact named exactly backlog.json; fall back to any *backlog*.json.
    """
    candidates: list[str] = []
    for task in state.tasks.values():
        if task.phase != PHASE_NAME or task.status != TaskStatus.COMPLETED:
            continue
        for artifact in task.artifacts:
            name = Path(artifact).name.lower()
            if "backlog" in name and name.endswith(".json"):
                candidates.append(artifact)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (Path(p).name.lower() != "backlog.json", p))
    resolved = _PROJECT_DIR / candidates[0]
    return resolved if resolved.exists() else None


def _walk_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_strings(v)


def _is_applicable(backlog, triage_path: Path | None) -> tuple[bool, str]:
    """Returns (applicable, reason). Improve / synthesized flows are out of scope."""
    if triage_path and triage_path.exists():
        try:
            triage = json.loads(triage_path.read_text(encoding="utf-8"))
            trigger = str(triage.get("trigger", triage.get("trigger_type", ""))).lower()
            if "improve" in trigger or triage.get("planner_required") is False:
                return False, "improve_flow_scoped"
        except (OSError, json.JSONDecodeError):
            pass
    # Synthesized backlog shape: simple task dicts without the structured contract.
    entries = backlog if isinstance(backlog, list) else [backlog]
    structured = any(
        isinstance(e, dict) and ("execution_contract" in e or "task_contract" in e or "origin" in e)
        for e in entries
    )
    if not structured:
        return False, "synthesized_backlog_no_contract"
    return True, "standard_flow"


def _resolve_spec(path_str: str) -> Path | None:
    raw = path_str.replace("{SPECS_DIR}", _SPECS_DIR)
    for candidate in (_PROJECT_DIR / raw, Path(raw)):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _referenced_specs(backlog) -> list[Path]:
    override = os.environ.get("ORCH_COVERAGE_SPEC_PATHS", "")
    if override.strip():
        names = [s.strip() for s in override.split(",") if s.strip()]
        return [p for p in (_resolve_spec(n) for n in names) if p]
    seen: dict[str, Path] = {}
    for s in _walk_strings(backlog):
        for m in _SPEC_PATH_RE.findall(s):
            resolved = _resolve_spec(m)
            if resolved and str(resolved) not in seen:
                seen[str(resolved)] = resolved
    return list(seen.values())


def _ids_defined(spec_paths: list[Path], pattern: re.Pattern, suffix_filter) -> dict[str, set]:
    """Map id -> set of spec files that define it, for specs matching suffix_filter."""
    out: dict[str, set] = {}
    for path in spec_paths:
        if not suffix_filter(path.name.lower()):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for ident in set(pattern.findall(text)):
            out.setdefault(ident, set()).add(path.name)
    return out


def evaluate() -> dict:
    state = reduce_all()
    backlog_path = _find_backlog(state)
    if backlog_path is None:
        return _result(True, {"applicable": False, "reason": "no_backlog_found"})

    try:
        backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _result(False, {"applicable": True, "reason": "backlog_unreadable",
                               "backlog": str(backlog_path), "detail": str(exc)})

    session_dir = backlog_path.parent.parent
    triage_path = session_dir / "triage.json"
    applicable, reason = _is_applicable(backlog, triage_path)
    if not applicable:
        return _result(True, {"applicable": False, "reason": reason,
                              "backlog": str(backlog_path.relative_to(_PROJECT_DIR))
                              if backlog_path.is_relative_to(_PROJECT_DIR) else str(backlog_path)})

    spec_paths = _referenced_specs(backlog)
    if not spec_paths:
        return _result(True, {"applicable": False, "reason": "no_referenced_specs"})

    backlog_text = json.dumps(backlog)
    covered = set(_UC_RE.findall(backlog_text)) | set(_FEAT_RE.findall(backlog_text))

    uc_defs = _ids_defined(spec_paths, _UC_RE,
                           lambda n: n.endswith(".spec.md") and not n.endswith(".feature.spec.md"))
    feat_defs = _ids_defined(spec_paths, _FEAT_RE, lambda n: n.endswith(".feature.spec.md"))
    br_defs = _ids_defined(spec_paths, _BR_RE, lambda n: n.endswith(".back.md"))

    uncovered_uc = sorted(uc for uc in uc_defs if uc not in covered)
    uncovered_feat = sorted(f for f in feat_defs if f not in covered)
    br_not_referenced = sorted(b for b in br_defs if b not in backlog_text)

    met = not uncovered_uc and not uncovered_feat
    return _result(met, {
        "applicable": True,
        "reason": "standard_flow",
        "backlog": str(backlog_path.relative_to(_PROJECT_DIR))
        if backlog_path.is_relative_to(_PROJECT_DIR) else str(backlog_path),
        "referenced_specs": [p.name for p in spec_paths],
        "required_uc": sorted(uc_defs),
        "required_feat": sorted(feat_defs),
        "uncovered_uc": uncovered_uc,
        "uncovered_feat": uncovered_feat,
        "br_not_referenced": br_not_referenced,  # informational — does NOT block
    })


def main() -> None:
    result = evaluate()
    print(json.dumps(result))
    if result.get("status") == "blocked":
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        print(json.dumps({
            "status": "error",
            "reason": "log_missing",
            "detail": "orchestration log not found — run orchestrator first",
        }), file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "error",
            "reason": "internal_error",
            "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
