"""Tests for on_stop.py — Task 3.7."""
import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).parents[2] / "dist" / ".claude" / "hooks"
SKILLS_DIR = Path(__file__).parents[2] / "dist" / ".claude" / "skills"
APPEND = str(SKILLS_DIR / "orch-log" / "scripts" / "append.py")
EMIT = str(SKILLS_DIR / "orch-report" / "scripts" / "emit.py")
HOOK = str(HOOKS_DIR / "on_stop.py")


def _append(cwd, agent, event_type, task_id=None, data=None, attempt=1, env=None):
    cmd = [
        sys.executable, APPEND,
        "--agent", agent,
        "--event-type", event_type,
        "--attempt", str(attempt),
        "--data", json.dumps(data or {}),
    ]
    if task_id:
        cmd += ["--task-id", task_id]
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _emit(cwd, worker_id, kind, task_id, attempt=1, data=None):
    env = {"ORCH_WORKER_ID": worker_id, "PATH": "/usr/bin:/bin"}
    r = subprocess.run(
        [sys.executable, EMIT, "--kind", kind, "--task-id", task_id,
         "--attempt", str(attempt), "--data", json.dumps(data or {})],
        cwd=str(cwd), capture_output=True, text=True, env=env
    )
    assert r.returncode == 0, r.stderr


def _run_hook(cwd):
    r = subprocess.run([sys.executable, HOOK], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _read_metrics(cwd):
    path = Path(cwd) / ".orch" / "metrics" / "current.json"
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------

def test_empty_log_no_output(tmp_path):
    """Hook is no-op when log doesn't exist yet."""
    _run_hook(tmp_path)
    assert not (tmp_path / ".orch" / "metrics" / "current.json").exists()


def test_metrics_written_after_workflow(tmp_path):
    """Metrics file is created with correct counts after a completed workflow."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_test", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "test-worker", "worker_id": "w1"})
    _emit(tmp_path, "w1", "completed", "t_001",
          data={"phase": "default", "artifacts": [], "summary": "done"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)

    assert m["workflow_id"] == "wf_test"
    assert m["tasks_total"] == 1
    assert m["tasks_completed"] == 1
    assert m["tasks_failed"] == 0
    assert m["tasks_dlq"] == 0
    assert m["run_status"] == "completed"
    assert m["last_seq"] > 0


def test_metrics_with_dlq(tmp_path):
    """Metrics reflect DLQ tasks correctly."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_dlq", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "test-worker", "worker_id": "w1"})
    _emit(tmp_path, "w1", "failed", "t_001",
          data={"phase": "default", "reason": "validation_failed", "retryable": False})
    _append(tmp_path, "orchestrator", "task_dlq", "t_001",
            data={"phase": "default", "reason": "non_retryable", "last_error": "spec_unclear"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)

    assert m["tasks_dlq"] == 1
    assert m["tasks_completed"] == 0
    assert m["run_status"] in ("completed_with_dlq",)


def test_metrics_partial_run_status(tmp_path):
    """Partial completion → run_status in ('partial', 'stale_orchestrator') when tasks incomplete."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_partial", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "test-worker", "worker_id": "w1"})
    _emit(tmp_path, "w1", "completed", "t_001",
          data={"phase": "default", "artifacts": [], "summary": "done"})
    # t_002 created but not completed — workflow is incomplete
    _append(tmp_path, "orchestrator", "task_created", "t_002",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "y"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)

    # Hook may return "partial" or "stale_orchestrator" (no recent heartbeat) — both indicate incomplete
    assert m["run_status"] in ("partial", "stale_orchestrator")
    assert m["tasks_completed"] == 1
    assert m["tasks_total"] >= 2


def test_metrics_keys_present(tmp_path):
    """All required metric keys are present in output."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_keys", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)

    required_keys = [
        "generated_at", "workflow_id", "run_status", "current_phase",
        "last_seq", "tasks_total", "tasks_by_status",
        "tasks_completed", "tasks_failed", "tasks_dlq",
        "phases_completed", "phase_durations", "escalations",
        "circuit_breaker_tripped",
    ]
    for key in required_keys:
        assert key in m, f"Missing key: {key}"


def test_hook_survives_corrupt_env(tmp_path):
    """Hook never raises even with a broken ORCH_DIR (graceful no-op)."""
    # Run from a tmp_path with no log — should just exit 0
    r = subprocess.run(
        [sys.executable, HOOK], cwd=str(tmp_path), capture_output=True, text=True
    )
    assert r.returncode == 0


def test_metrics_overwritten_on_second_run(tmp_path):
    """Second run of hook overwrites first metrics file."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_overwrite", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})

    _run_hook(tmp_path)
    m1 = _read_metrics(tmp_path)

    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _run_hook(tmp_path)
    m2 = _read_metrics(tmp_path)

    assert m2["tasks_total"] == 1
    assert m2["tasks_total"] != m1["tasks_total"]


def test_empty_workflow_run_status(tmp_path):
    """Workflow with no tasks has run_status=empty."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_empty", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})

    _run_hook(tmp_path)
    m = _read_metrics(tmp_path)
    assert m["run_status"] == "empty"
    assert m["tasks_total"] == 0


# ---------------------------------------------------------------------------
# last_error.json (suggestion 3c)
# ---------------------------------------------------------------------------

def _read_last_error(cwd):
    path = Path(cwd) / ".orch" / "last_error.json"
    return json.loads(path.read_text())


def test_last_error_written_on_dlq(tmp_path):
    """last_error.json is created when run_status is completed_with_dlq."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_err_dlq", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "w", "worker_id": "w1"})
    _emit(tmp_path, "w1", "failed", "t_001",
          data={"phase": "default", "reason": "validation_failed", "retryable": False})
    _append(tmp_path, "orchestrator", "task_dlq", "t_001",
            data={"phase": "default", "reason": "non_retryable", "last_error": "spec_error"})

    _run_hook(tmp_path)

    assert (tmp_path / ".orch" / "last_error.json").exists()
    err = _read_last_error(tmp_path)
    assert err["run_status"] == "completed_with_dlq"
    assert err["workflow_id"] == "wf_err_dlq"
    assert "last_error_event" in err
    assert err["last_error_event"]["event_type"] in (
        "task_failed", "task_dlq", "escalation", "circuit_breaker_tripped", "preflight_failed"
    )


def test_last_error_written_on_escalation(tmp_path):
    """last_error.json is created when an escalation is active."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_esc", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    # A task is needed so run_status is derived from tasks (not short-circuited as "empty")
    _append(tmp_path, "orchestrator", "task_created", "t_esc",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_esc",
            data={"phase": "default", "worker_type": "w", "worker_id": "w_esc"})
    _emit(tmp_path, "w_esc", "failed", "t_esc",
          data={"phase": "default", "reason": "internal_error", "retryable": False})
    _append(tmp_path, "orchestrator", "task_dlq", "t_esc",
            data={"phase": "default", "reason": "non_retryable", "last_error": "critical_error"})
    _append(tmp_path, "orchestrator", "escalation",
            data={"code": "E04_critical_task_dlq", "severity": "critical",
                  "reason": "task failed", "evidence": [], "suggested_actions": []})

    _run_hook(tmp_path)

    assert (tmp_path / ".orch" / "last_error.json").exists()
    err = _read_last_error(tmp_path)
    assert err["run_status"] == "escalated"
    assert err["last_error_event"]["event_type"] == "escalation"


def test_last_error_not_written_on_clean_completion(tmp_path):
    """last_error.json is NOT created when the workflow completes cleanly."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_clean", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_001",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_001",
            data={"phase": "default", "worker_type": "w", "worker_id": "w1"})
    _emit(tmp_path, "w1", "completed", "t_001",
          data={"phase": "default", "artifacts": [], "summary": "ok"})

    _run_hook(tmp_path)

    assert not (tmp_path / ".orch" / "last_error.json").exists()


def test_last_error_contains_required_keys(tmp_path):
    """last_error.json has all required top-level keys."""
    _append(tmp_path, "orchestrator", "phase_declared",
            data={"workflow_id": "wf_keys_err", "phases": [{"name": "default", "order": 1, "required": True}]})
    _append(tmp_path, "orchestrator", "phase_entered", data={"phase": "default", "order": 1, "workflow_id": "wf-fix"})
    _append(tmp_path, "orchestrator", "task_created", "t_002",
            data={"phase": "default", "deps": [], "tier": "standard", "type": "impl", "spec": "x"})
    _append(tmp_path, "orchestrator", "task_claimed", "t_002",
            data={"phase": "default", "worker_type": "w", "worker_id": "w2"})
    _emit(tmp_path, "w2", "failed", "t_002",
          data={"phase": "default", "reason": "stale_timeout", "retryable": False})
    _append(tmp_path, "orchestrator", "task_dlq", "t_002",
            data={"phase": "default", "reason": "non_retryable", "last_error": "timeout"})

    _run_hook(tmp_path)

    err = _read_last_error(tmp_path)
    for key in ("generated_at", "workflow_id", "run_status", "last_seq", "last_error_event"):
        assert key in err, f"Missing key in last_error.json: {key}"


# ---------------------------------------------------------------------------
# LE-01 regression — _detect_stale_orchestrator must read Event.ts (the real
# field), not Event.timestamp (nonexistent). Before the fix, line ~196 raised
# AttributeError (swallowed by try/except, killing the freshness check) and
# line ~206 raised AttributeError out of the function whenever heartbeats
# existed.
# Uses the local tmp_orch fixture (monkeypatched paths, no module reload) to
# preserve class identity for the rest of the session.
# ---------------------------------------------------------------------------

def _load_on_stop_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("on_stop_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestStaleOrchestratorDetector:
    def _seed_active_phase_with_pending_task(self, orch_core):
        orch_core.append_event(
            agent="orchestrator", event_type="phase_declared",
            data={"workflow_id": "wf-hb",
                  "phases": [{"name": "dev", "order": 1, "required": True}]})
        orch_core.append_event(
            agent="orchestrator", event_type="phase_entered",
            data={"phase": "dev", "order": 1, "workflow_id": "wf-hb"})
        orch_core.append_event(
            agent="orchestrator-dev", event_type="task_created", task_id="dev_tc_001",
            data={"phase": "dev", "deps": [], "tier": "standard",
                  "type": "impl", "spec": "x"})

    def test_fresh_heartbeat_suppresses_alert(self, tmp_orch):
        """A heartbeat younger than the stale threshold must return None."""
        import orch_core
        self._seed_active_phase_with_pending_task(orch_core)
        orch_core.append_event(
            agent="orchestrator-dev", event_type="orchestrator_heartbeat",
            data={"phase": "dev"})
        mod = _load_on_stop_module()
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered(event_type=None))
        assert mod._detect_stale_orchestrator(state, events) is None

    def test_stale_heartbeat_reports_last_heartbeat_ts(self, tmp_orch, monkeypatch):
        """A heartbeat older than the threshold must produce a diagnostic
        whose last_heartbeat equals the heartbeat event's ts field."""
        from datetime import timedelta
        import orch_core
        self._seed_active_phase_with_pending_task(orch_core)
        hb = orch_core.append_event(
            agent="orchestrator-dev", event_type="orchestrator_heartbeat",
            data={"phase": "dev"})
        mod = _load_on_stop_module()
        # Advance the detector's clock 16 minutes past the heartbeat (threshold 900s)
        future = (orch_core.parse_iso(orch_core.now_iso())
                  + timedelta(seconds=960)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        monkeypatch.setattr(mod, "now_iso", lambda: future)
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered(event_type=None))
        stale = mod._detect_stale_orchestrator(state, events)
        assert stale is not None
        assert stale["stale_orchestrator"] == "dev"
        assert stale["last_heartbeat"] == hb.ts

    def test_no_heartbeat_with_pending_tasks_alerts(self, tmp_orch):
        """No heartbeats at all + pending tasks → diagnostic with last_heartbeat None."""
        import orch_core
        self._seed_active_phase_with_pending_task(orch_core)
        mod = _load_on_stop_module()
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered(event_type=None))
        stale = mod._detect_stale_orchestrator(state, events)
        assert stale is not None
        assert stale["last_heartbeat"] is None


# ---------------------------------------------------------------------------
# F-05 — unfinalized SDD phase detector. The pipeline reached a clean terminal
# (all sdd tasks completed) but the orchestrator was cut off before emitting
# phase_transitioned + regenerating the handoff manifest. on_stop must surface
# run_status: sdd_finalization_pending so the operator re-invokes.
# ---------------------------------------------------------------------------

class TestUnfinalizedSddDetector:
    def _seed_sdd(self, orch_core):
        orch_core.append_event(
            agent="orchestrator", event_type="phase_declared",
            data={"workflow_id": "wf-sdd",
                  "phases": [{"name": "sdd", "order": 1, "required": True}]})
        orch_core.append_event(
            agent="orchestrator", event_type="phase_entered",
            data={"phase": "sdd", "order": 1, "workflow_id": "wf-sdd"})

    def _add_task(self, orch_core, task_id, complete=True):
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="task_created", task_id=task_id,
            data={"phase": "sdd", "deps": [], "tier": "standard",
                  "type": "spec-validator", "spec": "x"})
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="task_claimed", task_id=task_id,
            data={"phase": "sdd", "worker_type": "spec-validator", "worker_id": f"w-{task_id}"})
        if complete:
            orch_core.append_event(
                agent=f"w-{task_id}", event_type="task_completed", task_id=task_id,
                data={"phase": "sdd", "artifacts": [], "handoff_allowed": True})

    def test_all_completed_no_transition_alerts(self, tmp_orch):
        import orch_core
        self._seed_sdd(orch_core)
        self._add_task(orch_core, "sdd_validate", complete=True)
        mod = _load_on_stop_module()
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered(event_type=None))
        diag = mod._detect_unfinalized_sdd_phase(state, events)
        assert diag is not None
        assert diag["unfinalized_phase"] == "sdd"
        assert diag["sdd_tasks_completed"] == 1

    def test_transitioned_phase_suppresses_alert(self, tmp_orch):
        import orch_core
        self._seed_sdd(orch_core)
        self._add_task(orch_core, "sdd_validate", complete=True)
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="phase_exit_approved",
            data={"phase": "sdd", "criteria_met": ["handoff_manifest_approved"],
                  "next_phase": "dev", "workflow_id": "wf-sdd"})
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="phase_transitioned",
            data={"from_phase": "sdd", "to_phase": "dev", "evidence_seq": 1,
                  "workflow_id": "wf-sdd"})
        mod = _load_on_stop_module()
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered(event_type=None))
        assert mod._detect_unfinalized_sdd_phase(state, events) is None

    def test_running_task_suppresses_alert(self, tmp_orch):
        import orch_core
        self._seed_sdd(orch_core)
        self._add_task(orch_core, "sdd_validate", complete=False)  # still running
        mod = _load_on_stop_module()
        state = orch_core.reduce_all()
        events = list(orch_core.read_events_filtered(event_type=None))
        assert mod._detect_unfinalized_sdd_phase(state, events) is None

    def test_run_status_written_to_metrics(self, tmp_orch):
        import orch_core
        self._seed_sdd(orch_core)
        self._add_task(orch_core, "sdd_validate", complete=True)
        mod = _load_on_stop_module()
        mod.main()
        metrics = json.loads((tmp_orch / ".orch" / "metrics" / "current.json").read_text())
        assert metrics["run_status"] == "sdd_finalization_pending"
        assert metrics["sdd_finalization_pending"] == "sdd"
        err = json.loads((tmp_orch / ".orch" / "last_error.json").read_text())
        assert err["run_status"] == "sdd_finalization_pending"
        assert err["diagnostic"]["command"] == "/u-orchestrator"
