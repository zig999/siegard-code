"""Tests for atomic check-and-claim: orch_core.claim_task + orch-log/scripts/claim.py.

Regression for the eternal double-dispatch incident (log seqs 774-788): two
concurrent orchestrator-review instances both read the same READY batch and
each appended task_claimed for the same tasks. claim_task re-checks the task's
status INSIDE the append lock, so the second claimant gets a structured
refusal instead of writing a duplicate claim.
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import orch_core
from orch_core import (
    EventValidationError,
    TaskStatus,
    append_event,
    claim_task,
    reduce_all,
)

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "dist" / ".claude" / "skills" / "orch-log" / "scripts" / "claim.py"
)

_CLAIM_DATA = {"phase": "dev", "worker_type": "impl", "worker_id": "u-be-developer-dev_tc_001"}


def _seed_ready_task(task_id: str = "dev_tc_001") -> None:
    """phase_declared + phase_entered + task_created(deps=[]) → task is READY."""
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": "wf_claim", "phases": [{"name": "dev", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": "dev", "order": 1, "workflow_id": "wf_claim"})
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": [],
    })


# ---------------------------------------------------------------------------
# claim_task — library
# ---------------------------------------------------------------------------

class TestClaimTask:
    def test_claim_ready_task_appends_and_runs(self, tmp_orch):
        _seed_ready_task()
        event, reason = claim_task("orchestrator-dev", "dev_tc_001", data=dict(_CLAIM_DATA))
        assert reason is None
        assert event is not None
        assert event.event_type == "task_claimed"
        state = reduce_all()
        assert state.tasks["dev_tc_001"].status == TaskStatus.RUNNING
        assert state.tasks["dev_tc_001"].worker_id == _CLAIM_DATA["worker_id"]

    def test_second_claim_refused_no_duplicate_event(self, tmp_orch):
        """The loser of the race gets (None, reason) and the log stays clean."""
        _seed_ready_task()
        claim_task("orchestrator-dev", "dev_tc_001", data=dict(_CLAIM_DATA))
        event, reason = claim_task("orchestrator-dev", "dev_tc_001", data=dict(_CLAIM_DATA))
        assert event is None
        assert reason == "not_ready:running"
        claims = [e for e in orch_core.read_events() if e.event_type == "task_claimed"]
        assert len(claims) == 1
        # No anomaly either — the duplicate was refused at append, never logged.
        assert reduce_all().anomalies == []

    def test_claim_unknown_task_refused(self, tmp_orch):
        _seed_ready_task()
        event, reason = claim_task("orchestrator-dev", "dev_tc_999", data=dict(_CLAIM_DATA))
        assert event is None
        assert reason == "task_not_found"

    def test_claim_pending_task_refused(self, tmp_orch):
        """Task with unmet deps is PENDING → not claimable."""
        _seed_ready_task()
        append_event("orchestrator", "task_created", task_id="dev_tc_002", data={
            "phase": "dev", "tier": "standard", "type": "impl", "spec": "s",
            "deps": ["dev_tc_001"],
        })
        event, reason = claim_task("orchestrator-dev", "dev_tc_002", data=dict(_CLAIM_DATA))
        assert event is None
        assert reason == "not_ready:pending"

    def test_claim_validates_required_fields(self, tmp_orch):
        _seed_ready_task()
        with pytest.raises(EventValidationError):
            claim_task("orchestrator-dev", "dev_tc_001", data={"phase": "dev"})

    def test_concurrent_claims_exactly_one_winner(self, tmp_orch):
        """N threads race on the same READY task; the lock serializes them and
        exactly one claim lands."""
        _seed_ready_task()
        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(claim_task("orchestrator-dev", "dev_tc_001", data=dict(_CLAIM_DATA)))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        winners = [r for r in results if r[0] is not None]
        losers = [r for r in results if r[0] is None]
        assert len(winners) == 1
        assert len(losers) == 7
        assert all(reason == "not_ready:running" for _, reason in losers)
        claims = [e for e in orch_core.read_events() if e.event_type == "task_claimed"]
        assert len(claims) == 1


# ---------------------------------------------------------------------------
# claim.py — CLI (subprocess)
# ---------------------------------------------------------------------------

APPEND_SCRIPT = SCRIPT.parent / "append.py"


def _run(script: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    (cwd / ".orch").mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )


def _seed_ready_task_cli(cwd: Path) -> None:
    for event_type, task_id, data in [
        ("phase_declared", None, {"workflow_id": "wf_claim",
                                  "phases": [{"name": "dev", "order": 1, "required": True}]}),
        ("phase_entered", None, {"phase": "dev", "order": 1, "workflow_id": "wf_claim"}),
        ("task_created", "dev_tc_001", {"phase": "dev", "tier": "standard",
                                        "type": "impl", "spec": "s", "deps": []}),
    ]:
        args = ["--agent", "orchestrator", "--event-type", event_type, "--data", json.dumps(data)]
        if task_id:
            args += ["--task-id", task_id]
        r = _run(APPEND_SCRIPT, args, cwd)
        assert r.returncode == 0, r.stdout + r.stderr


class TestClaimCli:
    def test_claim_then_refusal(self, tmp_path):
        _seed_ready_task_cli(tmp_path)
        args = ["--agent", "orchestrator-dev", "--task-id", "dev_tc_001",
                "--data", json.dumps(_CLAIM_DATA)]

        first = _run(SCRIPT, args, tmp_path)
        assert first.returncode == 0, first.stdout + first.stderr
        out1 = json.loads(first.stdout)
        assert out1["claimed"] is True
        assert out1["event"]["event_type"] == "task_claimed"

        second = _run(SCRIPT, args, tmp_path)
        assert second.returncode == 0, second.stdout + second.stderr
        out2 = json.loads(second.stdout)
        assert out2 == {"claimed": False, "reason": "not_ready:running"}

    def test_task_not_found(self, tmp_path):
        _seed_ready_task_cli(tmp_path)
        r = _run(SCRIPT, ["--agent", "orchestrator-dev", "--task-id", "nope",
                          "--data", json.dumps(_CLAIM_DATA)], tmp_path)
        assert r.returncode == 0
        assert json.loads(r.stdout) == {"claimed": False, "reason": "task_not_found"}

    def test_invalid_json_exits_1(self, tmp_path):
        r = _run(SCRIPT, ["--agent", "o", "--task-id", "t", "--data", "{not json"], tmp_path)
        assert r.returncode == 1
        assert json.loads(r.stdout)["reason"] == "invalid_json"

    def test_missing_required_fields_exits_1(self, tmp_path):
        _seed_ready_task_cli(tmp_path)
        r = _run(SCRIPT, ["--agent", "orchestrator-dev", "--task-id", "dev_tc_001",
                          "--data", json.dumps({"phase": "dev"})], tmp_path)
        assert r.returncode == 1
        assert json.loads(r.stdout)["reason"] == "validation_error"
