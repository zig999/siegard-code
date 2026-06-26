"""
Rec #11 (lighter) — check_acceptance_criteria_covered.py (dev exit).

Independent gate over each completed dev task's delivery-gate acceptance_criteria
block: blocks when uncovered is non-empty, covered < total, or the block is absent.
"""
import orch_core  # noqa: F401
from orch_core import append_event

from .conftest import SKILLS_DIR, phase_env, run_check  # noqa: F401

SCRIPT = SKILLS_DIR / "phase-dev-rules" / "scripts" / "check_acceptance_criteria_covered.py"

_COVERED = "acceptance_criteria:\n  total: 2\n  covered: 2\n  uncovered: []\n"
_UNCOVERED = "acceptance_criteria:\n  total: 2\n  covered: 1\n  uncovered:\n    - the missing criterion\n"
_MISMATCH = "acceptance_criteria:\n  total: 3\n  covered: 2\n  uncovered: []\n"
_NO_BLOCK = ""


def _dev_phase():
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": "wf_ac_test",
        "phases": [{"name": "dev", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf_ac_test"})


def _completed_with_gate(task_id, project_dir, ac_yaml):
    delivery_dir = project_dir / ".orch" / "sessions" / "wf_ac_test" / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)
    path = delivery_dir / f"{task_id}-delivery.md"
    path.write_text(
        "```yaml\n# delivery-gate\n"
        f"task: {task_id}\nstatus: implemented\n"
        f"{ac_yaml}"
        "qa_ready: true\n```\n\n# Delivery\n"
    )
    rel = str(path.relative_to(project_dir))
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": [],
    })
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "dev", "worker_type": "impl", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "dev", "artifacts": [rel], "summary": "done",
    })
    return rel


def test_all_covered_is_met(phase_env):
    _dev_phase()
    _completed_with_gate("dev_tc_1", phase_env, _COVERED)
    out = run_check(SCRIPT, phase_env)
    assert out["status"] == "ok" and out["met"] is True
    assert out["evidence"]["fully_covered"] == 1


def test_uncovered_blocks(phase_env):
    _dev_phase()
    _completed_with_gate("dev_tc_1", phase_env, _UNCOVERED)
    out = run_check(SCRIPT, phase_env)
    assert out["status"] == "blocked"
    assert out["evidence"]["violations"][0]["reason"] == "uncovered_criteria_present"


def test_covered_less_than_total_blocks(phase_env):
    _dev_phase()
    _completed_with_gate("dev_tc_1", phase_env, _MISMATCH)
    out = run_check(SCRIPT, phase_env)
    assert out["status"] == "blocked"
    assert out["evidence"]["violations"][0]["reason"] == "covered_less_than_total"


def test_missing_block_blocks(phase_env):
    _dev_phase()
    _completed_with_gate("dev_tc_1", phase_env, _NO_BLOCK)
    out = run_check(SCRIPT, phase_env)
    assert out["status"] == "blocked"
    assert out["evidence"]["violations"][0]["reason"] == "ac_block_missing"


def test_no_dev_deliveries_is_met(phase_env):
    _dev_phase()
    out = run_check(SCRIPT, phase_env)
    assert out["status"] == "ok" and out["evidence"]["total"] == 0
