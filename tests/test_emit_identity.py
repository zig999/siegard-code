"""B2 (v2.34.0) — emit.py identity must be backed by the worker registry.

The env-var identity model is spoofable by construction: any session that can
`export ORCH_WORKER_ID` chooses its identity (the downstream flow-discipline
incident class). The orchestrator registers every worker BEFORE spawning (I5),
so a legitimate identity always has a matching registry entry.

Two hard violations (exit 1, reason identity_mismatch):
  - entry for worker_id binds a different (task_id, attempt)
  - (task_id, attempt) is registered to a different worker_id

Missing entry on both sides is a WARNING (stderr), not an error: the
reverse-spec pipeline dispatches workers without registry entries; hard-failing
would break it. The deterministic boundary is flow_guard + notarization
(Pacote A) — this check only removes the cheap impersonation paths.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()

import orch_core  # noqa: E402  (lib on sys.path via conftest)

_EMIT_PATH = dist / "skills" / "orch-report" / "scripts" / "emit.py"
_spec = importlib.util.spec_from_file_location("emit_identity_under_test", _EMIT_PATH)
emit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(emit)


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
    # emit.py binds WORKERS_DIR at import time — repoint its copy too.
    monkeypatch.setattr(emit, "WORKERS_DIR", base / "workers")
    orch_core.ensure_dirs()


def _run_emit(monkeypatch, capsys, worker_id, task_id, attempt=1, kind="progress"):
    monkeypatch.setenv("ORCH_WORKER_ID", worker_id)
    monkeypatch.setattr(sys, "argv", [
        "emit.py", "--kind", kind, "--task-id", task_id, "--attempt", str(attempt),
        "--data", json.dumps({"phase": "sdd", "note": "context_loaded"}),
    ])
    rc = emit.main()
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


class TestIdentityMismatch:
    def test_entry_binding_other_task_is_rejected(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        orch_core.register_worker("u-spec-writer-t1", "t1", 1, phase="sdd")
        rc, out, _ = _run_emit(monkeypatch, capsys, "u-spec-writer-t1", "t2")
        assert rc == 1
        result = json.loads(out.strip())
        assert result["status"] == "error"
        assert result["reason"] == "identity_mismatch"

    def test_entry_binding_other_attempt_is_rejected(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        orch_core.register_worker("u-spec-writer-t1", "t1", 2, phase="sdd")
        rc, out, _ = _run_emit(monkeypatch, capsys, "u-spec-writer-t1", "t1", attempt=1)
        assert rc == 1
        assert json.loads(out.strip())["reason"] == "identity_mismatch"

    def test_task_claimed_by_other_worker_is_rejected(self, tmp_path, monkeypatch, capsys):
        """Impersonation path: the caller exports an arbitrary ID and targets a
        task registered to someone else."""
        _isolate_orch(tmp_path, monkeypatch)
        orch_core.register_worker("u-spec-writer-t1", "t1", 1, phase="sdd")
        rc, out, _ = _run_emit(monkeypatch, capsys, "u-imposter", "t1")
        assert rc == 1
        result = json.loads(out.strip())
        assert result["reason"] == "identity_mismatch"
        assert "u-spec-writer-t1" in result["detail"]


class TestUnregisteredTier:
    def test_unregistered_worker_warns_but_emits(self, tmp_path, monkeypatch, capsys):
        """Off-registry pipelines (reverse-spec) must keep working: warning on
        stderr, event still appended."""
        _isolate_orch(tmp_path, monkeypatch)
        rc, out, err = _run_emit(monkeypatch, capsys, "u-reverse-spec-analyzer-x", "rs_t1")
        assert rc == 0
        warning = json.loads(err.strip())
        assert warning["reason"] == "unregistered_worker"
        event = json.loads(out.strip())
        assert event["event_type"] == "task_progress"

    def test_registered_match_is_silent(self, tmp_path, monkeypatch, capsys):
        _isolate_orch(tmp_path, monkeypatch)
        orch_core.register_worker("u-spec-writer-t1", "t1", 1, phase="sdd")
        rc, out, err = _run_emit(monkeypatch, capsys, "u-spec-writer-t1", "t1")
        assert rc == 0
        assert err.strip() == ""
        assert json.loads(out.strip())["event_type"] == "task_progress"


class TestFailOpen:
    def test_corrupt_registry_entry_does_not_block(self, tmp_path, monkeypatch, capsys):
        """An unreadable registry is not evidence of forgery — fail-open."""
        _isolate_orch(tmp_path, monkeypatch)
        (tmp_path / ".orch" / "workers").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".orch" / "workers" / "u-spec-writer-t1.json").write_text(
            "{not json", encoding="utf-8"
        )
        rc, out, _ = _run_emit(monkeypatch, capsys, "u-spec-writer-t1", "t1")
        assert rc == 0
        assert json.loads(out.strip())["event_type"] == "task_progress"
