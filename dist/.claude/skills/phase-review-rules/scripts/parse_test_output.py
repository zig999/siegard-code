#!/usr/bin/env python3
"""
parse_test_output.py — Normalize test runner output (vitest / jest) into a
canonical schema consumed by attribute_failures.py.

Both runners share the same JSON shape (numTotalTests, testResults[],
assertionResults[]). Other frameworks fall through to a degraded "unknown"
result with no parsed failures — workers will revert to local test-gate.

Usage:
    python3 parse_test_output.py \
      --framework vitest|jest|auto \
      --input <path-to-runner-stdout-json> \
      [--project-dir <dir>]

Output (stdout, exit 0):
    {
      "framework": "vitest"|"jest"|"unknown",
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


def detect_framework(project_dir: Path) -> str:
    pkg = project_dir / "package.json"
    if not pkg.exists():
        return "unknown"
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


def parse(framework: str, raw_text: str, project_dir: Path) -> dict:
    if framework == "auto":
        framework = detect_framework(project_dir)

    if framework in ("vitest", "jest"):
        payload = None
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            extracted = _extract_json_object(raw_text)
            if extracted:
                try:
                    payload = json.loads(extracted)
                except json.JSONDecodeError:
                    payload = None

        if payload is None:
            return {
                "framework": framework,
                "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "executed_test_files": [],
                "failures": [],
                "_warning": "non-JSON output — degraded mode (workers fall back to local test-gate)",
            }
        result = parse_jest_like(payload, project_dir)
        result["framework"] = framework
        return result

    return {
        "framework": "unknown",
        "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
        "executed_test_files": [],
        "failures": [],
        "_warning": "framework not supported by parser — workers fall back to local test-gate",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--framework", default="auto",
                    choices=["auto", "vitest", "jest", "unknown"])
    ap.add_argument("--input", required=True,
                    help="path to test runner stdout (JSON expected)")
    ap.add_argument("--project-dir",
                    default=os.environ.get("ORCH_PROJECT_DIR", "."))
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
    result = parse(args.framework, raw, project_dir)
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
