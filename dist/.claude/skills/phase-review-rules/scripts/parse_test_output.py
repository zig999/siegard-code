#!/usr/bin/env python3
"""
parse_test_output.py — Normalize test runner output (vitest / jest) into a
canonical schema consumed by attribute_failures.py.

Both runners share the same JSON shape (numTotalTests, testResults[],
assertionResults[]).

**Shape wins over provenance (R09a).** The payload is parsed whenever it
carries that shape, regardless of which framework was detected or declared.
The previous order — detect the framework first, and only then consider
parsing — silently discarded fully parseable output whenever detection
failed: a monorepo whose `vitest` lives in `backend/package.json` and whose
root has no `package.json` at all resolved to `unknown`, so a green run of
2022 tests was reported as `{total: 0}` / degraded. Detection is a heuristic;
the shape of the bytes on disk is a fact.

Only genuinely unusable output (not JSON, or JSON in an unrecognized shape)
falls through to a degraded result with no parsed failures — workers then
revert to local test-gate.

Usage:
    python3 parse_test_output.py \
      --framework vitest|jest|auto \
      --input <path-to-runner-stdout-json> \
      [--project-dir <dir>] [--test-command <cmd>]

Output (stdout, exit 0):
    {
      "framework": "vitest"|"jest"|"jest-like"|"unknown",
      "summary": {"total": int, "passed": int, "failed": int, "skipped": int},
      "executed_test_files": ["<rel/path/to/test.spec.ts>", ...],
      "failures": [
        {
          "test_file": "<rel path>",
          "test_name": "<full name>",
          "line": int|null,
          "error_class": "<AssertionError>"|null,
          "error_message": "<first chunk of failure message>"
        }
      ]
    }

Output (exit 1, stderr):
    {"status": "error", "reason": "<code>", "detail": "<message>"}
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


_ERROR_CLASS_RE = re.compile(r"^([A-Z][A-Za-z0-9_]+(?:Error|Exception)):\s*(.*)$")


def _normalize_path(raw: str, project_dir: Path) -> str:
    if not raw:
        return ""
    p = Path(raw)
    if p.is_absolute():
        try:
            return str(p.relative_to(project_dir)).replace("\\", "/")
        except ValueError:
            return raw.replace("\\", "/")
    return raw.replace("\\", "/")


def _parse_failure_message(joined: str) -> tuple[str | None, str]:
    if not joined:
        return None, ""
    first_line = next((ln for ln in joined.splitlines() if ln.strip()), "").strip()
    m = _ERROR_CLASS_RE.match(first_line)
    if m:
        return m.group(1), joined.strip()
    return None, joined.strip()


def parse_jest_like(payload: dict, project_dir: Path) -> dict:
    failures: list[dict] = []
    skipped = 0
    executed: list[str] = []
    for tr in payload.get("testResults", []):
        test_file_raw = tr.get("name") or tr.get("testFilePath") or ""
        test_file = _normalize_path(test_file_raw, project_dir) if test_file_raw else ""
        if test_file:
            executed.append(test_file)
        for ar in tr.get("assertionResults", []):
            status = ar.get("status")
            if status in ("skipped", "pending", "todo", "disabled"):
                skipped += 1
                continue
            if status != "failed":
                continue
            messages = ar.get("failureMessages") or []
            joined = "\n".join(m for m in messages if isinstance(m, str))
            error_class, error_message = _parse_failure_message(joined)
            location = ar.get("location") or {}
            line = location.get("line") if isinstance(location, dict) else None
            failures.append({
                "test_file": test_file,
                "test_name": ar.get("fullName") or ar.get("title") or "",
                "line": line,
                "error_class": error_class,
                "error_message": error_message[:1000],
            })

    total = int(payload.get("numTotalTests", 0) or 0)
    passed = int(payload.get("numPassedTests", 0) or 0)
    failed = int(payload.get("numFailedTests", len(failures)) or 0)
    pending = int(payload.get("numPendingTests", 0) or 0)
    todo = int(payload.get("numTodoTests", 0) or 0)
    skipped_total = max(skipped, pending + todo)

    return {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped_total,
        },
        "executed_test_files": executed,
        "failures": failures,
    }


_CMD_FRAMEWORK_RE = re.compile(r"(?:^|[\s/\\'\"])(vitest|jest)(?:$|[\s'\"])")

# Depth cap for the package.json sweep: enough for the common
# `<root>/backend`, `<root>/packages/api` layouts without walking a whole
# node_modules tree.
_PKG_SWEEP_MAX_DEPTH = 2
_PKG_SWEEP_SKIP = {"node_modules", ".git", "dist", "build", "coverage", ".venv", "__pycache__"}


def _framework_from_deps(pkg: Path) -> str:
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    deps = {
        **(data.get("devDependencies") or {}),
        **(data.get("dependencies") or {}),
    }
    if "vitest" in deps:
        return "vitest"
    if "jest" in deps:
        return "jest"
    return "unknown"


def _iter_package_jsons(project_dir: Path):
    """`project_dir/package.json` first, then nested ones up to a small depth.

    R09b: the runner's cwd is frequently NOT the project root — a
    `test_command` of `cd backend && npx vitest run` runs one level down, and
    plenty of repos have no root manifest at all. Looking only at the root
    made detection fail on exactly the layouts that need it.
    """
    root = project_dir / "package.json"
    if root.is_file():
        yield root
    for depth in range(1, _PKG_SWEEP_MAX_DEPTH + 1):
        for pkg in sorted(project_dir.glob("/".join(["*"] * depth) + "/package.json")):
            if any(part in _PKG_SWEEP_SKIP for part in pkg.relative_to(project_dir).parts):
                continue
            yield pkg


def detect_framework(project_dir: Path, test_command: str | None = None) -> str:
    """Resolve the runner. Order = strongest evidence first.

    1. `test_command` — the command that actually produced the output. A repo
       may declare both runners; only one of them ran.
    2. `<project_dir>/package.json`, then nested manifests (R09b).

    Returns ``"unknown"`` when nothing matches. Detection failing is no longer
    fatal to parsing — see the module docstring (R09a).
    """
    if test_command:
        m = _CMD_FRAMEWORK_RE.search(test_command)
        if m:
            return m.group(1)
    for pkg in _iter_package_jsons(project_dir):
        found = _framework_from_deps(pkg)
        if found != "unknown":
            return found
    return "unknown"


def _extract_json_object(text: str) -> str | None:
    """
    Best-effort extraction of the outermost JSON object from a stdout blob
    that may contain leading/trailing log lines. Returns the substring or
    None if no balanced object is found.
    """
    if not text:
        return None
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        start = text.find("{", start + 1)
    return None


_JEST_LIKE_KEYS = ("numTotalTests", "testResults", "numPassedTests", "numFailedTests")


def looks_jest_like(payload: object) -> bool:
    """True when the payload carries the jest/vitest reporter shape.

    This is the parseability test. It deliberately does not care which runner
    produced the bytes — `vitest --reporter=json` and `jest --json` emit the
    same schema, and so do the several runners that copy it.
    """
    return isinstance(payload, dict) and any(k in payload for k in _JEST_LIKE_KEYS)


def _load_payload(raw_text: str) -> object | None:
    """Parse the blob, tolerating log lines around the JSON object."""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass
    extracted = _extract_json_object(raw_text)
    if extracted:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            return None
    return None


def _degraded(framework: str, warning: str) -> dict:
    return {
        "framework": framework,
        "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
        "executed_test_files": [],
        "failures": [],
        "_warning": warning,
    }


def parse(framework: str, raw_text: str, project_dir: Path,
          test_command: str | None = None) -> dict:
    if framework == "auto":
        framework = detect_framework(project_dir, test_command)

    # R09a — attempt the parse unconditionally. Framework detection only
    # decides the LABEL, never whether the payload gets read.
    payload = _load_payload(raw_text)

    if looks_jest_like(payload):
        result = parse_jest_like(payload, project_dir)
        # Keep a declared/detected runner name when we have one; otherwise be
        # honest that the shape was recognized but the runner was not.
        result["framework"] = framework if framework in ("vitest", "jest") else "jest-like"
        return result

    if payload is None:
        return _degraded(
            framework,
            "non-JSON output — degraded mode (workers fall back to local test-gate)",
        )

    return _degraded(
        framework,
        "JSON output does not carry the jest/vitest reporter shape "
        "(no numTotalTests/testResults) — degraded mode "
        "(workers fall back to local test-gate)",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--framework", default="auto",
                    choices=["auto", "vitest", "jest", "unknown"])
    ap.add_argument("--input", required=True,
                    help="path to test runner stdout (JSON expected)")
    ap.add_argument("--project-dir",
                    default=os.environ.get("ORCH_PROJECT_DIR", "."))
    ap.add_argument("--test-command", default="",
                    help="the command that produced the output — strongest "
                         "framework signal when --framework is auto (R09b)")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({
            "status": "error",
            "reason": "input_not_found",
            "detail": str(input_path),
        }), file=sys.stderr)
        sys.exit(1)

    raw = input_path.read_text(encoding="utf-8", errors="replace")
    result = parse(args.framework, raw, project_dir, args.test_command or None)
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
