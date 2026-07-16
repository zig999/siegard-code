"""detect_mode.py — new / resume / completed (2026-07-15 post-fix audit, 1.6).

"sdd in state.phases" alone meant mode=resume forever after the first workflow,
including after it completed — a second /u-spec on a used project could never
start (the meta re-printed the old completion report; only manual log cleanup
unblocked it, and nothing said so). A terminal workflow must be reported as its
own mode so the entry point directs the operator to purge before re-declaring.
"""
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "skills" / "orch-state" / "scripts"

_spec = importlib.util.spec_from_file_location("detect_mode", SCRIPTS / "detect_mode.py")
detect_mode = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(detect_mode)

_WF = "wf-dm"


def _seed_sdd_workflow(orch_core, phases):
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": _WF, "phases": phases})
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": "sdd", "order": 1, "workflow_id": _WF})


def _complete_phase(orch_core, name, next_phase):
    orch_core.append_event(
        agent=f"orchestrator-{name}", event_type="phase_exit_approved",
        data={"phase": name, "criteria_met": ["c"], "next_phase": next_phase,
              "workflow_id": _WF})
    seq = orch_core.reduce_all().last_seq
    orch_core.append_event(
        agent=f"orchestrator-{name}", event_type="phase_transitioned",
        data={"from_phase": name, "to_phase": next_phase, "evidence_seq": seq,
              "workflow_id": _WF})


def _mode(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(detect_mode, "LOG_PATH", tmp_path / ".orch" / "log.jsonl")
    assert detect_mode.main() == 0
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_unfinished_sdd_workflow_is_resume(tmp_orch, monkeypatch, capsys):
    import orch_core
    _seed_sdd_workflow(orch_core, [{"name": "sdd", "order": 1, "required": True}])
    out = _mode(monkeypatch, tmp_orch, capsys)
    assert out["mode"] == "resume"
    assert out["workflow_id"] == _WF


def test_completed_workflow_is_completed_not_resume(tmp_orch, monkeypatch, capsys):
    import orch_core
    _seed_sdd_workflow(orch_core, [{"name": "sdd", "order": 1, "required": True}])
    _complete_phase(orch_core, "sdd", "done")
    out = _mode(monkeypatch, tmp_orch, capsys)
    assert out["mode"] == "completed"
    assert out["workflow_id"] == _WF


def test_multiphase_with_pending_required_phase_is_resume(tmp_orch, monkeypatch, capsys):
    import orch_core
    _seed_sdd_workflow(orch_core, [
        {"name": "sdd", "order": 1, "required": True},
        {"name": "dev", "order": 2, "required": True}])
    _complete_phase(orch_core, "sdd", "dev")
    out = _mode(monkeypatch, tmp_orch, capsys)
    assert out["mode"] == "resume"


def test_missing_log_is_new(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(detect_mode, "LOG_PATH", tmp_path / "nope" / "log.jsonl")
    assert detect_mode.main() == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["mode"] == "new"
