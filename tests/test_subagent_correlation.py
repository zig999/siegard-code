"""Exact SubagentStop correlation (v2.35.0) — B3 experiment productized.

Validated empirically (2026-07-28, CLI 2.1.220): the SubagentStop payload
carries agent_transcript_path — the stopped subagent's own JSONL, which
contains the spawn prompt with the literal `ORCH_WORKER_ID=<id>` line. The
hook now correlates the stop to ONE registered worker:

  correlated + no terminal  -> synthesize task_failed IMMEDIATELY (no liveness
                               wait) — collapses the audited 20-30 min dead
                               windows to seconds
  correlated + terminal     -> registry cleanup only
  other workers             -> untouched by this stop (liveness gate applies)
  no payload / no fields /
  no match / unreadable     -> the pre-2.35 liveness-gated fallback, unchanged
                               (F-03 / SIEGARD BUG-1 guarantees intact)

The rejected route is pinned too: session_id (env and payload) carries the
PARENT's id and must never be used for correlation.
"""
import io
import json
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
_HOOKS = dist / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import orch_core  # noqa: E402
import on_subagent_stop as sas  # noqa: E402


def _isolate_orch(tmp_path, monkeypatch):
    base = tmp_path / ".orch"
    paths = {
        "ORCH_DIR": base, "LOG_PATH": base / "log.jsonl",
        "LOCK_PATH": base / "log.jsonl.lock", "STATE_DIR": base / "state",
        "DLQ_DIR": base / "dlq", "AUDIT_DIR": base / "audit",
        "METRICS_DIR": base / "metrics", "BLOBS_DIR": base / "blobs",
        "WORKERS_DIR": base / "workers", "CONFIG_PATH": base / "config.json",
    }
    for name, val in paths.items():
        monkeypatch.setattr(orch_core, name, val)
    orch_core.ensure_dirs()


def _seed_running_worker(worker_id="u-spec-writer-t1", task_id="t1"):
    """Full legitimate lifecycle up to RUNNING with recent activity."""
    orch_core.append_event(
        agent="orchestrator", event_type="phase_declared",
        data={"workflow_id": "wf", "phases": [{"name": "sdd", "order": 1}]},
    )
    orch_core.append_event(
        agent="orchestrator", event_type="phase_entered",
        data={"phase": "sdd", "order": 1, "workflow_id": "wf"},
    )
    orch_core.append_event(
        agent="orchestrator-sdd", event_type="task_created", task_id=task_id, attempt=1,
        data={"phase": "sdd", "tier": "standard", "type": "spec-writer",
              "spec": "x", "deps": []},
    )
    orch_core.append_event(
        agent="orchestrator-sdd", event_type="task_claimed", task_id=task_id, attempt=1,
        data={"phase": "sdd", "worker_type": "u-spec-writer", "worker_id": worker_id},
    )
    orch_core.register_worker(worker_id, task_id, 1, phase="sdd")


def _write_transcript(tmp_path, worker_id) -> Path:
    """Mimics the real subagent transcript: JSONL whose first user record holds
    the spawn prompt, ORCH_WORKER_ID included (validated against a live one)."""
    t = tmp_path / "agent-abc123.jsonl"
    prompt = (
        "Execute your spec pipeline task.\nEnvironment context:\n"
        f"  ORCH_TASK_ID=t1\n  ORCH_ATTEMPT=1\n  ORCH_WORKER_ID={worker_id}\n"
    )
    t.write_text(json.dumps({"type": "user", "message": prompt}) + "\n", encoding="utf-8")
    return t


def _run_hook(monkeypatch, payload: dict | str):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    return sas.main()


def _failed_events(tmp_path):
    lines = (tmp_path / ".orch" / "log.jsonl").read_text().strip().splitlines()
    return [json.loads(l) for l in lines if json.loads(l)["event_type"] == "task_failed"]


class TestCorrelatedStop:
    def test_correlated_worker_fails_immediately(self, tmp_path, monkeypatch):
        """The upgrade: recent activity would block synthesis pre-2.35; exact
        correlation proves the exit, so the terminal lands NOW."""
        _isolate_orch(tmp_path, monkeypatch)
        _seed_running_worker()
        transcript = _write_transcript(tmp_path, "u-spec-writer-t1")
        rc = _run_hook(monkeypatch, {
            "agent_id": "abc123", "agent_type": "u-spec-writer",
            "agent_transcript_path": str(transcript),
            "session_id": "parent-session",
        })
        assert rc == 0
        failed = _failed_events(tmp_path)
        assert len(failed) == 1
        data = failed[0]["data"]
        assert data["reason"] == "worker_exited_without_terminal"
        assert data["correlated"] is True
        assert data["agent_type"] == "u-spec-writer"

    def test_correlated_with_terminal_only_cleans_registry(self, tmp_path, monkeypatch):
        _isolate_orch(tmp_path, monkeypatch)
        _seed_running_worker()
        orch_core.append_event(
            agent="u-spec-writer-t1", event_type="task_completed",
            task_id="t1", attempt=1,
            data={"phase": "sdd", "artifacts": []},
        )
        transcript = _write_transcript(tmp_path, "u-spec-writer-t1")
        _run_hook(monkeypatch, {"agent_transcript_path": str(transcript)})
        assert _failed_events(tmp_path) == []
        assert not (tmp_path / ".orch" / "workers" / "u-spec-writer-t1.json").exists()

    def test_sibling_workers_are_untouched(self, tmp_path, monkeypatch):
        """The stop is exact evidence about ONE worker — a live sibling with
        recent activity must not be reaped (F-03 preserved under correlation)."""
        _isolate_orch(tmp_path, monkeypatch)
        _seed_running_worker("u-spec-writer-t1", "t1")
        # sibling, also running, recent activity
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="task_created", task_id="t2", attempt=1,
            data={"phase": "sdd", "tier": "standard", "type": "spec-back",
                  "spec": "y", "deps": []},
        )
        orch_core.append_event(
            agent="orchestrator-sdd", event_type="task_claimed", task_id="t2", attempt=1,
            data={"phase": "sdd", "worker_type": "u-spec-back", "worker_id": "u-spec-back-t2"},
        )
        orch_core.register_worker("u-spec-back-t2", "t2", 1, phase="sdd")
        transcript = _write_transcript(tmp_path, "u-spec-writer-t1")
        _run_hook(monkeypatch, {"agent_transcript_path": str(transcript)})
        failed = _failed_events(tmp_path)
        assert len(failed) == 1
        assert failed[0]["task_id"] == "t1"  # sibling t2 untouched


class TestUncorrelatedFallback:
    @pytest.mark.parametrize("payload", [
        "{}",                                        # empty payload
        "not json at all {{{",                       # malformed stdin
        json.dumps({"session_id": "parent-only"}),   # pre-2.35 CLI shape
    ])
    def test_recent_worker_survives_uncorrelated_stop(self, tmp_path, monkeypatch, payload):
        """SIEGARD BUG-1 regression: without correlation, a worker with recent
        activity must NOT be synthesized on an unrelated stop."""
        _isolate_orch(tmp_path, monkeypatch)
        _seed_running_worker()
        rc = _run_hook(monkeypatch, payload)
        assert rc == 0
        assert _failed_events(tmp_path) == []

    def test_transcript_without_marker_falls_back(self, tmp_path, monkeypatch):
        _isolate_orch(tmp_path, monkeypatch)
        _seed_running_worker()
        t = tmp_path / "agent-aux.jsonl"
        t.write_text(json.dumps({"type": "user", "message": "auxiliary task"}) + "\n",
                     encoding="utf-8")
        _run_hook(monkeypatch, {"agent_transcript_path": str(t)})
        assert _failed_events(tmp_path) == []

    def test_unreadable_transcript_falls_back(self, tmp_path, monkeypatch):
        _isolate_orch(tmp_path, monkeypatch)
        _seed_running_worker()
        _run_hook(monkeypatch, {"agent_transcript_path": str(tmp_path / "gone.jsonl")})
        assert _failed_events(tmp_path) == []


class TestCorrelationUnit:
    def test_extracts_worker_id(self, tmp_path):
        t = _write_transcript(tmp_path, "u-be-developer-dev_wf_task-3")
        assert sas._correlate_worker_id(
            {"agent_transcript_path": str(t)}
        ) == "u-be-developer-dev_wf_task-3"

    def test_no_path_returns_none(self):
        assert sas._correlate_worker_id({}) is None
        assert sas._correlate_worker_id({"session_id": "x"}) is None

    def test_session_id_is_never_used(self):
        """Pin the rejected route: session_id alone must correlate nothing."""
        assert sas._correlate_worker_id({"session_id": "u-spec-writer-t1"}) is None
