"""Layer Hard Stale Runtime — wire stale_tasks() into a deterministic runtime path (task 06).

A2-F1: stale_tasks() was tested but had ZERO runtime callers — a hung worker
(process alive, no events) was only caught by a prompt-level check. Now
orch_core.reap_stale_tasks() emits task_failed(reason=stale_timeout) from Python,
invoked by check_stale.py (orchestrator Step 5.0) and by on_stop.py.
A2-F6: the divergent threshold tables collapse onto Tier.default_stale_seconds.
"""
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
CHECK = ROOT / "dist" / ".claude" / "scripts" / "check_stale.py"
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))


def _seed_running_task(make_event):
    make_event("phase_declared", data={"workflow_id": "w", "phases": [{"name": "dev", "order": 2, "required": True}]})
    make_event("phase_entered", data={"phase": "dev", "order": 2, "workflow_id": "w"})
    make_event("task_created", task_id="T1", data={"phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": []})
    make_event("task_claimed", task_id="T1", data={"phase": "dev", "worker_type": "u-be-developer", "worker_id": "w1"})


def _future(orch_core, seconds):
    return (orch_core.parse_iso(orch_core.now_iso()) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class TestReapStaleTasks:
    def test_reap_emits_stale_timeout_for_overdue_running(self, orch_dir, make_event):
        import orch_core
        _seed_running_task(make_event)
        reaped = orch_core.reap_stale_tasks(_future(orch_core, 2000))  # > impl override 1200s (F-02)
        assert reaped == ["T1"]
        st = orch_core.reduce_all()
        assert st.tasks["T1"].status == orch_core.TaskStatus.FAILED
        assert st.tasks["T1"].last_failure_reason == "stale_timeout"

    def test_no_reap_when_recent(self, orch_dir, make_event):
        import orch_core
        _seed_running_task(make_event)
        assert orch_core.reap_stale_tasks() == []   # just claimed -> not stale

    def test_reap_is_idempotent(self, orch_dir, make_event):
        import orch_core
        _seed_running_task(make_event)
        future = _future(orch_core, 2000)
        assert orch_core.reap_stale_tasks(future) == ["T1"]
        # second pass: T1 already FAILED (not RUNNING) -> nothing to reap
        assert orch_core.reap_stale_tasks(future) == []


class TestCheckStaleCli:
    def test_cli_emits_and_reports(self, orch_dir, make_event):
        import orch_core
        _seed_running_task(make_event)
        future = _future(orch_core, 2000)
        p = subprocess.run([sys.executable, str(CHECK), "--now", future],
                           capture_output=True, text=True,
                           env={**os.environ, "ORCH_PROJECT_DIR": str(orch_dir)})
        assert p.returncode == 0, p.stderr
        out = json.loads(p.stdout)
        assert out["stale_count"] == 1 and "T1" in out["failed"]


class TestThresholdsUnified:
    def test_single_source_of_truth(self):
        from orch_core import Tier
        assert Tier.STANDARD.default_stale_seconds == 300
        assert Tier.CRITICAL.default_stale_seconds == 600
        assert Tier.BULK.default_stale_seconds == 120

    def test_orchestrator_dev_prompt_matrix_removed(self):
        # A2-F6: the divergent in-prompt threshold matrix (impl=900/600) must be gone.
        src = (ROOT / "dist/.claude/agents/orchestrator-dev.md").read_text()
        assert "check_stale.py" in src
        assert "impl=900" not in src and "impl = 900" not in src
