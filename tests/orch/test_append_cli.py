"""Tests for orch-log/scripts/append.py CLI (subprocess)."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "append.py"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    (cwd / ".orch").mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------

def test_append_task_created_success(tmp_path):
    data = json.dumps({
        "phase": "dev",
        "tier": "standard",
        "type": "impl",
        "spec": "implement X",
        "deps": [],
    })
    result = _run(
        ["--agent", "orchestrator", "--event-type", "task_created",
         "--task-id", "t_001", "--data", data],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    event = json.loads(result.stdout)
    assert event["event_type"] == "task_created"
    assert event["agent"] == "orchestrator"
    assert event["task_id"] == "t_001"
    assert event["seq"] == 1
    assert event["hash"] != ""


_PHASE_DECLARED_DATA = '{"workflow_id":"wf_1","phases":[{"name":"dev","order":1}]}'


def test_append_phase_declared_no_task_id(tmp_path):
    result = _run(
        ["--agent", "orchestrator", "--event-type", "phase_declared",
         "--data", _PHASE_DECLARED_DATA],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    event = json.loads(result.stdout)
    assert event["event_type"] == "phase_declared"
    assert event["task_id"] is None


def test_append_default_attempt(tmp_path):
    result = _run(
        ["--agent", "orchestrator", "--event-type", "phase_declared",
         "--data", '{"workflow_id":"wf_2","phases":[{"name":"dev","order":1}]}'],
        tmp_path,
    )
    assert result.returncode == 0
    event = json.loads(result.stdout)
    assert event["attempt"] == 1


def test_append_explicit_attempt(tmp_path):
    (tmp_path / ".orch").mkdir(exist_ok=True)
    _run(
        ["--agent", "orchestrator", "--event-type", "phase_declared",
         "--data", '{"workflow_id":"wf_3","phases":[{"name":"dev","order":1}]}'],
        tmp_path,
    )
    result = _run(
        ["--agent", "orchestrator", "--event-type", "task_created",
         "--task-id", "t_002", "--attempt", "2",
         "--data", '{"phase":"dev","tier":"standard","type":"impl","spec":"y","deps":[]}'],
        tmp_path,
    )
    assert result.returncode == 0
    event = json.loads(result.stdout)
    assert event["attempt"] == 2


def test_append_hash_chain(tmp_path):
    (tmp_path / ".orch").mkdir(exist_ok=True)
    r1 = _run(
        ["--agent", "orchestrator", "--event-type", "phase_declared",
         "--data", '{"workflow_id":"wf_4","phases":[{"name":"dev","order":1}]}'],
        tmp_path,
    )
    r2 = _run(
        ["--agent", "orchestrator", "--event-type", "task_created",
         "--task-id", "t_003",
         "--data", '{"phase":"dev","tier":"standard","type":"impl","spec":"z","deps":[]}'],
        tmp_path,
    )
    e1 = json.loads(r1.stdout)
    e2 = json.loads(r2.stdout)
    assert e2["prev_hash"] == e1["hash"]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_append_unknown_event_type_exits_nonzero(tmp_path):
    result = _run(
        ["--agent", "orchestrator", "--event-type", "not_a_real_event"],
        tmp_path,
    )
    assert result.returncode != 0
    err = json.loads(result.stdout)
    assert err["status"] == "error"
    assert err["reason"] == "unknown_event_type"


def test_append_invalid_json_data_exits_nonzero(tmp_path):
    result = _run(
        ["--agent", "orchestrator", "--event-type", "workflow_started",
         "--data", "{not-valid-json}"],
        tmp_path,
    )
    assert result.returncode != 0
    err = json.loads(result.stdout)
    assert err["status"] == "error"
    assert err["reason"] == "invalid_json"


def test_append_data_not_object_exits_nonzero(tmp_path):
    result = _run(
        ["--agent", "orchestrator", "--event-type", "workflow_started",
         "--data", '"just a string"'],
        tmp_path,
    )
    assert result.returncode != 0
    err = json.loads(result.stdout)
    assert err["status"] == "error"
    assert err["reason"] == "invalid_json"
