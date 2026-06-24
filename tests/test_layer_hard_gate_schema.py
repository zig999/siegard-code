"""Layer Hard Gate Schema — uniform gate output + strict select_worker (task 10).

A4-F6 (Option B, user-chosen): every phase exit-criteria gate emits the same
superset {status, check, criterion, met, timestamp, evidence}. dev/sdd already
did; this adds the missing keys to the review/test gates (additive — no reader
of the existing keys breaks; the SDD orchestrator's status/check/timestamp
contract is preserved).
A4-F5: select_worker.py exits non-zero on an unknown task_type instead of
silently routing to DEFAULT_WORKER.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SK = ROOT / "dist" / ".claude" / "skills"
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))

REVIEW_TEST_GATES = [
    "phase-review-rules/scripts/check_all_qa_verdicts_approved.py",
    "phase-review-rules/scripts/check_no_open_critical_findings.py",
    "phase-review-rules/scripts/check_documentation_verified.py",
    "phase-review-rules/scripts/check_no_orphan_placeholders.py",
    "phase-test-rules/scripts/check_all_test_tasks_terminal.py",
    "phase-test-rules/scripts/check_all_tests_passed.py",
    "phase-test-rules/scripts/check_no_critical_failures.py",
]
SUPERSET = {"status", "check", "criterion", "met", "timestamp", "evidence"}

SELECT_WORKERS = [
    "phase-dev-rules/scripts/select_worker.py",
    "phase-sdd-rules/scripts/select_worker.py",
    "phase-review-rules/scripts/select_worker.py",
    "phase-test-rules/scripts/select_worker.py",
]


class TestGateSchemaUniform:
    def test_review_test_gates_emit_superset(self, orch_dir, make_event):
        # seed a log so reduce_all() has a file to read
        make_event("phase_declared", data={"workflow_id": "w", "phases": [{"name": "review", "order": 3, "required": True}]})
        for rel in REVIEW_TEST_GATES:
            p = subprocess.run([sys.executable, str(SK / rel)], capture_output=True, text=True,
                               env={**os.environ, "ORCH_PROJECT_DIR": str(orch_dir)})
            assert p.stdout, f"{rel} produced no stdout (stderr={p.stderr[:200]})"
            out = json.loads(p.stdout)
            missing = SUPERSET - set(out)
            assert not missing, f"{rel} missing keys {missing} (has {sorted(out)})"
            # status must agree with met
            assert out["status"] in ("ok", "blocked")
            assert (out["status"] == "ok") == bool(out["met"])


class TestSelectWorkerStrict:
    def test_unknown_task_type_errors(self):
        for rel in SELECT_WORKERS:
            p = subprocess.run([sys.executable, str(SK / rel), "--task-type", "bogus_xyz", "--stack", "be"],
                               capture_output=True, text=True)
            assert p.returncode != 0, f"{rel} did not error on unknown task_type"

    def test_known_task_type_still_resolves(self):
        # dev: ('impl','be') -> a real worker, exit 0
        p = subprocess.run([sys.executable, str(SK / "phase-dev-rules/scripts/select_worker.py"),
                            "--task-type", "impl", "--stack", "be"], capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        assert json.loads(p.stdout)["worker"]
