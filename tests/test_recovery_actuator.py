"""R07 — recovery needs an actuator that does not depend on an orchestrator.

Every recovery mechanism in the engine — promoting a due `task_scheduled_retry`,
reaping a silent worker, resolving a lingering FAILED — ran ONLY inside a phase
orchestrator's dispatch loop. The detector was the session Stop hook. So:

    seq 5  23:09:25  task_claimed          triage
    seq 6  23:19:36  task_failed           agent=stale-monitor reason=stale_timeout
    seq 7  23:19:36  task_scheduled_retry  next_retry_at=23:20:02
                     <- end of log. The retry never fired.

`on_stop.py` scheduled a recovery at the exact moment the only actuator able to
run it ceased to exist. The other measured case cost 63 min: the log's last event
was a SUCCESSFUL task_completed, with three Task Contracts ready on disk.

Closed by:
  R07b  recovery_tick.py, run from SessionStart — opening a session recovers
  R07c  on_stop.py escalates the orphaned retry into the LOG, not a side file
  R07a  check_supervisor_lease.py records whether anything is watching (advisory)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
RECOVERY = dist / "scripts" / "recovery_tick.py"
LEASE = dist / "scripts" / "check_supervisor_lease.py"

# The estalo1 evidence, replayed structurally: a claimed task reaped by the stop
# hook, its retry scheduled, and nothing after it.
_ESTALO_WF = "motor-derivacao-sujeito"


def _run(script: Path, project_dir: Path, *args) -> tuple[int, dict]:
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir)}
    env.pop("ORCH_WORKFLOW_ID", None)
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(project_dir), env=env, capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode, json.loads(out)


def _events(project_dir: Path) -> list[dict]:
    log = project_dir / ".orch" / "log.jsonl"
    if not log.is_file():
        return []
    return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]


def _orphaned_retry_scenario(orch_dir, make_event, make_active_phase):
    """A task reaped and retry-scheduled, with no orchestrator left to promote it."""
    make_active_phase("sdd", workflow_id=_ESTALO_WF)
    make_event("task_created", task_id=f"sdd_{_ESTALO_WF}_triage", data={
        "phase": "sdd", "tier": "standard", "type": "spec-triage", "spec": "",
        "deps": [], "workflow_id": _ESTALO_WF,
    })
    make_event("task_claimed", task_id=f"sdd_{_ESTALO_WF}_triage", data={
        "phase": "sdd", "worker_type": "u-spec-triage", "worker_id": "w1",
    })
    failed = make_event("task_failed", task_id=f"sdd_{_ESTALO_WF}_triage", data={
        "phase": "sdd", "reason": "stale_timeout", "retryable": True,
    })
    make_event("task_scheduled_retry", task_id=f"sdd_{_ESTALO_WF}_triage", data={
        "phase": "sdd", "next_retry_at": "2026-07-26T23:20:02Z",
        "backoff_seconds": 26.6, "previous_failure_seq": failed.seq,
    })


# ---------------------------------------------------------------------------
# R07b — the actuator
# ---------------------------------------------------------------------------

class TestRecoveryTickIsFailSoft:
    """A SessionStart hook that raises would break the session it exists to help."""

    def test_no_orch_directory_is_a_noop(self, tmp_path):
        rc, out = _run(RECOVERY, tmp_path)
        assert rc == 0 and out["status"] == "noop"

    def test_empty_log_is_a_noop(self, tmp_path):
        (tmp_path / ".orch").mkdir()
        (tmp_path / ".orch" / "log.jsonl").write_text("", encoding="utf-8")
        rc, out = _run(RECOVERY, tmp_path)
        assert rc == 0 and out["status"] in ("noop", "attention")

    def test_corrupt_log_never_raises(self, tmp_path):
        (tmp_path / ".orch").mkdir()
        (tmp_path / ".orch" / "log.jsonl").write_text("{not json\n", encoding="utf-8")
        rc, out = _run(RECOVERY, tmp_path)
        assert rc == 0, "a SessionStart hook must never fail the session"
        assert out["status"] in ("error", "noop")

    def test_always_exits_zero(self, tmp_path):
        rc, _ = _run(RECOVERY, tmp_path, "--workflow-id", "nope")
        assert rc == 0


class TestRecoveryTickPromotesTheOrphanedRetry:
    def test_the_estalo_case_recovers(self, orch_dir, make_event, make_active_phase):
        """The exact production stall: a scheduled retry with no actuator."""
        _orphaned_retry_scenario(orch_dir, make_event, make_active_phase)
        rc, out = _run(RECOVERY, orch_dir, "--now", "2026-07-26T23:25:00Z")
        assert rc == 0
        assert out["status"] == "recovered"
        assert f"sdd_{_ESTALO_WF}_triage" in out["retried"], (
            "the due retry must be promoted — this is the 20 minutes that were lost"
        )

    def test_recovery_is_recorded_in_the_log(self, orch_dir, make_event, make_active_phase):
        _orphaned_retry_scenario(orch_dir, make_event, make_active_phase)
        _run(RECOVERY, orch_dir, "--now", "2026-07-26T23:25:00Z")
        types = [e["event_type"] for e in _events(orch_dir)]
        assert "task_retried" in types

    def test_escalation_makes_the_state_visible(self, orch_dir, make_event, make_active_phase):
        """A passive last_error.json is how 63 minutes went unnoticed."""
        _orphaned_retry_scenario(orch_dir, make_event, make_active_phase)
        _run(RECOVERY, orch_dir, "--now", "2026-07-26T23:25:00Z")
        codes = [
            (e.get("data") or {}).get("code") for e in _events(orch_dir)
            if e["event_type"] == "escalation"
        ]
        assert "E26_workflow_left_unattended" in codes

    def test_escalation_is_emitted_once(self, orch_dir, make_event, make_active_phase):
        """Repeating it every session would bury the signal."""
        _orphaned_retry_scenario(orch_dir, make_event, make_active_phase)
        _run(RECOVERY, orch_dir, "--now", "2026-07-26T23:25:00Z")
        _run(RECOVERY, orch_dir, "--now", "2026-07-26T23:30:00Z")
        codes = [
            (e.get("data") or {}).get("code") for e in _events(orch_dir)
            if e["event_type"] == "escalation"
        ]
        assert codes.count("E26_workflow_left_unattended") == 1

    def test_dry_run_emits_nothing(self, orch_dir, make_event, make_active_phase):
        _orphaned_retry_scenario(orch_dir, make_event, make_active_phase)
        before = len(_events(orch_dir))
        rc, out = _run(RECOVERY, orch_dir, "--dry-run",
                       "--now", "2026-07-26T23:25:00Z")
        assert rc == 0 and out["status"] == "attention"
        assert len(_events(orch_dir)) == before

    def test_all_terminal_workflow_is_left_alone(self, orch_dir, make_event, make_active_phase):
        make_active_phase("sdd", workflow_id="wf-done")
        make_event("task_created", task_id="sdd_wf-done_t1", data={
            "phase": "sdd", "tier": "standard", "type": "spec-triage", "spec": "",
            "deps": [], "workflow_id": "wf-done",
        })
        make_event("task_claimed", task_id="sdd_wf-done_t1", data={
            "phase": "sdd", "worker_type": "w", "worker_id": "w1"})
        make_event("task_completed", task_id="sdd_wf-done_t1", data={
            "phase": "sdd", "artifacts": ["a.json"], "summary": "ok"})
        before = len(_events(orch_dir))
        rc, out = _run(RECOVERY, orch_dir)
        assert rc == 0 and out["non_terminal"] == 0
        assert len(_events(orch_dir)) == before, "nothing to recover, nothing emitted"


class TestSessionStartHookIsRegistered:
    def test_settings_declares_the_hook(self):
        settings = json.loads(
            (dist / "settings.json").read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {}).get("SessionStart", [])
        assert hooks, "recovery_tick.py has no SessionStart registration"
        flat = json.dumps(hooks)
        assert "recovery_tick.py" in flat

    def test_hook_passes_the_project_dir(self):
        settings = json.loads(
            (dist / "settings.json").read_text(encoding="utf-8"))
        flat = json.dumps(settings["hooks"]["SessionStart"])
        assert "ORCH_PROJECT_DIR" in flat


# ---------------------------------------------------------------------------
# R07c — the orphaned retry is escalated into the log
# ---------------------------------------------------------------------------

class TestOnStopEscalatesOrphanedRetry:
    def test_helper_exists_and_is_wired(self):
        src = (dist / "hooks" / "on_stop.py").read_text(encoding="utf-8")
        assert "_escalate_orphaned_retry" in src
        assert "E27_retry_scheduled_without_actuator" in src

    def test_reaped_result_is_captured_not_discarded(self):
        """The old code called reap_stale_tasks() and threw the result away."""
        src = (dist / "hooks" / "on_stop.py").read_text(encoding="utf-8")
        assert "reaped = reap_stale_tasks()" in src

    def test_escalation_is_emitted_once_per_workflow(self, orch_dir, make_event,
                                                     make_active_phase):
        sys.path.insert(0, str(dist / "lib"))
        sys.path.insert(0, str(dist / "hooks"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "on_stop_mod", dist / "hooks" / "on_stop.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        import orch_core
        make_active_phase("sdd", workflow_id="wf-x")
        state = orch_core.reduce_all()
        mod._escalate_orphaned_retry(["t1"], state)
        mod._escalate_orphaned_retry(["t1"], state)
        codes = [
            (e.get("data") or {}).get("code") for e in _events(orch_dir)
            if e["event_type"] == "escalation"
        ]
        assert codes.count("E27_retry_scheduled_without_actuator") == 1

    def test_codes_are_in_the_master_catalog(self):
        catalog = (dist / "ESCALATION_CODES.md").read_text(encoding="utf-8")
        for code in ("E26_workflow_left_unattended",
                     "E27_retry_scheduled_without_actuator",
                     "E28_no_supervisor_lease"):
            assert f"`{code}`" in catalog


# ---------------------------------------------------------------------------
# R07a — the lease is advisory, and says so
# ---------------------------------------------------------------------------

class TestSupervisorLeaseIsAdvisory:
    def test_no_supervisor_activity_reports_unleased(self, orch_dir, make_event,
                                                     make_active_phase):
        make_active_phase("sdd", workflow_id="wf-x")
        rc, out = _run(LEASE, orch_dir, "--workflow-id", "wf-x")
        assert rc == 0, "an advisory check must never block"
        assert out["leased"] is False
        assert "/u-supervise" in out["advice"]

    def test_recent_supervisor_activity_is_a_lease(self, orch_dir, make_event,
                                                   make_active_phase):
        make_active_phase("sdd", workflow_id="wf-x")
        make_event("orchestrator_resumed", data={
            "phase": "sdd", "workflow_id": "wf-x", "operator": "supervisor"})
        rc, out = _run(LEASE, orch_dir, "--workflow-id", "wf-x")
        assert rc == 0 and out["leased"] is True
        assert out["age_seconds"] is not None

    def test_expired_activity_is_not_a_lease(self, orch_dir, make_event,
                                            make_active_phase):
        """A supervisor that ran hours ago is not running now.

        Uses a future `--now` rather than a zero TTL: age past the window is the
        real condition, and it keeps the boundary (age == ttl still leased) intact.
        """
        make_active_phase("sdd", workflow_id="wf-x")
        make_event("orchestrator_resumed", data={
            "phase": "sdd", "workflow_id": "wf-x", "operator": "supervisor"})
        rc, out = _run(LEASE, orch_dir, "--workflow-id", "wf-x",
                       "--now", "2099-01-01T00:00:00Z")
        assert rc == 0 and out["leased"] is False
        assert "past the" in out["advice"]
        assert out["age_seconds"] > out["ttl_seconds"]

    def test_exit_code_is_always_zero(self, tmp_path):
        rc, _ = _run(LEASE, tmp_path)
        assert rc == 0

    def test_meta_orchestrator_never_blocks_on_it(self):
        text = (dist / "agents" / "orchestrator.md").read_text(encoding="utf-8")
        idx = text.index("check_supervisor_lease.py")
        window = text[idx:idx + 1800]
        assert "never blocks phase entry" in window
        assert "E28_no_supervisor_lease" in window

    def test_rationale_names_the_attended_mode(self):
        """Blocking would break the mode every measured workflow actually used."""
        text = (dist / "agents" / "orchestrator.md").read_text(encoding="utf-8")
        idx = text.index("check_supervisor_lease.py")
        assert "attended mode" in text[idx:idx + 1800]
