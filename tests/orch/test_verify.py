"""
Tests for Task 1.5: verify_chain (strict and audit modes).
Covers scenarios: 2.1, 2.2, 2.3, 2.4
"""
import json

import pytest
import orch_core
from orch_core import append_event, verify_chain, VerifyResult


def _task(i: int) -> dict:
    return {"phase": "dev", "tier": "standard", "type": "impl",
            "spec": f"task {i}", "deps": []}


def _seed(tmp_orch, n: int) -> list:
    return [append_event("orchestrator", "task_created",
                         task_id=f"t_{i:04d}", data=_task(i))
            for i in range(1, n + 1)]


def _corrupt_line(path, line_index: int, replacement: bytes = b"CORRUPTED\n") -> None:
    """Replaces a line in the log with invalid content."""
    lines = path.read_bytes().splitlines(keepends=True)
    lines[line_index] = replacement
    path.write_bytes(b"".join(lines))


def _tamper_data(path, line_index: int, new_data: dict) -> None:
    """Modifies the `data` field of an event but keeps the original hash intact."""
    lines = path.read_bytes().splitlines(keepends=True)
    d = json.loads(lines[line_index])
    d["data"] = new_data      # change data, leave hash unchanged → mismatch
    lines[line_index] = (json.dumps(d, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(b"".join(lines))


# ---------------------------------------------------------------------------
# Scenario 2.1: verify_chain passes on intact log
# ---------------------------------------------------------------------------

class TestVerifyIntactLog:
    def test_empty_log_ok(self, tmp_orch):
        result = verify_chain()
        assert result.ok is True
        assert result.events_verified == 0

    def test_single_event_ok(self, tmp_orch):
        _seed(tmp_orch, 1)
        result = verify_chain()
        assert result.ok is True
        assert result.events_verified == 1

    def test_ten_events_ok(self, tmp_orch):
        """Scenario 2.1: intact log of 10 events."""
        _seed(tmp_orch, 10)
        result = verify_chain()
        assert result.ok is True
        assert result.events_verified == 10
        assert result.first_error_seq is None

    def test_result_carries_mode(self, tmp_orch):
        _seed(tmp_orch, 3)
        result = verify_chain(mode="strict")
        assert result.mode == "strict"

    def test_no_file_ok(self, tmp_orch):
        assert not orch_core.LOG_PATH.exists()
        result = verify_chain()
        assert result.ok is True


# ---------------------------------------------------------------------------
# Scenario 2.2: verify_chain detects tampered data
# ---------------------------------------------------------------------------

class TestVerifyTamperedData:
    def test_detects_hash_mismatch(self, tmp_orch):
        """Scenario 2.2: edit data of seq=3, keep original hash → mismatch."""
        _seed(tmp_orch, 5)
        _tamper_data(orch_core.LOG_PATH, 2,
                     {"phase": "dev", "tier": "standard", "type": "TAMPERED",
                      "spec": "evil", "deps": []})

        result = verify_chain(mode="strict")
        assert result.ok is False
        assert result.first_error_seq == 3

    def test_strict_stops_at_first_error(self, tmp_orch):
        """Strict mode must stop at first error, not scan the whole log."""
        _seed(tmp_orch, 5)
        # Tamper lines 2 and 4 (seq 3 and 5)
        _tamper_data(orch_core.LOG_PATH, 2,
                     {"phase": "dev", "tier": "standard", "type": "BAD1",
                      "spec": "x", "deps": []})
        _tamper_data(orch_core.LOG_PATH, 4,
                     {"phase": "dev", "tier": "standard", "type": "BAD2",
                      "spec": "y", "deps": []})

        result = verify_chain(mode="strict")
        assert result.ok is False
        assert result.first_error_seq == 3
        assert len(result.error_details) == 1  # stopped at first

    def test_message_mentions_seq(self, tmp_orch):
        _seed(tmp_orch, 3)
        _tamper_data(orch_core.LOG_PATH, 1,
                     {"phase": "dev", "tier": "standard", "type": "BAD",
                      "spec": "x", "deps": []})
        result = verify_chain(mode="strict")
        assert "seq=2" in result.message

    def test_events_verified_count_stops_before_error(self, tmp_orch):
        _seed(tmp_orch, 5)
        _tamper_data(orch_core.LOG_PATH, 2,
                     {"phase": "dev", "tier": "standard", "type": "BAD",
                      "spec": "x", "deps": []})
        result = verify_chain(mode="strict")
        assert result.events_verified == 2  # verified 2 before hitting seq=3


# ---------------------------------------------------------------------------
# Scenario 2.3: verify_chain detects reordering
# ---------------------------------------------------------------------------

class TestVerifyReordering:
    def test_detects_swapped_lines(self, tmp_orch):
        """Scenario 2.3: swap lines 2 and 3 → prev_hash mismatch at seq=2."""
        _seed(tmp_orch, 5)
        lines = orch_core.LOG_PATH.read_bytes().splitlines(keepends=True)
        lines[1], lines[2] = lines[2], lines[1]
        orch_core.LOG_PATH.write_bytes(b"".join(lines))

        result = verify_chain(mode="strict")
        assert result.ok is False
        # After swap, the event now at position 1 has wrong prev_hash
        assert result.first_error_seq is not None

    def test_detects_chain_break(self, tmp_orch):
        _seed(tmp_orch, 4)
        lines = orch_core.LOG_PATH.read_bytes().splitlines(keepends=True)
        # Move last event to position 1 → chain breaks at line 1
        lines = [lines[-1]] + lines[:-1]
        orch_core.LOG_PATH.write_bytes(b"".join(lines))

        result = verify_chain(mode="strict")
        assert result.ok is False


# ---------------------------------------------------------------------------
# Scenario 2.4: audit mode reports all errors
# ---------------------------------------------------------------------------

class TestVerifyAuditMode:
    def test_audit_finds_multiple_errors(self, tmp_orch):
        """Scenario 2.4: two tampered events → two errors in audit mode."""
        _seed(tmp_orch, 7)
        _tamper_data(orch_core.LOG_PATH, 2,
                     {"phase": "dev", "tier": "standard", "type": "BAD1",
                      "spec": "x", "deps": []})
        _tamper_data(orch_core.LOG_PATH, 5,
                     {"phase": "dev", "tier": "standard", "type": "BAD2",
                      "spec": "y", "deps": []})

        result = verify_chain(mode="audit")
        assert result.ok is False
        # audit reports all errors (at minimum 2, chain errors may cascade)
        assert len(result.error_details) >= 2

    def test_audit_does_not_modify_log(self, tmp_orch):
        """Scenario 2.4: log is unchanged after audit."""
        _seed(tmp_orch, 5)
        _tamper_data(orch_core.LOG_PATH, 2,
                     {"phase": "dev", "tier": "standard", "type": "BAD",
                      "spec": "x", "deps": []})

        content_before = orch_core.LOG_PATH.read_bytes()
        verify_chain(mode="audit")
        content_after = orch_core.LOG_PATH.read_bytes()
        assert content_before == content_after

    def test_audit_returns_all_error_seqs(self, tmp_orch):
        _seed(tmp_orch, 5)
        _tamper_data(orch_core.LOG_PATH, 1,
                     {"phase": "dev", "tier": "standard", "type": "B1",
                      "spec": "x", "deps": []})
        _tamper_data(orch_core.LOG_PATH, 3,
                     {"phase": "dev", "tier": "standard", "type": "B2",
                      "spec": "y", "deps": []})

        result = verify_chain(mode="audit")
        error_seqs = [e["seq"] for e in result.error_details]
        assert 2 in error_seqs

    def test_audit_ok_on_intact_log(self, tmp_orch):
        _seed(tmp_orch, 5)
        result = verify_chain(mode="audit")
        assert result.ok is True
        assert result.events_verified == 5

    def test_audit_mode_field(self, tmp_orch):
        _seed(tmp_orch, 3)
        result = verify_chain(mode="audit")
        assert result.mode == "audit"


# ---------------------------------------------------------------------------
# log_path override
# ---------------------------------------------------------------------------

class TestVerifyLogPathOverride:
    def test_override_path(self, tmp_orch):
        """verify_chain with explicit log_path works independently of module paths.

        Uses tmp_orch (not bare tmp_path): ensure_dirs/append_event below touch
        ALL path globals — with pristine relative paths they would create a
        stray .orch/ in the repo root (cwd) as a side effect.
        """
        alt_path = tmp_orch / "alt_log.jsonl"

        # Write a single valid event directly
        import orch_core as oc
        orig = oc.LOG_PATH
        try:
            oc.LOG_PATH = alt_path
            oc.ensure_dirs()
            append_event("orchestrator", "task_created",
                         task_id="t_0001", data=_task(1))
        finally:
            oc.LOG_PATH = orig

        result = verify_chain(log_path=alt_path)
        assert result.ok is True
        assert result.events_verified == 1

    def test_strict_does_not_modify_log(self, tmp_orch):
        _seed(tmp_orch, 3)
        content = orch_core.LOG_PATH.read_bytes()
        verify_chain(mode="strict")
        assert orch_core.LOG_PATH.read_bytes() == content


# ---------------------------------------------------------------------------
# B3 — physically corrupted JSON line in the middle is detected
# ---------------------------------------------------------------------------

class TestVerifyCorruptJSON:
    def test_strict_detects_corrupt_json_middle(self, tmp_orch):
        """B3: invalid JSON in middle of log → verify_chain ok=False (strict)."""
        _seed(tmp_orch, 5)
        _corrupt_line(orch_core.LOG_PATH, 2)  # line index 2 = seq 3

        result = verify_chain(mode="strict")
        assert result.ok is False

    def test_audit_detects_corrupt_json_middle(self, tmp_orch):
        """B3: invalid JSON in middle of log → verify_chain ok=False (audit)."""
        _seed(tmp_orch, 5)
        _corrupt_line(orch_core.LOG_PATH, 2)

        result = verify_chain(mode="audit")
        assert result.ok is False
        assert len(result.error_details) >= 1

    def test_corrupt_last_line_still_ok(self, tmp_orch):
        """Truncated last line is tolerated — not a corruption error."""
        _seed(tmp_orch, 3)
        _corrupt_line(orch_core.LOG_PATH, 2)  # last line

        result = verify_chain(mode="strict")
        assert result.ok is True
        assert result.events_verified == 2

    def test_error_detail_type_is_parse_error(self, tmp_orch):
        """B3: error_details entry has type='parse_error' for corrupt JSON."""
        _seed(tmp_orch, 4)
        _corrupt_line(orch_core.LOG_PATH, 1)  # middle line

        result = verify_chain(mode="audit")
        types = [e["type"] for e in result.error_details]
        assert "parse_error" in types
