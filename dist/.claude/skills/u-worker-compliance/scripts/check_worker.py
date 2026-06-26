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
