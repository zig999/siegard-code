"""Layer Hard DLQ Gate — DLQ-blocking policy encoded in the terminal-gate met (task 07).

A4-F4: check_all_test_tasks_terminal.py excluded DLQ from `met`, so a DLQ'd test
task passed the gate (the "DLQ blocks" intent lived only in the orchestrator prompt).
Now: test terminal gate met = (non_terminal==0 AND dlq==0) and exits 1 on DLQ.
Dev keeps DLQ as an accepted terminal (documented policy) but surfaces it in evidence.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEST_TERMINAL = ROOT / "dist/.claude/skills/phase-test-rules/scripts/check_all_test_tasks_terminal.py"
DEV_TERMINAL = ROOT / "dist/.claude/skills/phase-dev-rules/scripts/check_all_impl_tasks_terminal.py"
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))


def _run(script, project_dir):
    return subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                          env={**os.environ, "ORCH_PROJECT_DIR": str(project_dir)})


def _seed(make_event, phase, statuses):
    make_event("phase_declared", data={"workflow_id": "w", "phases": [{"name": phase, "order": 2, "required": True}]})
    make_event("phase_entered", data={"phase": phase, "order": 2, "workflow_id": "w"})
    for i, st in enumerate(statuses):
        tid = f"T{i}"
        make_event("task_created", task_id=tid, data={"phase": phase, "tier": "standard", "type": "impl", "spec": "s", "deps": []})
        make_event("task_claimed", task_id=tid, data={"phase": phase, "worker_type": "w", "worker_id": f"w{i}"})
        if st == "completed":
            make_event("task_completed", task_id=tid, data={"phase": phase, "artifacts": [f"{tid}.md"]})
        else:  # dlq
            make_event("task_failed", task_id=tid, data={"phase": phase, "reason": "max_attempts_exceeded", "retryable": False})
            make_event("task_dlq", task_id=tid, data={"phase": phase, "reason": "max_attempts_exceeded", "last_error": "exhausted"})


class TestTestPhaseDlqBlocks:
    def test_dlq_blocks_test_terminal(self, orch_dir, make_event):
        _seed(make_event, "test", ["completed", "dlq"])
        p = _run(TEST_TERMINAL, orch_dir)
        out = json.loads(p.stdout)
        assert out["met"] is False           # DLQ present -> deterministic block
        assert p.returncode != 0             # and exit 1 (not prompt-trusted)

    def test_all_completed_test_passes(self, orch_dir, make_event):
        _seed(make_event, "test", ["completed", "completed"])
        p = _run(TEST_TERMINAL, orch_dir)
        assert json.loads(p.stdout)["met"] is True
        assert p.returncode == 0


class TestDevPhaseDlqAcceptedTerminal:
    def test_dlq_accepted_but_flagged(self, orch_dir, make_event):
        _seed(make_event, "dev", ["completed", "dlq"])
        p = _run(DEV_TERMINAL, orch_dir)
        out = json.loads(p.stdout)
        assert out["met"] is True            # dev policy: DLQ is an accepted terminal
        assert out["evidence"]["dlq_blocks_criterion"] is True   # ...but explicitly surfaced
