"""Tests for orch-state scripts: reduce.py, summary.py, current_phase.py."""
import json
import subprocess
import sys
from pathlib import Path

_BASE = Path(__file__).parent.parent / ".claude"
REDUCE_SCRIPT = _BASE / "skills" / "orch-state" / "scripts" / "reduce.py"
SUMMARY_SCRIPT = _BASE / "skills" / "orch-state" / "scripts" / "summary.py"
PHASE_SCRIPT = _BASE / "skills" / "orch-state" / "scripts" / "current_phase.py"
APPEND_SCRIPT = _BASE / "skills" / "orch-log" / "scripts" / "append.py"


def _run(script: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _append(cwd: Path, event_type: str, task_id: str | None = None,
            data: dict | None = None, attempt: int = 1) -> dict:
    extra: list[str] = []
    if task_id:
        extra += ["--task-id", task_id]
    if data:
        extra += ["--data", json.dumps(data)]
    if attempt != 1:
        extra += ["--attempt", str(attempt)]
    r = _run(APPEND_SCRIPT, ["--agent", "orch", "--event-type", event_type] + extra, cwd)
    assert r.returncode == 0, r.stderr + r.stdout
    return json.loads(r.stdout)


def _setup_empty(tmp_path: Path) -> None:
    (tmp_path / ".orch").mkdir(exist_ok=True)


def _setup_with_tasks(tmp_path: Path) -> None:
    _setup_empty(tmp_path)
    _append(tmp_path, "phase_declared",
            data={"workflow_id": "wf_test",
                  "phases": [{"name": "dev", "order": 1, "required": True},
                              {"name": "qa", "order": 2, "required": True}]})
    _append(tmp_path, "phase_entered", data={"phase": "dev", "order": 1})
    _append(tmp_path, "task_created", task_id="t_001",
            data={"phase": "dev", "tier": "standard", "type": "impl",
                  "spec": "do A", "deps": []})
    _append(tmp_path, "task_created", task_id="t_002",
            data={"phase": "dev", "tier": "standard", "type": "impl",
                  "spec": "do B", "deps": []})


# ---------------------------------------------------------------------------
# reduce.py
# ---------------------------------------------------------------------------

def test_reduce_empty_log_returns_empty_state(tmp_path):
    _setup_empty(tmp_path)
    r = _run(REDUCE_SCRIPT, [], tmp_path)
    assert r.returncode == 0, r.stderr
    state = json.loads(r.stdout)
    assert state["workflow_id"] is None
    assert state["tasks"] == {}
    assert state["phases"] == {}
    assert state["current_phase"] is None
    assert state["last_seq"] == 0


def test_reduce_after_workflow_returns_consistent_state(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(REDUCE_SCRIPT, [], tmp_path)
    assert r.returncode == 0, r.stderr
    state = json.loads(r.stdout)
    assert state["workflow_id"] == "wf_test"
    assert "t_001" in state["tasks"]
    assert "t_002" in state["tasks"]
    # tasks created after phase_entered with no deps are promoted to ready immediately
    assert state["tasks"]["t_001"]["status"] == "ready"
    assert state["current_phase"] == "dev"
    assert state["last_seq"] == 4


def test_reduce_output_has_required_top_level_keys(tmp_path):
    _setup_empty(tmp_path)
    r = _run(REDUCE_SCRIPT, [], tmp_path)
    state = json.loads(r.stdout)
    for key in ("workflow_id", "run_status", "current_phase", "tasks",
                "phases", "escalation", "circuit_breaker", "last_seq"):
        assert key in state, f"missing key: {key}"


def test_reduce_tasks_have_required_fields(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(REDUCE_SCRIPT, [], tmp_path)
    state = json.loads(r.stdout)
    task = state["tasks"]["t_001"]
    for key in ("task_id", "phase", "status", "tier", "task_type", "spec"):
        assert key in task, f"missing task field: {key}"


# ---------------------------------------------------------------------------
# summary.py
# ---------------------------------------------------------------------------

def test_summary_is_not_pure_json(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(SUMMARY_SCRIPT, [], tmp_path)
    assert r.returncode == 0, r.stderr
    # summary output should not be valid JSON (it's human-readable)
    try:
        json.loads(r.stdout)
        assert False, "summary.py should not emit pure JSON"
    except json.JSONDecodeError:
        pass


def test_summary_contains_workflow_id(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(SUMMARY_SCRIPT, [], tmp_path)
    assert "wf_test" in r.stdout


def test_summary_contains_phase(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(SUMMARY_SCRIPT, [], tmp_path)
    assert "dev" in r.stdout


def test_summary_contains_task_status(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(SUMMARY_SCRIPT, [], tmp_path)
    # tasks without deps created after phase_entered are promoted to ready
    assert "ready" in r.stdout


def test_summary_empty_log(tmp_path):
    _setup_empty(tmp_path)
    r = _run(SUMMARY_SCRIPT, [], tmp_path)
    assert r.returncode == 0
    assert "(none)" in r.stdout


# ---------------------------------------------------------------------------
# current_phase.py
# ---------------------------------------------------------------------------

def test_current_phase_no_phase_returns_null(tmp_path):
    _setup_empty(tmp_path)
    r = _run(PHASE_SCRIPT, [], tmp_path)
    assert r.returncode == 0, r.stderr
    result = json.loads(r.stdout)
    assert result["current_phase"] is None
    assert result["status"] is None


def test_current_phase_after_phase_entered(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(PHASE_SCRIPT, [], tmp_path)
    assert r.returncode == 0, r.stderr
    result = json.loads(r.stdout)
    assert result["current_phase"] == "dev"
    assert result["status"] is not None


def test_current_phase_output_has_order(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(PHASE_SCRIPT, [], tmp_path)
    result = json.loads(r.stdout)
    assert "order" in result
    assert result["order"] == 1


def test_current_phase_output_is_valid_json(tmp_path):
    _setup_with_tasks(tmp_path)
    r = _run(PHASE_SCRIPT, [], tmp_path)
    result = json.loads(r.stdout)
    assert isinstance(result, dict)
