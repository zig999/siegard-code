"""Tests for Task 4.4 — verify_and_recover and updated verify.py CLI.

Covers scenarios 9.1, 9.2, 9.3, 9.4.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).parents[1] / ".claude" / "lib"
SKILLS_DIR = Path(__file__).parents[1] / ".claude" / "skills"
VERIFY = str(SKILLS_DIR / "orch-log" / "scripts" / "verify.py")
APPEND = str(SKILLS_DIR / "orch-log" / "scripts" / "append.py")

sys.path.insert(0, str(LIB))

from orch_core import (
    ORCH_DIR,
    verify_chain,
    verify_and_recover,
    read_events,
    last_event,
    EventType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _append(cwd, agent, event_type, task_id=None, attempt=1, data=None):
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


def _build_log(cwd, n_events: int = 5) -> list[dict]:
    """Build a valid log with n_events phase_declared + task_created events."""
    evts = []
    evts.append(_append(cwd, "orchestrator", "phase_declared",
                        data={"workflow_id": "wf_test",
                              "phases": [{"name": "default", "order": 1, "required": True}]}))
    evts.append(_append(cwd, "orchestrator", "phase_entered",
                        data={"phase": "default", "order": 1}))
    for i in range(n_events - 2):
        evts.append(_append(cwd, "orchestrator", "task_created", f"t_{i+1:03d}",
                            data={"phase": "default", "deps": [], "tier": "standard",
                                  "type": "impl", "spec": f"task {i+1}"}))
    return evts


def _log_path(cwd) -> Path:
    return Path(cwd) / ".orch" / "log.jsonl"


def _corrupt_at_seq(cwd, seq: int) -> None:
    """Corrupt the raw JSON line for the given seq in-place."""
    log = _log_path(cwd)
    lines = log.read_bytes().splitlines(keepends=True)
    new_lines = []
    for line in lines:
        try:
            obj = json.loads(line)
            if obj.get("seq") == seq:
                # Replace with invalid JSON
                new_lines.append(b'{"seq":' + str(seq).encode() + b',"CORRUPTED":true}\n')
            else:
                new_lines.append(line)
        except json.JSONDecodeError:
            new_lines.append(line)
    log.write_bytes(b"".join(new_lines))


def _run_verify(cwd, *args):
    r = subprocess.run(
        [sys.executable, VERIFY] + list(args),
        cwd=str(cwd), capture_output=True, text=True
    )
    return r


# ---------------------------------------------------------------------------
# verify_and_recover — unit tests
# ---------------------------------------------------------------------------

class TestVerifyAndRecover:
    def test_confirm_false_raises(self, tmp_path):
        """Scenario 9.1: confirm=False must raise ValueError."""
        _build_log(tmp_path, 5)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with pytest.raises(ValueError, match="confirm=True"):
                verify_and_recover(from_seq=3, operator="ops@example.com", confirm=False)
        finally:
            os.chdir(old)

    def test_confirm_false_does_not_modify_log(self, tmp_path):
        """Log must not be modified when confirm=False."""
        _build_log(tmp_path, 5)
        log_before = _log_path(tmp_path).read_bytes()
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with pytest.raises(ValueError):
                verify_and_recover(from_seq=3, operator="ops", confirm=False)
        finally:
            os.chdir(old)
        assert _log_path(tmp_path).read_bytes() == log_before

    def test_from_seq_less_than_1_raises(self, tmp_path):
        _build_log(tmp_path, 3)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with pytest.raises(ValueError, match="from_seq"):
                verify_and_recover(from_seq=0, operator="ops", confirm=True)
        finally:
            os.chdir(old)

    def test_log_not_found_raises(self, tmp_path):
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with pytest.raises(FileNotFoundError):
                verify_and_recover(from_seq=3, operator="ops", confirm=True)
        finally:
            os.chdir(old)

    def test_recovery_truncates_log(self, tmp_path):
        """Scenario 9.2: events >= from_seq are removed from the log."""
        evts = _build_log(tmp_path, 7)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            verify_and_recover(from_seq=5, operator="ops@example.com", confirm=True)
            remaining = list(read_events())
        finally:
            os.chdir(old)

        seqs = [e.seq for e in remaining]
        # seqs 1-4 preserved, seq 5 is log_recovered
        assert 1 in seqs
        assert 4 in seqs
        # original seqs 5,6,7 removed
        assert 5 not in [e.seq for e in remaining if e.event_type != EventType.LOG_RECOVERED.value]
        assert 6 not in seqs
        assert 7 not in seqs

    def test_recovery_emits_log_recovered_event(self, tmp_path):
        """log_recovered event is appended after truncation."""
        _build_log(tmp_path, 5)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            verify_and_recover(from_seq=4, operator="ops@example.com", confirm=True)
            events = list(read_events())
        finally:
            os.chdir(old)

        last = events[-1]
        assert last.event_type == EventType.LOG_RECOVERED.value
        assert last.data["seq_truncated_from"] == 4
        assert last.data["operator"] == "ops@example.com"
        assert last.data["events_removed"] >= 1

    def test_corrupt_file_created(self, tmp_path):
        """Scenario 9.2: removed events are archived in .orch/log.jsonl.corrupt.*"""
        _build_log(tmp_path, 6)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            evt = verify_and_recover(from_seq=4, operator="ops", confirm=True)
        finally:
            os.chdir(old)

        corrupt_path = Path(tmp_path) / ".orch" / Path(evt.data["corrupt_file_path"]).name
        assert corrupt_path.exists()
        # Corrupt file must contain the removed lines
        content = corrupt_path.read_bytes()
        assert len(content) > 0

    def test_corrupt_file_path_in_event_data(self, tmp_path):
        """corrupt_file_path in log_recovered matches the pattern .orch/log.jsonl.corrupt.*"""
        _build_log(tmp_path, 4)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            evt = verify_and_recover(from_seq=3, operator="ops", confirm=True)
        finally:
            os.chdir(old)

        assert evt.data["corrupt_file_path"].startswith(".orch/log.jsonl.corrupt.")

    def test_after_recovery_verify_strict_passes(self, tmp_path):
        """Scenario 9.2: after recovery, verify_chain(strict) returns ok=True."""
        _build_log(tmp_path, 8)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            verify_and_recover(from_seq=5, operator="ops", confirm=True)
            result = verify_chain(mode="strict")
        finally:
            os.chdir(old)

        assert result.ok is True

    def test_recovery_hash_chain_intact_after_recovery(self, tmp_path):
        """Hash chain is valid after recovery (log_recovered chains correctly)."""
        _build_log(tmp_path, 6)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            verify_and_recover(from_seq=4, operator="ops", confirm=True)
            result = verify_chain(mode="strict")
        finally:
            os.chdir(old)

        assert result.ok is True

    def test_recovery_returns_event_with_correct_seq(self, tmp_path):
        """Returned event has seq = from_seq (first seq after the kept events)."""
        _build_log(tmp_path, 6)
        import os
        old = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            evt = verify_and_recover(from_seq=4, operator="ops", confirm=True)
        finally:
            os.chdir(old)

        # events 1-3 kept, log_recovered appended as seq 4
        assert evt.seq == 4


# ---------------------------------------------------------------------------
# verify.py CLI — recovery mode
# ---------------------------------------------------------------------------

class TestVerifyCLIRecovery:
    def test_recover_without_confirm_exits_2(self, tmp_path):
        _build_log(tmp_path, 5)
        r = _run_verify(tmp_path, "--recover", "--from-seq", "3", "--operator", "ops")
        assert r.returncode == 2

    def test_recover_without_from_seq_exits_2(self, tmp_path):
        _build_log(tmp_path, 5)
        r = _run_verify(tmp_path, "--recover", "--confirm", "--operator", "ops")
        assert r.returncode == 2

    def test_recover_without_operator_exits_2(self, tmp_path):
        _build_log(tmp_path, 5)
        r = _run_verify(tmp_path, "--recover", "--confirm", "--from-seq", "3")
        assert r.returncode == 2

    def test_recover_success(self, tmp_path):
        _build_log(tmp_path, 6)
        r = _run_verify(tmp_path, "--recover", "--confirm",
                        "--from-seq", "4", "--operator", "ops@example.com")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["ok"] is True
        assert out["recovered"] is True
        assert out["seq_truncated_from"] == 4
        assert out["operator"] == "ops@example.com"

    def test_recover_creates_corrupt_file(self, tmp_path):
        _build_log(tmp_path, 6)
        r = _run_verify(tmp_path, "--recover", "--confirm",
                        "--from-seq", "4", "--operator", "ops")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        corrupt_path = tmp_path / ".orch" / Path(out["corrupt_file_path"]).name
        assert corrupt_path.exists()

    def test_recover_then_verify_strict_passes(self, tmp_path):
        _build_log(tmp_path, 7)
        _run_verify(tmp_path, "--recover", "--confirm",
                    "--from-seq", "5", "--operator", "ops")
        r = _run_verify(tmp_path, "--mode", "strict")
        out = json.loads(r.stdout)
        assert out["ok"] is True

    def test_normal_verify_mode_unchanged(self, tmp_path):
        """--mode strict/audit still works after adding recovery flags."""
        _build_log(tmp_path, 4)
        r = _run_verify(tmp_path, "--mode", "strict")
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["ok"] is True
        assert out["events_verified"] == 4
