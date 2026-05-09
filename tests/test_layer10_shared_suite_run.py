"""Layer 10 — Shared Suite Run: parse_test_output.py and attribute_failures.py scripts."""
import json
import subprocess
import tempfile
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "dist" / ".claude" / "skills" / "phase-review-rules" / "scripts"
PARSE_TEST = SCRIPTS / "parse_test_output.py"
ATTRIBUTE = SCRIPTS / "attribute_failures.py"


def _run_py(script, args):
    result = subprocess.run(
        ["python3", str(script)] + args,
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Script failed: {result.stderr}")
    return result.stdout


def _delivery_doc(created=(), modified=(), tests=()):
    created_block = (
        "files_created: []" if not created
        else "files_created:\n" + "\n".join(
            f'  - path: "{p}"\n    responsibility: ""' for p in created
        )
    )
    modified_block = (
        "files_modified: []" if not modified
        else "files_modified:\n" + "\n".join(
            f'  - path: "{p}"\n    change: ""' for p in modified
        )
    )
    tests_block = (
        "tests: []" if not tests
        else "tests:\n" + "\n".join(
            f'  - file: "{f}"\n    covers: []' for f in tests
        )
    )
    return "\n".join([
        "```yaml", "# delivery-gate", "task: TC-XX", "qa_ready: true", "```",
        "", "```yaml", "# delivery-body",
        created_block, modified_block, tests_block,
        "```", "",
    ])


def _build_manifest(tc_ids, parsed, build=None):
    return {
        "schema_version": "1",
        "suite_run_id": "sr-1",
        "round": 1,
        "scope": {"tc_ids_covered": tc_ids, "signature": "test-signature"},
        "build": build or {"command": "tsc --noEmit", "exit_code": 0, "result": "passed", "errors": []},
        "tests": {
            "command": "vitest run --reporter=json",
            "framework": parsed.get("framework", "vitest"),
            "exit_code": 1 if parsed["summary"]["failed"] > 0 else 0,
            "result": "failed" if parsed["summary"]["failed"] > 0 else "passed",
            "summary": parsed["summary"],
            "executed_test_files": parsed.get("executed_test_files", []),
            "failures": parsed.get("failures", []),
        },
    }


def _setup_session(root, deliveries):
    proj = root / "proj"
    sr = root / "session" / "qa" / "_suite-run" / "sr-1"
    proj.mkdir(parents=True, exist_ok=True)
    sr.mkdir(parents=True, exist_ok=True)
    for d in deliveries:
        target = proj / d["delivery_rel"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(d["delivery"], encoding="utf-8")
    return proj, sr


def _parse_test_output(raw_json_path, project_dir, framework="vitest"):
    output = _run_py(PARSE_TEST, [
        "--framework", framework,
        "--input", str(raw_json_path),
        "--project-dir", str(project_dir),
    ])
    return json.loads(output)


def _run_attribution(sr, proj, deliveries):
    arg = json.dumps([
        {"task_id": d["task_id"], "delivery_path": d["delivery_rel"]}
        for d in deliveries
    ])
    output = _run_py(ATTRIBUTE, [
        "--suite-run-dir", str(sr),
        "--project-dir", str(proj),
        "--deliveries", arg,
    ])
    return json.loads(output)


@pytest.fixture
def tmp_dir():
    d = Path(tempfile.mkdtemp(prefix="shared-suite-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestLayer10SharedSuiteRun:
    def test_sr001_attributes_failing_test_to_tc(self, tmp_dir):
        deliveries = [
            {
                "task_id": "dev_tc_001",
                "delivery_rel": ".orch/sessions/wf/delivery/dev_tc_001-delivery.md",
                "delivery": _delivery_doc(
                    created=["src/users/controller.ts"],
                    modified=["src/users/service.ts"],
                    tests=["__tests__/integration/user.spec.ts"],
                ),
            },
            {
                "task_id": "dev_tc_002",
                "delivery_rel": ".orch/sessions/wf/delivery/dev_tc_002-delivery.md",
                "delivery": _delivery_doc(
                    created=["src/orders/service.ts"],
                    tests=["__tests__/unit/order.spec.ts"],
                ),
            },
            {
                "task_id": "dev_tc_003",
                "delivery_rel": ".orch/sessions/wf/delivery/dev_tc_003-delivery.md",
                "delivery": _delivery_doc(
                    modified=["src/billing.ts"],
                    tests=["__tests__/unit/billing.spec.ts"],
                ),
            },
        ]
        proj, sr = _setup_session(tmp_dir, deliveries)

        runner_output = {
            "numTotalTests": 4,
            "numPassedTests": 3,
            "numFailedTests": 1,
            "testResults": [
                {
                    "name": str(proj / "__tests__/integration/user.spec.ts"),
                    "assertionResults": [{
                        "fullName": "POST /users returns 201",
                        "title": "returns 201",
                        "status": "failed",
                        "failureMessages": ["AssertionError: expected 500 to be 201"],
                        "location": {"line": 42, "column": 5},
                    }],
                },
                {
                    "name": str(proj / "__tests__/unit/order.spec.ts"),
                    "assertionResults": [{"fullName": "createOrder builds payload", "title": "builds",
                                          "status": "passed", "location": {"line": 12}}],
                },
                {
                    "name": str(proj / "__tests__/unit/billing.spec.ts"),
                    "assertionResults": [
                        {"fullName": "computeTax zero", "title": "zero", "status": "passed", "location": {"line": 8}},
                        {"fullName": "computeTax neg", "title": "neg", "status": "passed", "location": {"line": 18}},
                    ],
                },
            ],
        }
        runner_out_path = sr / "tests.stdout.json"
        runner_out_path.write_text(json.dumps(runner_output), encoding="utf-8")

        parsed = _parse_test_output(runner_out_path, proj)
        assert parsed["summary"]["failed"] == 1
        assert len(parsed["failures"]) == 1

        manifest = _build_manifest(tc_ids=[d["task_id"] for d in deliveries], parsed=parsed)
        (sr / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        result = _run_attribution(sr, proj, deliveries)
        assert result["status"] == "ok"
        assert result["by_tc_count"] == 3
        assert result["unattributed_test_failures"] == 0

        slice1 = json.loads((sr / "by-tc/dev_tc_001.json").read_text())
        slice2 = json.loads((sr / "by-tc/dev_tc_002.json").read_text())
        slice3 = json.loads((sr / "by-tc/dev_tc_003.json").read_text())

        assert slice1["test_gate_result"] == "failed"
        assert slice1["test_gate_cause"] == "code"
        assert len(slice1["test_attribution"]["failures_attributed"]) == 1
        assert slice1["test_attribution"]["failures_attributed"][0]["attribution_reason"] == "test_in_tests_written"
        assert slice1["test_attribution"]["failures_attributed"][0]["diagnosis"]["probable_cause"] == "code"
        assert slice2["test_gate_result"] == "passed"
        assert slice2["test_attribution"]["failures_attributed"] == []
        assert slice3["test_gate_result"] == "passed"
        assert slice3["test_attribution"]["failures_attributed"] == []

    def test_sr002_unattributed_failure_blocks_all_tcs(self, tmp_dir):
        deliveries = [
            {
                "task_id": "dev_tc_001",
                "delivery_rel": ".orch/sessions/wf/delivery/dev_tc_001-delivery.md",
                "delivery": _delivery_doc(
                    modified=["src/users/service.ts"],
                    tests=["__tests__/unit/user.spec.ts"],
                ),
            },
            {
                "task_id": "dev_tc_002",
                "delivery_rel": ".orch/sessions/wf/delivery/dev_tc_002-delivery.md",
                "delivery": _delivery_doc(
                    modified=["src/orders/service.ts"],
                    tests=["__tests__/unit/order.spec.ts"],
                ),
            },
        ]
        proj, sr = _setup_session(tmp_dir, deliveries)

        runner_output = {
            "numTotalTests": 1,
            "numPassedTests": 0,
            "numFailedTests": 1,
            "testResults": [{
                "name": str(proj / "__tests__/integration/auth.spec.ts"),
                "assertionResults": [{
                    "fullName": "login returns token",
                    "title": "login",
                    "status": "failed",
                    "failureMessages": ["Error: ECONNREFUSED 127.0.0.1:5432"],
                    "location": {"line": 10},
                }],
            }],
        }
        runner_out_path = sr / "tests.stdout.json"
        runner_out_path.write_text(json.dumps(runner_output), encoding="utf-8")

        parsed = _parse_test_output(runner_out_path, proj)
        manifest = _build_manifest(tc_ids=[d["task_id"] for d in deliveries], parsed=parsed)
        (sr / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        result = _run_attribution(sr, proj, deliveries)
        assert result["unattributed_test_failures"] == 1

        slice1 = json.loads((sr / "by-tc/dev_tc_001.json").read_text())
        slice2 = json.loads((sr / "by-tc/dev_tc_002.json").read_text())
        assert slice1["test_gate_result"] == "blocked_by_unattributed_failure"
        assert slice2["test_gate_result"] == "blocked_by_unattributed_failure"

        updated_manifest = json.loads((sr / "manifest.json").read_text())
        assert len(updated_manifest["attribution"]["unattributed_failures"]) == 1
        assert "auth.spec.ts" in updated_manifest["attribution"]["unattributed_failures"][0]["test_file"]

    def test_sr003_build_error_marks_all_tcs_build_blocked(self, tmp_dir):
        deliveries = [
            {
                "task_id": "dev_tc_001",
                "delivery_rel": ".orch/sessions/wf/delivery/dev_tc_001-delivery.md",
                "delivery": _delivery_doc(
                    modified=["src/users/service.ts"],
                    tests=["__tests__/unit/user.spec.ts"],
                ),
            },
            {
                "task_id": "dev_tc_002",
                "delivery_rel": ".orch/sessions/wf/delivery/dev_tc_002-delivery.md",
                "delivery": _delivery_doc(
                    modified=["src/orders/service.ts"],
                    tests=["__tests__/unit/order.spec.ts"],
                ),
            },
        ]
        proj, sr = _setup_session(tmp_dir, deliveries)

        parsed = {
            "framework": "vitest",
            "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            "executed_test_files": [],
            "failures": [],
        }
        manifest = _build_manifest(
            tc_ids=[d["task_id"] for d in deliveries],
            parsed=parsed,
            build={
                "command": "tsc --noEmit",
                "exit_code": 1,
                "duration_s": 1.2,
                "result": "failed",
                "errors": [{
                    "file": "src/users/service.ts",
                    "line": 12, "column": 3,
                    "code": "TS2322",
                    "message": "Type 'string' is not assignable to type 'number'.",
                }],
            },
        )
        (sr / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        result = _run_attribution(sr, proj, deliveries)
        assert result["status"] == "ok"

        slice1 = json.loads((sr / "by-tc/dev_tc_001.json").read_text())
        slice2 = json.loads((sr / "by-tc/dev_tc_002.json").read_text())

        assert slice1["build_attribution"]["blocked_by_build"] is True
        assert len(slice1["build_attribution"]["build_errors_in_my_files"]) == 1
        assert slice1["test_gate_result"] == "failed"
        assert slice1["test_gate_cause"] == "build"
        assert slice2["build_attribution"]["blocked_by_build"] is True
        assert slice2["build_attribution"]["build_errors_in_my_files"] == []
        assert slice2["test_gate_result"] == "failed"
        assert slice2["test_gate_cause"] == "build"

    def test_sr004_tests_declared_but_not_executed_setup_failure(self, tmp_dir):
        deliveries = [{
            "task_id": "dev_tc_001",
            "delivery_rel": ".orch/sessions/wf/delivery/dev_tc_001-delivery.md",
            "delivery": _delivery_doc(
                modified=["src/users/service.ts"],
                tests=[
                    "__tests__/unit/user.spec.ts",
                    "__tests__/unit/user-extra.spec.ts",
                ],
            ),
        }]
        proj, sr = _setup_session(tmp_dir, deliveries)

        runner_output = {
            "numTotalTests": 1,
            "numPassedTests": 1,
            "numFailedTests": 0,
            "testResults": [{
                "name": str(proj / "__tests__/unit/user.spec.ts"),
                "assertionResults": [{
                    "fullName": "creates user", "title": "creates",
                    "status": "passed", "location": {"line": 12},
                }],
            }],
        }
        runner_out_path = sr / "tests.stdout.json"
        runner_out_path.write_text(json.dumps(runner_output), encoding="utf-8")

        parsed = _parse_test_output(runner_out_path, proj)
        manifest = _build_manifest(tc_ids=["dev_tc_001"], parsed=parsed)
        (sr / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        _run_attribution(sr, proj, deliveries)

        slice_ = json.loads((sr / "by-tc/dev_tc_001.json").read_text())
        assert "__tests__/unit/user-extra.spec.ts" in slice_["test_attribution"]["tests_declared_but_not_executed"]
        assert slice_["test_gate_result"] == "failed"
        assert slice_["test_gate_cause"] == "setup"
