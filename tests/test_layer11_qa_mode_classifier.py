"""Layer 11 — QA Mode Classifier: classify_qa_mode.py and check_micro_unanimous_clean.py."""
import json
import subprocess
import tempfile
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "dist" / ".claude" / "skills" / "phase-review-rules" / "scripts"
CLASSIFY = SCRIPTS / "classify_qa_mode.py"
AUTO_APPROVE = SCRIPTS / "check_micro_unanimous_clean.py"


def _run_py(script, args, ok_codes=(0,)):
    result = subprocess.run(
        ["python3", str(script)] + args,
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode not in ok_codes:
        raise RuntimeError(f"Script failed (exit {result.returncode}): {result.stderr}")
    return result.stdout


def _classify(workflow_type, dev_impact, changed_files, tc_type, delivery_rel, project_dir):
    output = _run_py(CLASSIFY, [
        "--workflow-type", workflow_type,
        "--dev-impact", dev_impact,
        "--changed-files-count", str(changed_files),
        "--tc-type", tc_type,
        "--delivery-path", delivery_rel,
        "--project-dir", str(project_dir),
    ])
    return json.loads(output)


def _delivery_doc(created=(), modified=(), tests=(), has_nfr=False):
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
    nfr_block = (
        "\nnfr_results:\n  - type: latency_p99_ms\n    threshold: 200\n    measured: 180\n    passed: true"
        if has_nfr else ""
    )
    return "\n".join([
        "```yaml", "# delivery-gate", "task: TC-XX", f"qa_ready: true{nfr_block}", "```",
        "", "```yaml", "# delivery-body",
        created_block, modified_block, tests_block,
        "```", "",
    ])


def _setup_project(root, delivery_name, doc):
    proj = root / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / delivery_name).write_text(doc, encoding="utf-8")
    return proj


@pytest.fixture
def tmp_dir():
    d = Path(tempfile.mkdtemp(prefix="qa-mode-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tmp_qa_dir():
    d = Path(tempfile.mkdtemp(prefix="auto-approve-"))
    qa = d / "qa"
    qa.mkdir()
    yield d, qa
    shutil.rmtree(d, ignore_errors=True)


class TestLayer11ClassifyQaMode:
    def test_qm001_micro_path_improve_narrow_1file_bugfix(self, tmp_dir):
        proj = _setup_project(tmp_dir, "d.md", _delivery_doc(
            modified=["src/utils/format-date.ts"],
            tests=["__tests__/unit/format-date.spec.ts"],
        ))
        r = _classify("improve", "narrow", 1, "Bugfix", "d.md", proj)
        assert r["qa_mode"] == "micro"
        assert r["concurrency_hint"] == 5

    def test_qm002_full_overrides_micro_when_touches_controller(self, tmp_dir):
        proj = _setup_project(tmp_dir, "d.md", _delivery_doc(
            modified=["src/users/controller.ts"],
            tests=["__tests__/integration/users.spec.ts"],
        ))
        r = _classify("improve", "narrow", 1, "Bugfix", "d.md", proj)
        assert r["qa_mode"] == "full"
        assert r["concurrency_hint"] == 2
        assert r["signals"]["touches_public_api"] is True
        assert "src/users/controller.ts" in r["signals"]["matched_public_api_paths"]

    def test_qm003_full_overrides_micro_when_touches_auth(self, tmp_dir):
        proj = _setup_project(tmp_dir, "d.md", _delivery_doc(
            modified=["src/middleware/auth-guard.ts"],
            tests=["__tests__/unit/auth-guard.spec.ts"],
        ))
        r = _classify("improve", "narrow", 1, "Bugfix", "d.md", proj)
        assert r["qa_mode"] == "full"
        assert r["signals"]["touches_security"] is True

    def test_qm004_full_when_tc_has_nfr(self, tmp_dir):
        proj = _setup_project(tmp_dir, "d.md", _delivery_doc(
            modified=["src/utils/format-date.ts"],
            tests=["__tests__/unit/format-date.spec.ts"],
            has_nfr=True,
        ))
        r = _classify("improve", "narrow", 1, "Bugfix", "d.md", proj)
        assert r["qa_mode"] == "full"
        assert r["signals"]["has_nfr"] is True

    def test_qm005_standard_fallback_when_changed_files_gt2(self, tmp_dir):
        proj = _setup_project(tmp_dir, "d.md", _delivery_doc(
            modified=["src/a.ts", "src/b.ts", "src/c.ts"],
            tests=["__tests__/unit/a.spec.ts"],
        ))
        r = _classify("improve", "narrow", 3, "Bugfix", "d.md", proj)
        assert r["qa_mode"] == "standard"
        assert r["concurrency_hint"] == 3
        assert "files=3" in r["rationale"]

    def test_qm006_standard_when_tc_type_new_feature(self, tmp_dir):
        proj = _setup_project(tmp_dir, "d.md", _delivery_doc(
            modified=["src/services/billing.ts"],
            tests=["__tests__/unit/billing.spec.ts"],
        ))
        r = _classify("improve", "narrow", 1, "NewFeature", "d.md", proj)
        assert r["qa_mode"] == "standard"

    def test_qm007_standard_when_workflow_type_standard(self, tmp_dir):
        proj = _setup_project(tmp_dir, "d.md", _delivery_doc(
            modified=["src/billing.ts"],
            tests=["__tests__/unit/billing.spec.ts"],
        ))
        r = _classify("standard", "narrow", 1, "Bugfix", "d.md", proj)
        assert r["qa_mode"] == "standard"


class TestLayer11CheckMicroUnanimousClean:
    def _write_verdict(self, qa_dir, name, verdict, severities=()):
        findings = "\n".join(f"- severity: {s}\n  message: dummy" for s in severities)
        (qa_dir / name).write_text(f"verdict: {verdict}\n\n## Findings\n{findings}\n", encoding="utf-8")

    def _run_auto_approve(self, tmp, tasks):
        # prod-hardening task 02: exit 2 = disqualified (valid result with stdout);
        # only exit 1 (bad input/error) is a failure.
        output = _run_py(AUTO_APPROVE, [
            "--project-dir", str(tmp),
            "--tasks", json.dumps(tasks),
        ], ok_codes=(0, 2))
        return json.loads(output)

    def test_aa001_qualifies_two_micro_both_approved_only_low(self, tmp_qa_dir):
        tmp, qa = tmp_qa_dir
        self._write_verdict(qa, "a.md", "approved", ["low"])
        self._write_verdict(qa, "b.md", "approved", [])
        r = self._run_auto_approve(tmp, [
            {"task_id": "a", "qa_mode": "micro", "verdict_path": "qa/a.md"},
            {"task_id": "b", "qa_mode": "micro", "verdict_path": "qa/b.md"},
        ])
        assert r["qualifies"] is True
        assert r["evidence"]["max_finding_severity"] == "low"

    def test_aa002_disqualifies_non_micro_task(self, tmp_qa_dir):
        tmp, qa = tmp_qa_dir
        self._write_verdict(qa, "a.md", "approved")
        self._write_verdict(qa, "b.md", "approved")
        r = self._run_auto_approve(tmp, [
            {"task_id": "a", "qa_mode": "micro", "verdict_path": "qa/a.md"},
            {"task_id": "b", "qa_mode": "standard", "verdict_path": "qa/b.md"},
        ])
        assert r["qualifies"] is False
        assert r["evidence"]["non_micro_tasks"] == ["b"]

    def test_aa003_disqualifies_medium_severity(self, tmp_qa_dir):
        tmp, qa = tmp_qa_dir
        self._write_verdict(qa, "a.md", "approved", ["low"])
        self._write_verdict(qa, "b.md", "approved", ["medium"])
        r = self._run_auto_approve(tmp, [
            {"task_id": "a", "qa_mode": "micro", "verdict_path": "qa/a.md"},
            {"task_id": "b", "qa_mode": "micro", "verdict_path": "qa/b.md"},
        ])
        assert r["qualifies"] is False
        assert r["evidence"]["max_finding_severity"] == "medium"
        assert len(r["evidence"]["tasks_with_blocking_findings"]) == 1

    def test_aa004_disqualifies_rejected_verdict(self, tmp_qa_dir):
        tmp, qa = tmp_qa_dir
        self._write_verdict(qa, "a.md", "approved")
        self._write_verdict(qa, "b.md", "rejected", ["high"])
        r = self._run_auto_approve(tmp, [
            {"task_id": "a", "qa_mode": "micro", "verdict_path": "qa/a.md"},
            {"task_id": "b", "qa_mode": "micro", "verdict_path": "qa/b.md"},
        ])
        assert r["qualifies"] is False
        assert r["evidence"]["non_approved_tasks"][0]["task_id"] == "b"

    def test_aa005_disqualifies_empty_task_list(self, tmp_qa_dir):
        tmp, _ = tmp_qa_dir
        r = self._run_auto_approve(tmp, [])
        assert r["qualifies"] is False
        assert r["evidence"]["total_review_tasks"] == 0

    def test_aa006_disqualifies_missing_verdict_artifact(self, tmp_qa_dir):
        tmp, qa = tmp_qa_dir
        self._write_verdict(qa, "a.md", "approved")
        r = self._run_auto_approve(tmp, [
            {"task_id": "a", "qa_mode": "micro", "verdict_path": "qa/a.md"},
            {"task_id": "b", "qa_mode": "micro", "verdict_path": "qa/missing.md"},
        ])
        assert r["qualifies"] is False
        missing_task = next(t for t in r["evidence"]["non_approved_tasks"] if t["task_id"] == "b")
        assert missing_task["reason"] == "verdict_artifact_missing"
