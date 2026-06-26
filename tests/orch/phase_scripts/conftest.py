"""
Shared fixtures and helpers for phase_scripts tests (Level A).

All check scripts are invoked as subprocesses so that module-level env vars
(ORCH_PROJECT_DIR, SPECS_DIR) are resolved correctly inside each script.

Log building uses orch_core in-process (via the parent conftest's tmp_orch
fixture) and the subprocess finds the same log because orch_core derives
its paths from ORCH_PROJECT_DIR at import time.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[3] / "dist" / ".claude" / "skills"


def _script(phase: str, name: str) -> Path:
    return SKILLS_DIR / f"phase-{phase}-rules" / "scripts" / name


DEV_SCRIPTS = {
    "check_terminal": _script("dev", "check_all_impl_tasks_terminal.py"),
    "check_qa_ready": _script("dev", "check_all_deliveries_qa_ready.py"),
    "check_prohibitions": _script("dev", "check_no_open_prohibitions.py"),
    "check_spec_coverage": _script("dev", "check_spec_requirements_covered.py"),
    "select_worker": _script("dev", "select_worker.py"),
}

SDD_SCRIPTS = {
    "check_manifest": _script("sdd", "check_handoff_manifest_approved.py"),
    "check_domains": _script("sdd", "check_all_domains_validated.py"),
    "check_error_codes": _script("sdd", "check_error_codes_synced.py"),
    "select_worker": _script("sdd", "select_worker.py"),
}

REVIEW_SCRIPTS = {
    "check_verdicts": _script("review", "check_all_qa_verdicts_approved.py"),
    "check_critical": _script("review", "check_no_open_critical_findings.py"),
    "check_docs": _script("review", "check_documentation_verified.py"),
    "check_placeholders": _script("review", "check_no_orphan_placeholders.py"),
    "select_worker": _script("review", "select_worker.py"),
}

TEST_SCRIPTS = {
    "check_terminal": _script("test", "check_all_test_tasks_terminal.py"),
    "check_passed": _script("test", "check_all_tests_passed.py"),
    "check_critical": _script("test", "check_no_critical_failures.py"),
    "select_worker": _script("test", "select_worker.py"),
}


def run_check(script_path: Path, project_dir: Path, extra_env: dict | None = None) -> dict:
    """Run a check script as subprocess; returns parsed JSON output."""
    env = {
        **os.environ,
        "ORCH_PROJECT_DIR": str(project_dir),
        "SPECS_DIR": "specs",
        **(extra_env or {}),
    }
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True, env=env, cwd=str(project_dir),
    )
    out = result.stdout.strip()
    err = result.stderr.strip()
    if out:
        return json.loads(out)
    if err:
        try:
            return json.loads(err)
        except json.JSONDecodeError:
            pass
    pytest.fail(f"Script produced no JSON output.\nstdout: {out}\nstderr: {err}")


def run_select(script_path: Path, task_type: str, stack: str | None = None) -> dict:
    """Run a select_worker script; returns parsed JSON."""
    args = [sys.executable, str(script_path), "--task-type", task_type]
    if stack:
        args += ["--stack", stack]
    result = subprocess.run(args, capture_output=True, text=True)
    # task 10 (A4-F5): an unknown task_type now errors (exit nonzero, JSON on stderr).
    out = result.stdout.strip()
    return json.loads(out) if out else json.loads(result.stderr)


@pytest.fixture
def phase_env(tmp_orch):
    """Returns tmp_path with ORCH_PROJECT_DIR implicitly set for subprocess calls.

    The tmp_orch fixture (from parent conftest) already monkeypatches orch_core so
    in-process append_event() writes to tmp_path/.orch/log.jsonl. Subprocesses
    invoked with project_dir=tmp_orch also find the same log because orch_core
    derives ORCH_DIR from ORCH_PROJECT_DIR env var at import time.
    """
    return tmp_orch
