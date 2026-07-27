"""R12 — per-session subagent spawn budget.

Production failure: an SDD fan-out spent the host's spawn budget mid-pipeline.
The Agent tool then failed for a task that was ALREADY claimed, producing

    task_failed reason=worker_exited_without_terminal retryable=true
    error="Agent spawn limit (200) exhausted in session."

`worker_exited_without_terminal` is a structural reason capped at one retry, so a
condition that cannot change until the session ends was spending the task's
retry budget. The recovery that actually worked was a fresh session — meaning the
correct handling is to STOP dispatching and leave state untouched, not to retry.
"""
import json
import os
import subprocess
import sys

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
SCRIPT = dist / "scripts" / "check_spawn_budget.py"
ORCHESTRATORS = ["orchestrator-sdd", "orchestrator-dev",
                 "orchestrator-review", "orchestrator-test"]


def _run(project_dir, *args):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir)}
    env.pop("ORCH_WORKFLOW_ID", None)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(project_dir), env=env,
        capture_output=True, text=True, timeout=30,
    )
    out = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode, json.loads(out)


def _claims(make_event, n, workflow_id="wf"):
    """`n` spawn attempts, interleaved with noise that must not be counted."""
    for i in range(n):
        make_event("task_claimed", task_id=f"sdd_{workflow_id}_t{i}",
                   data={"phase": "sdd", "workflow_id": workflow_id,
                         "worker_id": f"w{i}", "worker_type": "u-spec-back"})
        make_event("task_progress", task_id=f"sdd_{workflow_id}_t{i}",
                   data={"phase": "sdd", "checkpoint": "context_loaded",
                         "note": "context_loaded"})


class TestBudgetStates:
    def test_counts_only_task_claimed(self, orch_dir, make_event):
        _claims(make_event, 5)
        rc, out = _run(orch_dir, "--since-seq", "0", "--budget", "200")
        assert rc == 0
        assert out["spawned"] == 5, "task_progress must not count as a spawn"
        assert out["state"] == "ok"
        assert out["remaining"] == 195

    def test_low_state_exits_three(self, orch_dir, make_event):
        _claims(make_event, 8)
        rc, out = _run(orch_dir, "--since-seq", "0", "--budget", "10")
        assert rc == 3 and out["state"] == "low"

    def test_exhausted_state_exits_four(self, orch_dir, make_event):
        _claims(make_event, 10)
        rc, out = _run(orch_dir, "--since-seq", "0", "--budget", "10")
        assert rc == 4 and out["state"] == "exhausted"
        assert out["remaining"] == 0

    def test_low_and_exhausted_exit_codes_differ(self, orch_dir, make_event):
        """3 vs 4 = 'warn and continue' vs 'stop dispatching'."""
        _claims(make_event, 9)
        low, _ = _run(orch_dir, "--since-seq", "0", "--budget", "10")
        _claims(make_event, 1, workflow_id="wf2")
        exhausted, _ = _run(orch_dir, "--since-seq", "0", "--budget", "10")
        assert (low, exhausted) == (3, 4)

    def test_warn_ratio_is_configurable(self, orch_dir, make_event):
        _claims(make_event, 6)
        rc_default, _ = _run(orch_dir, "--since-seq", "0", "--budget", "10")
        rc_tight, out = _run(orch_dir, "--since-seq", "0", "--budget", "10",
                             "--warn-ratio", "0.5")
        assert rc_default == 0, "0.6 is under the 0.8 default"
        assert rc_tight == 3 and out["state"] == "low"


class TestInvocationScoping:
    def test_since_seq_excludes_earlier_invocations(self, orch_dir, make_event):
        """The budget is per session; the log spans sessions.

        `--since-seq` is the orchestrator's own `log_seq_at_spawn`, so spawns
        from previous invocations must not count against this one.
        """
        _claims(make_event, 5)
        boundary = make_event("orchestrator_heartbeat", data={"phase": "sdd"}).seq
        _claims(make_event, 2, workflow_id="wf2")

        _, all_out = _run(orch_dir, "--since-seq", "0", "--budget", "200")
        _, recent = _run(orch_dir, "--since-seq", str(boundary), "--budget", "200")
        assert all_out["spawned"] == 7
        assert recent["spawned"] == 2

    def test_workflow_id_filters_other_workflows(self, orch_dir, make_event):
        _claims(make_event, 3, workflow_id="mine")
        _claims(make_event, 4, workflow_id="other")
        _, out = _run(orch_dir, "--since-seq", "0", "--workflow-id", "mine")
        assert out["spawned"] == 3

    def test_missing_log_is_full_budget_not_an_error(self, tmp_path):
        rc, out = _run(tmp_path, "--since-seq", "0")
        assert rc == 0 and out["spawned"] == 0 and out["state"] == "ok"


class TestUsageErrors:
    def test_zero_budget_is_rejected(self, orch_dir, make_event):
        _claims(make_event, 1)
        rc, out = _run(orch_dir, "--since-seq", "0", "--budget", "0")
        assert rc == 1 and out["reason"] == "invalid_budget"


class TestOrchestratorWiring:
    @pytest.mark.parametrize("name", ORCHESTRATORS)
    def test_every_orchestrator_checks_the_budget(self, name):
        text = (dist / "agents" / f"{name}.md").read_text(encoding="utf-8")
        assert "check_spawn_budget.py" in text, (
            f"{name} dispatches workers without checking the spawn budget"
        )

    @pytest.mark.parametrize("name", ORCHESTRATORS)
    def test_every_orchestrator_declares_e24(self, name):
        text = (dist / "agents" / f"{name}.md").read_text(encoding="utf-8")
        assert "E24_spawn_budget_exhausted" in text

    @pytest.mark.parametrize("name", ORCHESTRATORS)
    def test_wiring_branches_on_exit_code(self, name):
        """Prose must point at the exit code, not at the JSON (R01's lesson)."""
        text = (dist / "agents" / f"{name}.md").read_text(encoding="utf-8")
        idx = text.index("check_spawn_budget.py")
        window = text[idx:idx + 1600]
        assert "exit code" in window.lower()
        assert "--since-seq" in window

    def test_e24_is_in_the_master_catalog(self):
        catalog = (dist / "ESCALATION_CODES.md").read_text(encoding="utf-8")
        assert "`E24_spawn_budget_exhausted`" in catalog

    def test_check_runs_before_claiming(self):
        """Claiming first IS the production bug: a claimed task that never ran
        burns one of its two structural retry attempts."""
        text = (dist / "agents" / "orchestrator-sdd.md").read_text(encoding="utf-8")
        assert text.index("check_spawn_budget.py") < text.index("#### 5.2 — Claim batch")
