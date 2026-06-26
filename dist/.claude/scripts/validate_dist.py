#!/usr/bin/env python3
"""
Validates consistency of dist/.claude/ artifacts.

Checks:
  1. All --event-type <value> refs in .md files exist in orch_core.EventType
  2. All keys in _REQUIRED_DATA_FIELDS are valid EventType values (no orphaned entries)
  3. Warns about EventType values with no _REQUIRED_DATA_FIELDS entry (likely missing schema)
  4. All event_type string refs in .py hooks and scripts match orch_core.EventType

Usage:
  python3 .claude/scripts/validate_dist.py
  python3 .claude/scripts/validate_dist.py --strict   # treat warnings as errors

Exit codes: 0 = clean, 1 = errors (or warnings in --strict mode).
"""
import json
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_DIST_CLAUDE = _SCRIPTS_DIR.parent
_LIB_DIR = _DIST_CLAUDE / "lib"
sys.path.insert(0, str(_LIB_DIR))

try:
    from orch_core import EventType, _REQUIRED_DATA_FIELDS  # type: ignore[attr-defined]
except ImportError as exc:
    print(f"ERROR: cannot import orch_core from {_LIB_DIR}: {exc}", file=sys.stderr)
    sys.exit(1)

_AGENTS_DIR = _DIST_CLAUDE / "agents"
_COMMANDS_DIR = _DIST_CLAUDE / "commands"
_SKILLS_DIR = _DIST_CLAUDE / "skills"
_HOOKS_DIR = _DIST_CLAUDE / "hooks"

# EventType values that intentionally have no _REQUIRED_DATA_FIELDS entry.
# These EventType values intentionally have no _REQUIRED_DATA_FIELDS entry:
# - snapshot, log_recovered: audit/recovery markers; payload varies by context
# - task_progress: heartbeat; only requires "phase" and "note" which are optional by design
# - preflight_failed: emitted by infra scripts; schema validated by those scripts, not append.py
_SCHEMA_EXEMPT = frozenset({"snapshot", "log_recovered", "task_progress", "preflight_failed"})


def _scan_md_event_types(directories: list[Path]) -> dict[str, list[str]]:
    """Return {event_type_value: [relative_path, ...]} for all --event-type refs in .md files."""
    pattern = re.compile(r'--event-type\s+([a-z_]+)')
    usage: dict[str, list[str]] = {}
    for directory in directories:
        if not directory.exists():
            continue
        for md_file in directory.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8", errors="replace")
            for match in pattern.finditer(content):
                et = match.group(1)
                rel = str(md_file.relative_to(_DIST_CLAUDE))
                usage.setdefault(et, []).append(rel)
    return usage


def _scan_py_event_types(directories: list[Path]) -> dict[str, list[str]]:
    """Return {event_type_value: [relative_path, ...]} for event_type string refs in .py files."""
    pattern = re.compile(r'event_type\s*=\s*["\']([a-z_]+)["\']')
    usage: dict[str, list[str]] = {}
    for directory in directories:
        if not directory.exists():
            continue
        for py_file in directory.rglob("*.py"):
            if py_file.name == "orch_core.py":
                continue  # skip source of truth
            content = py_file.read_text(encoding="utf-8", errors="replace")
            for match in pattern.finditer(content):
                et = match.group(1)
                rel = str(py_file.relative_to(_DIST_CLAUDE))
                usage.setdefault(et, []).append(rel)
    return usage


def _check_exit_criteria_scripts(skills_dir: Path) -> list[str]:
    """Structural check (task 11, A5-F6): every phase-*-rules/exit-criteria.json
    parses as JSON and each criterion's `script` exists on disk. Returns errors."""
    errs: list[str] = []
    if not skills_dir.exists():
        return errs
    for ec in sorted(skills_dir.glob("phase-*-rules/exit-criteria.json")):
        try:
            data = json.loads(ec.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errs.append(f"{ec.parent.name}/exit-criteria.json: invalid JSON ({exc})")
            continue
        skill_dir = ec.parent
        for crit in data.get("criteria", []):
            script = crit.get("script")
            if not script:
                errs.append(f"{ec.parent.name}: criterion {crit.get('id')!r} has no 'script'")
            elif not (skill_dir / script).exists():
                errs.append(f"{ec.parent.name}: criterion {crit.get('id')!r} script not found: {script}")
    return errs


def main(strict: bool = False) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    valid_types: frozenset[str] = EventType.values()
    required_keys: set[str] = set(_REQUIRED_DATA_FIELDS.keys())

    print(f"orch_core.py  EventType          : {len(valid_types)} values")
    print(f"              _REQUIRED_DATA_FIELDS: {len(required_keys)} entries")

    # Check 1: _REQUIRED_DATA_FIELDS keys are all valid EventType values
    orphaned = required_keys - valid_types
    for key in sorted(orphaned):
        errors.append(
            f"_REQUIRED_DATA_FIELDS key '{key}' is NOT a valid EventType value "
            f"(remove or add to EventType enum)"
        )

    # Check 2: every EventType value has a schema entry (warn if missing and not exempt)
    uncovered = valid_types - required_keys - _SCHEMA_EXEMPT
    for et in sorted(uncovered):
        warnings.append(
            f"EventType '{et}' has no _REQUIRED_DATA_FIELDS entry "
            f"(add schema or add to _SCHEMA_EXEMPT in this script)"
        )

    # Check 3: all --event-type refs in .md files are valid
    md_usage = _scan_md_event_types([_AGENTS_DIR, _COMMANDS_DIR, _SKILLS_DIR])
    print(f"\n.md files          reference {len(md_usage)} distinct event types")
    for et in sorted(md_usage):
        if et not in valid_types:
            files = md_usage[et]
            loc = files[0] + (f" (+{len(files)-1} more)" if len(files) > 1 else "")
            errors.append(
                f"'{et}' used in .md ({loc}) is NOT in orch_core.EventType"
            )

    # Check 4: event_type string refs in .py hooks/scripts are valid
    py_usage = _scan_py_event_types([_HOOKS_DIR, _SCRIPTS_DIR])
    print(f".py hooks/scripts  reference {len(py_usage)} distinct event types")
    for et in sorted(py_usage):
        if et and et not in valid_types:
            files = py_usage[et]
            loc = files[0] + (f" (+{len(files)-1} more)" if len(files) > 1 else "")
            warnings.append(
                f"'{et}' string in .py ({loc}) not in orch_core.EventType"
            )

    # Check 5: exit-criteria.json structural integrity (task 11, A5-F6)
    ec_errors = _check_exit_criteria_scripts(_SKILLS_DIR)
    print(f"exit-criteria.json structural: {len(ec_errors)} error(s)")
    errors.extend(ec_errors)

    # Report
    print()
    if warnings:
        print(f"{len(warnings)} WARNING(S):")
        for w in warnings:
            print(f"  WARN : {w}")
        print()

    if errors:
        print(f"{len(errors)} ERROR(S):")
        for e in errors:
            print(f"  ERROR: {e}")
        return 1

    if strict and warnings:
        print("FAILED (--strict: warnings treated as errors).")
        return 1

    print("OK — dist/ is consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main(strict="--strict" in sys.argv))
