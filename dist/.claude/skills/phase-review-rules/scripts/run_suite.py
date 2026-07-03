#!/usr/bin/env python3
"""
run_suite.py — Execute build + test suite once per round, write manifest base.

Produces (under <suite-run-dir>):
  - build.stdout.txt
  - build.stderr.txt
  - tests.stdout.json     (raw runner output)
  - tests.stderr.txt
  - manifest.json         (build + tests sections; attribution is empty —
                           filled by attribute_failures.py in a later step)

Does NOT update current.txt — the orchestrator does that after a successful
attribution pass, ensuring readers never observe a partially-built run.

Usage:
    python3 run_suite.py \
      --suite-run-dir <abs path to qa/_suite-run/sr-N> \
      --project-dir <abs path> \
      --suite-run-id sr-1 \
      --workflow-id <wf> \
      --round 1 \
      --tc-ids dev_myflow_tc_001,dev_myflow_tc_002 \
      --signature <hex> \
      [--build-cmd "<cmd>"] \
      --test-cmd "<cmd>" \
      [--framework auto|vitest|jest|unknown] \
      [--timeout-build 180] \
      [--timeout-tests 900]

Output (stdout, exit 0):
    {"status": "ok", "manifest": "<path>", "build_result": "passed|failed|skipped",
     "tests_result": "passed|failed|degraded"}

Output (exit 1, stderr):
    {"status": "error", "reason": "<code>", "detail": "..."}
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PARSE_SCRIPT = _HERE / "parse_test_output.py"


_TS_ERROR_RE = re.compile(
    r"^(?P<file>.+?)[(:](?P<line>\d+)[,:](?P<col>\d+)\)?:\s+error\s+(?P<code>[A-Z]+\d+):\s+(?P<msg>.+)$"
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: str, cwd: Path, timeout: int) -> tuple[int, str, str, float]:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), shell=True, timeout=timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return proc.returncode, proc.stdout or "", proc.stderr or "", time.monotonic() - start
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        out = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        err = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        return 124, out, f"{err}\n[run_suite: timeout after {timeout}s]", elapsed


def _parse_build_errors(stdout: str, stderr: str, project_dir: Path) -> list[dict]:
    errors: list[dict] = []
    blob = (stdout or "") + "\n" + (stderr or "")
    for line in blob.splitlines():
        m = _TS_ERROR_RE.match(line.strip())
        if not m:
            continue
        file_raw = m.group("file").strip()
        # Normalize against project_dir
        p = Path(file_raw)
        if p.is_absolute():
            try:
                file_norm = str(p.relative_to(project_dir)).replace("\\", "/")
            except ValueError:
                file_norm = file_raw.replace("\\", "/")
        else:
            file_norm = file_raw.replace("\\", "/")
        errors.append({
            "file": file_norm,
            "line": int(m.group("line")),
            "column": int(m.group("col")),
            "code": m.group("code"),
            "message": m.group("msg").strip(),
        })
    return errors


def _invoke_parser(framework: str, input_path: Path, project_dir: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(_PARSE_SCRIPT),
         "--framework", framework,
         "--input", str(input_path),
         "--project-dir", str(project_dir)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        return {
            "framework": "unknown",
            "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "executed_test_files": [],
            "failures": [],
            "_warning": f"parse_test_output.py exited {proc.returncode}: {proc.stderr.strip()[:240]}",
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "framework": "unknown",
            "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "executed_test_files": [],
            "failures": [],
            "_warning": f"parse_test_output.py returned non-JSON ({exc})",
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite-run-dir", required=True)
    ap.add_argument("--project-dir", default=os.environ.get("ORCH_PROJECT_DIR", "."))
    ap.add_argument("--suite-run-id", required=True)
    ap.add_argument("--workflow-id", required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--tc-ids", default="",
                    help="comma-separated list of task_ids covered by this run")
    ap.add_argument("--signature", default="",
                    help="opaque signature for staleness comparison")
    ap.add_argument("--build-cmd", default="")
    ap.add_argument("--test-cmd", required=True)
    ap.add_argument("--framework", default="auto",
                    choices=["auto", "vitest", "jest", "unknown"])
    ap.add_argument("--timeout-build", type=int, default=180)
    ap.add_argument("--timeout-tests", type=int, default=900)
    ap.add_argument("--trigger-seq", type=int, default=0)
    args = ap.parse_args()

    suite_run_dir = Path(args.suite_run_dir).resolve()
    project_dir = Path(args.project_dir).resolve()
    suite_run_dir.mkdir(parents=True, exist_ok=True)

    if not project_dir.exists():
        print(json.dumps({
            "status": "error", "reason": "project_dir_missing",
            "detail": str(project_dir),
        }), file=sys.stderr)
        sys.exit(1)

    tc_ids = [t.strip() for t in args.tc_ids.split(",") if t.strip()]

    # ── Build ──
    build_section: dict = {
        "command": args.build_cmd,
        "exit_code": None,
        "duration_s": 0.0,
        "result": "skipped",
        "errors": [],
    }
    if args.build_cmd:
        rc, out, err, elapsed = _run(args.build_cmd, project_dir, args.timeout_build)
        (suite_run_dir / "build.stdout.txt").write_text(out, encoding="utf-8")
        (suite_run_dir / "build.stderr.txt").write_text(err, encoding="utf-8")
        build_section["exit_code"] = rc
        build_section["duration_s"] = round(elapsed, 2)
        build_section["result"] = "passed" if rc == 0 else "failed"
        build_section["errors"] = _parse_build_errors(out, err, project_dir)

    # ── Tests ──
    # Always run tests even if build failed; the build-failed branch in
    # attribute_failures.py marks all TCs as test_gate_result=failed and the
    # orchestrator's policy is to skip dispatch — but capturing test output
    # alongside makes manual triage easier.
    tests_stdout_path = suite_run_dir / "tests.stdout.json"
    tests_stderr_path = suite_run_dir / "tests.stderr.txt"

    rc, out, err, elapsed = _run(args.test_cmd, project_dir, args.timeout_tests)
    tests_stdout_path.write_text(out, encoding="utf-8")
    tests_stderr_path.write_text(err, encoding="utf-8")

    parsed = _invoke_parser(args.framework, tests_stdout_path, project_dir)

    if "_warning" in parsed:
        tests_result = "degraded"
    elif parsed["summary"].get("failed", 0) > 0:
        tests_result = "failed"
    elif parsed["summary"].get("total", 0) == 0 and rc != 0:
        tests_result = "failed"
    else:
        tests_result = "passed"

    tests_section = {
        "command": args.test_cmd,
        "framework": parsed.get("framework", "unknown"),
        "exit_code": rc,
        "duration_s": round(elapsed, 2),
        "result": tests_result,
        "summary": parsed.get("summary", {"total": 0, "passed": 0, "failed": 0, "skipped": 0}),
        "executed_test_files": parsed.get("executed_test_files", []),
        "raw_output_path": str(tests_stdout_path.relative_to(suite_run_dir.parent.parent)).replace("\\", "/"),
        "failures": parsed.get("failures", []),
    }
    if "_warning" in parsed:
        tests_section["warning"] = parsed["_warning"]

    # ── Manifest ──
    manifest = {
        "schema_version": "1",
        "suite_run_id": args.suite_run_id,
        "workflow_id": args.workflow_id,
        "round": args.round,
        "executed_at": _now_iso(),
        "executed_by": "orchestrator-review",
        "trigger_seq": args.trigger_seq,
        "scope": {
            "type": "full",
            "tc_ids_covered": tc_ids,
            "signature": args.signature,
            "filter_patterns": None,
        },
        "build": build_section,
        "tests": tests_section,
        "attribution": {
            "method": "pending",
            "by_tc": {},
            "unattributed_failures": [],
            "unattributed_build_errors": [],
            "shared_failures": [],
        },
    }

    manifest_path = suite_run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "manifest": str(manifest_path),
        "build_result": build_section["result"],
        "tests_result": tests_result,
        "tests_summary": tests_section["summary"],
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "error", "reason": "internal_error", "detail": str(exc),
        }), file=sys.stderr)
        sys.exit(1)
