"""Tests for orch-log/scripts/read.py and verify.py CLIs (subprocess)."""
import json
import subprocess
import sys
from pathlib import Path

READ_SCRIPT = (
    Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "read.py"
)
VERIFY_SCRIPT = (
    Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "verify.py"
)
APPEND_SCRIPT = (
    Path(__file__).parent.parent.parent / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "append.py"
)


def _run(script: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _append(cwd: Path, event_type: str, task_id: str | None = None, data: dict | None = None) -> dict:
    extra = []
    if task_id:
        extra += ["--task-id", task_id]
    if data:
        extra += ["--data", json.dumps(data)]
    r = _run(APPEND_SCRIPT, ["--agent", "orch", "--event-type", event_type] + extra, cwd)
    assert r.returncode == 0, r.stderr + r.stdout
    return json.loads(r.stdout)


def _setup_log(tmp_path: Path) -> list[dict]:
    (tmp_path / ".orch").mkdir(exist_ok=True)
    events = []
    events.append(_append(tmp_path, "phase_declared",
                           data={"workflow_id": "wf_1", "phases": [{"name": "dev", "order": 1}]}))
    events.append(_append(tmp_path, "phase_entered",
                           data={"phase": "dev", "order": 1, "workflow_id": "wf-fix"}))
    events.append(_append(tmp_path, "task_created", task_id="t_001",
                           data={"phase": "dev", "tier": "standard",
                                 "type": "impl", "spec": "do A", "deps": []}))
    events.append(_append(tmp_path, "task_created", task_id="t_002",
                           data={"phase": "dev", "tier": "standard",
                                 "type": "impl", "spec": "do B", "deps": []}))
    return events


# ---------------------------------------------------------------------------
# read.py — basic
# ---------------------------------------------------------------------------

def test_read_no_args_returns_all(tmp_path):
    events = _setup_log(tmp_path)
    r = _run(READ_SCRIPT, [], tmp_path)
    assert r.returncode == 0
    lines = [json.loads(l) for l in r.stdout.strip().splitlines()]
    assert len(lines) == len(events)


def test_read_empty_log_returns_nothing(tmp_path):
    (tmp_path / ".orch").mkdir()
    r = _run(READ_SCRIPT, [], tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_read_from_seq(tmp_path):
    events = _setup_log(tmp_path)
    r = _run(READ_SCRIPT, ["--from-seq", "3"], tmp_path)
    assert r.returncode == 0
    lines = [json.loads(l) for l in r.stdout.strip().splitlines()]
    assert all(e["seq"] >= 3 for e in lines)
    assert len(lines) == len([e for e in events if e["seq"] >= 3])


def test_read_tail(tmp_path):
    _setup_log(tmp_path)
    r = _run(READ_SCRIPT, ["--tail", "2"], tmp_path)
    assert r.returncode == 0
    lines = [json.loads(l) for l in r.stdout.strip().splitlines()]
    assert len(lines) == 2
    assert lines[-1]["seq"] == 4


def test_read_filter_task_id(tmp_path):
    _setup_log(tmp_path)
    r = _run(READ_SCRIPT, ["--task-id", "t_001"], tmp_path)
    assert r.returncode == 0
    lines = [json.loads(l) for l in r.stdout.strip().splitlines()]
    assert len(lines) == 1
    assert lines[0]["task_id"] == "t_001"


def test_read_filter_event_type(tmp_path):
    _setup_log(tmp_path)
    r = _run(READ_SCRIPT, ["--event-type", "task_created"], tmp_path)
    assert r.returncode == 0
    lines = [json.loads(l) for l in r.stdout.strip().splitlines()]
    assert len(lines) == 2
    assert all(e["event_type"] == "task_created" for e in lines)


def test_read_filter_phase(tmp_path):
    _setup_log(tmp_path)
    r = _run(READ_SCRIPT, ["--phase", "dev"], tmp_path)
    assert r.returncode == 0
    lines = [json.loads(l) for l in r.stdout.strip().splitlines()]
    # phase_entered + task_created × 2
    assert len(lines) == 3


def test_read_multiple_filters_are_AND(tmp_path):
    _setup_log(tmp_path)
    r = _run(READ_SCRIPT, ["--event-type", "task_created", "--task-id", "t_002"], tmp_path)
    assert r.returncode == 0
    lines = [json.loads(l) for l in r.stdout.strip().splitlines()]
    assert len(lines) == 1
    assert lines[0]["task_id"] == "t_002"


def test_read_each_line_is_valid_json(tmp_path):
    _setup_log(tmp_path)
    r = _run(READ_SCRIPT, [], tmp_path)
    assert r.returncode == 0
    for line in r.stdout.strip().splitlines():
        obj = json.loads(line)
        assert "seq" in obj and "event_type" in obj


# ---------------------------------------------------------------------------
# verify.py — strict mode
# ---------------------------------------------------------------------------

def test_verify_strict_intact_log_exit_0(tmp_path):
    _setup_log(tmp_path)
    r = _run(VERIFY_SCRIPT, ["--mode", "strict"], tmp_path)
    assert r.returncode == 0
    result = json.loads(r.stdout)
    assert result["ok"] is True
    assert result["events_verified"] == 4


def test_verify_strict_empty_log_exit_0(tmp_path):
    (tmp_path / ".orch").mkdir()
    r = _run(VERIFY_SCRIPT, [], tmp_path)
    assert r.returncode == 0
    result = json.loads(r.stdout)
    assert result["ok"] is True


def test_verify_strict_corrupt_log_exit_nonzero(tmp_path):
    _setup_log(tmp_path)
    log = tmp_path / ".orch" / "log.jsonl"
    lines = log.read_text().splitlines()
    # Tamper the second event's data field
    second = json.loads(lines[1])
    second["data"]["phase"] = "TAMPERED"
    lines[1] = json.dumps(second)
    log.write_text("\n".join(lines) + "\n")

    r = _run(VERIFY_SCRIPT, ["--mode", "strict"], tmp_path)
    assert r.returncode != 0
    result = json.loads(r.stdout)
    assert result["ok"] is False
    assert "first_error_seq" in result


# ---------------------------------------------------------------------------
# verify.py — audit mode
# ---------------------------------------------------------------------------

def test_verify_audit_intact_log_exit_0(tmp_path):
    _setup_log(tmp_path)
    r = _run(VERIFY_SCRIPT, ["--mode", "audit"], tmp_path)
    assert r.returncode == 0
    result = json.loads(r.stdout)
    assert result["ok"] is True
    assert result["mode"] == "audit"


def test_verify_audit_corrupt_log_still_exit_0(tmp_path):
    _setup_log(tmp_path)
    log = tmp_path / ".orch" / "log.jsonl"
    lines = log.read_text().splitlines()
    second = json.loads(lines[1])
    second["data"]["phase"] = "TAMPERED"
    lines[1] = json.dumps(second)
    log.write_text("\n".join(lines) + "\n")

    r = _run(VERIFY_SCRIPT, ["--mode", "audit"], tmp_path)
    assert r.returncode == 0  # audit always exits 0
    result = json.loads(r.stdout)
    assert result["ok"] is False
    assert len(result.get("error_details", [])) >= 1


def test_verify_audit_does_not_modify_log(tmp_path):
    _setup_log(tmp_path)
    log = tmp_path / ".orch" / "log.jsonl"
    content_before = log.read_bytes()
    _run(VERIFY_SCRIPT, ["--mode", "audit"], tmp_path)
    assert log.read_bytes() == content_before


