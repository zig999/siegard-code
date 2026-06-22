"""
SIEGARD-07 — respond_escalation.py: append a human_response to resolve an escalation.

Runs the helper as a subprocess against a log seeded in-process. Uses tmp_orch
(no-reload isolation per the tests/orch/ convention); the subprocess reads the
same log via ORCH_PROJECT_DIR.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import orch_core

SCRIPT = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "scripts" / "respond_escalation.py"


def _emit(event_type, task_id=None, data=None):
    return orch_core.append_event(
        agent="orch", event_type=event_type, task_id=task_id, data=data or {}
    )


def _run(project_dir, *args):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir)}
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", *args],
        capture_output=True, text=True, env=env,
    )
    out = (p.stdout or p.stderr).strip()
    return json.loads(out), p.returncode


def _seed_escalation():
    _emit("phase_declared", data={"workflow_id": "w", "phases": [{"name": "review", "order": 1, "required": True}]})
    _emit("phase_entered", data={"phase": "review", "order": 1, "workflow_id": "w"})
    return _emit("escalation", data={
        "code": "E99_human_approval_required", "severity": "info",
        "reason": "awaiting approval", "evidence": [],
    })


def test_responds_to_active_escalation(tmp_orch):
    esc = _seed_escalation()

    out, rc = _run(tmp_orch, "--action", "approve", "--operator", "alice")
    assert rc == 0, out
    assert out["escalation_seq"] == esc.seq
    assert out["escalation_code"] == "E99_human_approval_required"
    assert out["action"] == "approve"

    # The escalation is now resolved in the derived state.
    assert orch_core.reduce_all().escalation is None


def test_no_active_escalation_errors(tmp_orch):
    _emit("phase_declared", data={"workflow_id": "w", "phases": [{"name": "dev", "order": 1, "required": True}]})
    out, rc = _run(tmp_orch, "--action", "approve")
    assert rc == 1 and out["reason"] == "no_active_escalation"


def test_targets_explicit_escalation_seq(tmp_orch):
    esc = _seed_escalation()
    out, rc = _run(tmp_orch, "--escalation-seq", str(esc.seq), "--action", "return_to_dev")
    assert rc == 0
    assert out["escalation_seq"] == esc.seq
    assert orch_core.reduce_all().escalation is None
