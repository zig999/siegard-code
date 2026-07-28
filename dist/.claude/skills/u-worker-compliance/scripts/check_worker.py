#!/usr/bin/env python3
"""
Worker compliance validator.
Checks worker agent .md files for protocol violations before promotion to dist/.

Exit codes:
  0 — all files pass
  1 — one or more violations found
  2 — usage error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# prod-hardening task 03c: drop the pyyaml dependency (zero external deps invariant).
_LIB = Path(__file__).resolve().parents[3] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
import minimal_yaml  # noqa: E402


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    rule: str
    severity: str  # critical | error | warning
    detail: str
    line: int | None = None


@dataclass
class FileResult:
    file: str
    status: str  # pass | fail
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "status": self.status,
            "violations": [
                {k: v for k, v in {
                    "rule": v.rule,
                    "severity": v.severity,
                    "detail": v.detail,
                    **({"line": v.line} if v.line else {}),
                }.items()}
                for v in self.violations
            ],
        }


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter(content: str) -> dict:
    """Extracts YAML frontmatter between --- delimiters."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    try:
        parsed = minimal_yaml.load(content[3:end])
    except Exception:  # noqa: BLE001 — fail-soft on any parse error (matches prior behavior)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_orchestrator(path: Path) -> bool:
    return "orchestrator" in path.stem


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _check_w06_skills_frontmatter(content: str, path: Path) -> Violation | None:
    # Orchestrators coordinate workers but do not emit worker events — exempt from W06.
    if _is_orchestrator(path):
        return None
    fm = _parse_frontmatter(content)
    skills = fm.get("skills") or []
    if isinstance(skills, list) and "orch-report" not in skills:
        return Violation(
            rule="W06",
            severity="error",
            detail="'orch-report' missing from frontmatter skills list — emit.py may not be available",
        )
    return None


def _check_w03_no_terminal_event(content: str, path: Path) -> Violation | None:
    if _is_orchestrator(path):
        return None
    has_completed = bool(re.search(r"--kind\s+completed", content))
    has_failed = bool(re.search(r"--kind\s+failed", content))
    if not has_completed and not has_failed:
        return Violation(
            rule="W03",
            severity="critical",
            detail="No --kind completed or --kind failed emit.py call found — on_subagent_stop.py will synthesize task_failed once the worker is silent past its stale threshold",
        )
    return None


def _extract_data_str(block: str) -> str:
    """Extracts the JSON payload from --data '...' or --data "..." (handles escaped quotes)."""
    # Single-quoted: --data '...'
    m = re.search(r"--data\s+'([^']*)'", block)
    if m:
        return m.group(1)
    # Double-quoted with backslash escapes: --data "{...}"
    m = re.search(r'--data\s+"((?:[^"\\]|\\.)*)"', block)
    if m:
        return m.group(1)
    return ""


def _check_w01_completed_fields(content: str, path: Path) -> list[Violation]:
    if _is_orchestrator(path):
        return []
    violations: list[Violation] = []
    for m in re.finditer(r"--kind\s+completed(.{0,500}?)(?=\n```|\Z)", content, re.DOTALL):
        block = m.group(0)
        data_str = _extract_data_str(block)
        if not data_str:
            continue
        line_num = content[: m.start()].count("\n") + 1
        for field_name in ("phase", "artifacts"):
            if f'"{field_name}"' not in data_str and f'\\"' + field_name + '\\"' not in data_str:
                violations.append(Violation(
                    rule="W01",
                    severity="error",
                    detail=f"task_completed emit missing required field: {field_name}",
                    line=line_num,
                ))
    return violations


def _check_w02_failed_fields(content: str, path: Path) -> list[Violation]:
    if _is_orchestrator(path):
        return []
    violations: list[Violation] = []
    for m in re.finditer(r"--kind\s+failed(.{0,500}?)(?=\n```|\Z)", content, re.DOTALL):
        block = m.group(0)
        data_str = _extract_data_str(block)
        if not data_str:
            continue
        line_num = content[: m.start()].count("\n") + 1
        for field_name in ("phase", "reason", "retryable"):
            if f'"{field_name}"' not in data_str and f'\\"' + field_name + '\\"' not in data_str:
                violations.append(Violation(
                    rule="W02",
                    severity="error",
                    detail=f"task_failed emit missing required field: {field_name}",
                    line=line_num,
                ))
    return violations


def _check_w04_default_phase(content: str, path: Path) -> list[Violation]:
    violations: list[Violation] = []
    # Matches both "phase":"default" and \"phase\":\"default\"
    patterns = [
        re.compile(r'"phase"\s*:\s*"default"'),
        re.compile(r'\\"phase\\"\s*:\s*\\"default\\"'),
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, content):
            line_num = content[: m.start()].count("\n") + 1
            violations.append(Violation(
                rule="W04",
                severity="error",
                detail='Hardcoded non-canonical phase value "default" — use a canonical phase (sdd, dev, review, test) or a runtime variable',
                line=line_num,
            ))
    return violations


def _check_w05_register_worker_phase(content: str, path: Path) -> list[Violation]:
    if not _is_orchestrator(path):
        return []
    violations: list[Violation] = []
    # Match register_worker( but NOT unregister_worker(
    for m in re.finditer(r"(?<!\w)register_worker\s*\(", content):
        start = m.end() - 1
        depth = 0
        end = start
        for i, ch in enumerate(content[start:], start=start):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        call_str = content[start : end + 1]
        if "phase=" not in call_str:
            line_num = content[: m.start()].count("\n") + 1
            violations.append(Violation(
                rule="W05",
                severity="error",
                detail="register_worker call missing phase= argument — on_subagent_stop.py will fall back to full log replay",
                line=line_num,
            ))
    return violations


# ---------------------------------------------------------------------------
# W08 — gate fields must be declared in the producing worker's protocol
#
# Origin: `documentation_verified` was required by
# `check_documentation_verified.py` and documented ONLY in the qa-report
# template. The QA worker delivered the review, omitted the field, and the
# phase blocked with E08 — work complete, record incomplete, one human
# round-trip burned. A requirement that lives only in a file the agent is
# expected to open is a requirement with a recurring failure mode.
#
# This registry is the artifact -> checker contract, in one place. Adding a
# field to a checker without adding it here (and to the worker) fails the gate.
# ---------------------------------------------------------------------------

GATE_FIELDS_BY_WORKER: dict[str, list[tuple[str, str]]] = {
    # worker stem -> [(field, checker that reads it)]
    "u-be-qa": [
        ("verdict", "check_all_qa_verdicts_approved.py"),
        ("documentation_verified", "check_documentation_verified.py"),
    ],
    "u-fe-qa": [
        ("verdict", "check_all_qa_verdicts_approved.py"),
        ("documentation_verified", "check_documentation_verified.py"),
    ],
    "u-be-developer": [("qa_ready", "check_all_deliveries_qa_ready.py")],
    "u-fe-developer": [("qa_ready", "check_all_deliveries_qa_ready.py")],
    "u-test-runner": [("result", "check_all_tests_passed.py")],
}


def _check_w08_gate_fields_declared(content: str, path: Path) -> list[Violation]:
    required = GATE_FIELDS_BY_WORKER.get(path.stem)
    if not required:
        return []
    violations: list[Violation] = []
    for field_name, checker in required:
        # Word-boundary match so `documentation_verified` is not satisfied by a
        # longer identifier that merely contains it.
        if not re.search(rf"(?<![\w-]){re.escape(field_name)}(?![\w-])", content):
            violations.append(Violation(
                rule="W08",
                severity="error",
                detail=(
                    f"gate field '{field_name}' is read by {checker} but never named in this "
                    f"worker's protocol — the worker can complete without writing it and block "
                    f"the phase with E08"
                ),
            ))
    return violations


# ---------------------------------------------------------------------------
# W09 — a review-only worker must not register the artifact it reviewed
#
# Origin: a reviewer that had reported two Major issues was retried over
# unchanged input, edited the two spec files under review, downgraded its own
# findings to "minor", approved the result, and registered both spec files as
# its artifacts. Nothing reviewed that change. emit.py now refuses such a path
# at runtime (R02c); this rule refuses the same thing in the agent's own
# documented contract, so the definition can never invite it.
# ---------------------------------------------------------------------------

REVIEW_ONLY_WORKERS: frozenset[str] = frozenset({"u-spec-reviewer"})
_REVIEWED_ARTIFACT_MARKER = "domains/"


def _check_w09_review_only_artifacts(content: str, path: Path) -> list[Violation]:
    if path.stem not in REVIEW_ONLY_WORKERS:
        return []
    violations: list[Violation] = []
    for m in re.finditer(r'"artifacts"\s*:\s*\[([^\]]*)\]', content):
        entry = m.group(1)
        if _REVIEWED_ARTIFACT_MARKER in entry.replace("\\", "/"):
            violations.append(Violation(
                rule="W09",
                severity="critical",
                detail=(
                    f"{path.stem} is a review-only worker but its contract registers an "
                    f"artifact under '{_REVIEWED_ARTIFACT_MARKER}' — that is the artifact "
                    "under review, not a review output. Separation of duties: report the "
                    "issues and let the writer apply them"
                ),
                line=content[: m.start()].count("\n") + 1,
            ))
    return violations


# ---------------------------------------------------------------------------
# W10 — the description must gate dispatch, not advertise capability
#
# Origin (v2.34.0 flow-discipline incident): a downstream host session offered
# to execute the SDD flow inline — "write the spec insertions, regenerate the
# manifest, run the five gates" — instead of routing through /u-improve. Agent
# descriptions are the host model's auto-delegation routing signal; a
# capability-only description ("Initial spec author. Transforms natural
# language requirements into OpenAPI contracts...") is bait for exactly that
# bypass. Every non-entry-point agent must therefore open its description with
# a dispatch gate: who exclusively spawns it, plus "never invoke directly" and
# the entry command to use instead. The gate clause comes FIRST — it is the
# part the routing decision reads.
# ---------------------------------------------------------------------------

# Agents that ARE legitimate direct-invocation entry points (commands route to
# them via the Agent tool): the meta-orchestrator and the reverse-spec pipeline
# orchestrator. Everything else is dispatched by an orchestrator or a command
# and must gate its description.
ENTRY_POINT_AGENTS: frozenset[str] = frozenset({"orchestrator", "orchestrator-reverse-spec"})

_W10_DISPATCH_RE = re.compile(r"(?:spawned|activated|dispatched)\s+exclusively\s+by", re.IGNORECASE)
_W10_NEVER_RE = re.compile(r"never\s+invoke\s+directly", re.IGNORECASE)


def _check_w10_description_gate(content: str, path: Path) -> list[Violation]:
    if path.stem in ENTRY_POINT_AGENTS:
        return []
    fm = _parse_frontmatter(content)
    desc = fm.get("description")
    if not isinstance(desc, str):
        desc = "" if desc is None else str(desc)
    violations: list[Violation] = []
    if not _W10_DISPATCH_RE.search(desc):
        violations.append(Violation(
            rule="W10",
            severity="error",
            detail=(
                "description missing the dispatch-gate clause ('Spawned exclusively by "
                "<dispatcher>') — descriptions are the host model's auto-delegation "
                "routing signal; a capability-only description invites direct invocation "
                "that bypasses claim/triage/validation"
            ),
        ))
    if not _W10_NEVER_RE.search(desc):
        violations.append(Violation(
            rule="W10",
            severity="error",
            detail=(
                "description missing 'never invoke directly' + the entry command to "
                "route through (/u-spec, /u-improve, /u-dev, /u-drift, ...) — a blocked "
                "path without a signposted correct door produces workarounds, not "
                "compliance"
            ),
        ))
    return violations


# ---------------------------------------------------------------------------
# W11 — env-dependent scripts must be invoked with inline env
#
# Origin (v2.35.1 / mwoassistant field incident): the orchestrator-sdd protocol
# exported SPECS_DIR in one bash block and invoked record_spec_baseline.py in a
# LATER block — but each Bash tool call is a fresh shell, so the export never
# reached the script, which fell back to the env default ("specs") while the
# target's CLAUDE.md declared docs/specs. The adoption baseline was recorded
# EMPTY, guaranteeing PROV false positives for the whole workflow. The scripts
# now self-resolve via orch_core.resolve_specs_dir (defense one); this rule is
# defense two: any invocation of an env-dependent script in an agent protocol
# must carry inline env on the SAME command line, so the intent survives the
# shell boundary regardless.
# ---------------------------------------------------------------------------

ENV_DEPENDENT_SCRIPTS: frozenset[str] = frozenset({
    "record_spec_baseline.py",
    "generate_handoff_manifest.py",
    "check_handoff_manifest_approved.py",
    "check_sdd_artifacts_committed.py",
})

_W11_INLINE_ENV_RE = re.compile(r"\bORCH_PROJECT_DIR=")


def _check_w11_inline_env(content: str, path: Path) -> list[Violation]:
    violations: list[Violation] = []
    for lineno, line in enumerate(content.splitlines(), 1):
        if "python3" not in line:
            continue  # prose mentions and comments without an invocation
        for script in ENV_DEPENDENT_SCRIPTS:
            if script in line and not _W11_INLINE_ENV_RE.search(line):
                violations.append(Violation(
                    rule="W11",
                    severity="error",
                    detail=(
                        f"{script} invoked without inline env (ORCH_PROJECT_DIR=... on the "
                        "same line) — exports do not survive across Bash tool calls; an "
                        "invocation relying on an earlier block resolves against the wrong "
                        "tree (the v2.35.0 empty-baseline incident)"
                    ),
                    line=lineno,
                ))
    return violations


# ---------------------------------------------------------------------------
# Single file validation
# ---------------------------------------------------------------------------

def check_file(path: Path) -> FileResult:
    content = path.read_text(encoding="utf-8")
    violations: list[Violation] = []

    v = _check_w06_skills_frontmatter(content, path)
    if v:
        violations.append(v)

    v = _check_w03_no_terminal_event(content, path)
    if v:
        violations.append(v)

    violations.extend(_check_w01_completed_fields(content, path))
    violations.extend(_check_w02_failed_fields(content, path))
    violations.extend(_check_w04_default_phase(content, path))
    violations.extend(_check_w05_register_worker_phase(content, path))
    violations.extend(_check_w08_gate_fields_declared(content, path))
    violations.extend(_check_w09_review_only_artifacts(content, path))
    violations.extend(_check_w10_description_gate(content, path))
    violations.extend(_check_w11_inline_env(content, path))

    return FileResult(
        file=str(path),
        status="fail" if violations else "pass",
        violations=violations,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _collect_files(args: argparse.Namespace) -> list[Path]:
    files: list[Path] = []
    if args.file:
        p = Path(args.file)
        if not p.exists():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            sys.exit(2)
        files.append(p)
    if args.dir:
        d = Path(args.dir)
        if not d.is_dir():
            print(f"ERROR: not a directory: {d}", file=sys.stderr)
            sys.exit(2)
        files.extend(sorted(d.rglob("*.md")))
    return files


def _format_human(results: list[FileResult]) -> str:
    lines: list[str] = []
    for r in results:
        icon = "✓" if r.status == "pass" else "✗"
        lines.append(f"{icon} {r.file}")
        for v in r.violations:
            loc = f" (line {v.line})" if v.line else ""
            lines.append(f"  [{v.severity.upper()}] {v.rule}{loc}: {v.detail}")
    total = len(results)
    failed = sum(1 for r in results if r.status == "fail")
    lines.append(f"\n{total} file(s) checked — {failed} failed, {total - failed} passed")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate worker agent .md files for protocol compliance"
    )
    parser.add_argument("--file", metavar="PATH", help="single file to validate")
    parser.add_argument("--dir", metavar="DIR", help="directory to scan recursively for *.md files")
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        help="output format (default: human)",
    )
    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.print_help()
        sys.exit(2)

    files = _collect_files(args)
    if not files:
        print("No .md files found.", file=sys.stderr)
        sys.exit(0)

    results = [check_file(f) for f in files]

    if args.format == "json":
        # A7: emit JSON (the project's universal machine contract). The prior
        # `yaml.dump` referenced a module no longer imported (pyyaml was dropped in
        # task 03c) and crashed with NameError on any --format yaml call.
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print(_format_human(results))

    if any(r.status == "fail" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
