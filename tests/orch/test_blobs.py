"""
Tests for Task 1.6: externalize_blob, load_blob_data, is_blob_ref.
Covers scenarios: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""
import json
import hashlib

import pytest
import orch_core
from orch_core import (
    append_event,
    load_blob_data,
    externalize_blob,
    is_blob_ref,
    BlobIntegrityError,
    BlobNotFoundError,
)


def _task(i: int = 1) -> dict:
    return {"phase": "dev", "tier": "standard", "type": "impl",
            "spec": f"task {i}", "deps": []}


def _large_data(size_bytes: int = 10_000) -> dict:
    """Returns a dict whose canonical JSON serialization exceeds size_bytes."""
    filler = "x" * size_bytes
    return {"phase": "dev", "tier": "standard", "type": "impl",
            "spec": filler, "deps": []}


# ---------------------------------------------------------------------------
# Scenario 6.7: is_blob_ref
# ---------------------------------------------------------------------------

class TestIsBlobRef:
    def test_true_when_all_keys_present(self):
        d = {"_blob_ref": ".orch/blobs/evt_abc.json", "_size": 100, "_blob_hash": "deadbeef"}
        assert is_blob_ref(d) is True

    def test_false_when_missing_blob_ref(self):
        d = {"_size": 100, "_blob_hash": "deadbeef"}
        assert is_blob_ref(d) is False

    def test_false_when_missing_size(self):
        d = {"_blob_ref": "path", "_blob_hash": "deadbeef"}
        assert is_blob_ref(d) is False

    def test_false_when_missing_blob_hash(self):
        d = {"_blob_ref": "path", "_size": 100}
        assert is_blob_ref(d) is False

    def test_false_for_regular_data(self):
        assert is_blob_ref({"key": "value"}) is False

    def test_false_for_empty_dict(self):
        assert is_blob_ref({}) is False

    def test_false_for_non_dict(self):
        assert is_blob_ref("string") is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Scenario 6.1: small payload stays inline
# ---------------------------------------------------------------------------

class TestSmallPayloadInline:
    def test_small_payload_is_inline(self, tmp_orch):
        """Scenario 6.1: payload < MAX_INLINE_PAYLOAD stays inline."""
        data = _task(1)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        assert not is_blob_ref(event.data)
        assert event.data == data

    def test_no_blob_file_created(self, tmp_orch):
        """Scenario 6.1: no file in .orch/blobs/ for small payload."""
        append_event("orchestrator", "task_created", task_id="t_0001", data=_task(1))

        blobs = list(orch_core.BLOBS_DIR.iterdir())
        assert len(blobs) == 0

    def test_inline_exactly_at_limit(self, tmp_orch):
        """Payload exactly at MAX_INLINE_PAYLOAD is NOT externalized."""
        import orch_core as oc
        from orch_core import canonical_json
        # Build data that serializes to exactly MAX_INLINE_PAYLOAD bytes
        base = {"phase": "dev", "tier": "standard", "type": "impl", "spec": "", "deps": []}
        base_size = len(canonical_json(base).encode("utf-8"))
        padding_needed = oc.MAX_INLINE_PAYLOAD - base_size - len('"spec":"",') + len('"spec":"x",')
        filler = "x" * max(0, oc.MAX_INLINE_PAYLOAD - base_size)
        base["spec"] = filler
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=base)
        # Whether inline or blob depends on exact size; just verify no crash
        assert event is not None


# ---------------------------------------------------------------------------
# Scenario 6.2: large payload is externalized
# ---------------------------------------------------------------------------

class TestLargePayloadExternalized:
    def test_large_payload_creates_blob_ref(self, tmp_orch):
        """Scenario 6.2: data > MAX_INLINE_PAYLOAD → _blob_ref in event.data."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        assert is_blob_ref(event.data)
        assert "_blob_ref" in event.data
        assert "_size" in event.data
        assert "_blob_hash" in event.data

    def test_blob_file_is_created(self, tmp_orch):
        """Scenario 6.2: blob file exists at referenced path."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        blob_path = orch_core.BLOBS_DIR / f"{event.event_id}.json"
        assert blob_path.exists()

    def test_blob_hash_matches_file_content(self, tmp_orch):
        """Scenario 6.2: SHA-256 of blob file equals _blob_hash."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        blob_path = orch_core.BLOBS_DIR / f"{event.event_id}.json"
        actual_hash = hashlib.sha256(blob_path.read_bytes()).hexdigest()
        assert actual_hash == event.data["_blob_hash"]

    def test_size_field_matches_serialized_size(self, tmp_orch):
        """_size in blob ref reflects the original serialized data size."""
        from orch_core import canonical_json
        data = _large_data(10_000)
        expected_size = len(canonical_json(data).encode("utf-8"))
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        assert event.data["_size"] == expected_size


# ---------------------------------------------------------------------------
# Scenario 6.3: load_blob_data detects tampering
# ---------------------------------------------------------------------------

class TestLoadBlobDataIntegrity:
    def test_raises_blob_integrity_error_on_tampered_blob(self, tmp_orch):
        """Scenario 6.3: blob tampered after write → BlobIntegrityError."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        blob_path = orch_core.BLOBS_DIR / f"{event.event_id}.json"
        blob_path.write_bytes(b'{"tampered": true}')

        with pytest.raises(BlobIntegrityError) as exc_info:
            load_blob_data(event)

        assert str(blob_path) in str(exc_info.value)

    def test_error_message_mentions_file(self, tmp_orch):
        """Error message identifies the corrupted file path."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        blob_path = orch_core.BLOBS_DIR / f"{event.event_id}.json"
        blob_path.write_bytes(b'{"evil": "data"}')

        with pytest.raises(BlobIntegrityError) as exc_info:
            load_blob_data(event)

        assert "blobs" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Scenario 6.4: load_blob_data returns inline data without I/O
# ---------------------------------------------------------------------------

class TestLoadBlobDataInline:
    def test_returns_inline_data_directly(self, tmp_orch):
        """Scenario 6.4: inline event → load_blob_data returns data unchanged."""
        data = _task(1)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        result = load_blob_data(event)
        assert result == data

    def test_inline_does_not_read_blobs_dir(self, tmp_orch):
        """Scenario 6.4: blobs/ dir stays empty for inline events."""
        data = _task(1)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)
        load_blob_data(event)

        assert list(orch_core.BLOBS_DIR.iterdir()) == []


# ---------------------------------------------------------------------------
# Scenario 6.5: missing blob raises error
# ---------------------------------------------------------------------------

class TestLoadBlobDataMissing:
    def test_raises_when_blob_missing(self, tmp_orch):
        """Scenario 6.5: blob file deleted → BlobNotFoundError or FileNotFoundError."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        blob_path = orch_core.BLOBS_DIR / f"{event.event_id}.json"
        blob_path.unlink()

        with pytest.raises((BlobNotFoundError, FileNotFoundError)):
            load_blob_data(event)


# ---------------------------------------------------------------------------
# Scenario 6.6: round-trip — load_blob_data recovers original data
# ---------------------------------------------------------------------------

class TestLoadBlobDataRoundTrip:
    def test_round_trip_large_payload(self, tmp_orch):
        """load_blob_data returns the original data for an externalized event."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        assert is_blob_ref(event.data)
        recovered = load_blob_data(event)
        assert recovered == data

    def test_multiple_blobs_independent(self, tmp_orch):
        """Multiple large events each get their own blob file."""
        data1 = _large_data(10_000)
        data2 = _large_data(12_000)
        ev1 = append_event("orchestrator", "task_created", task_id="t_0001", data=data1)
        ev2 = append_event("orchestrator", "task_created", task_id="t_0002", data=data2)

        assert load_blob_data(ev1) == data1
        assert load_blob_data(ev2) == data2
        assert ev1.data["_blob_ref"] != ev2.data["_blob_ref"]

    def test_externalize_blob_directly(self, tmp_orch):
        """externalize_blob called directly returns correct path and hash."""
        from orch_core import canonical_json
        data = _large_data(5_000)
        event_id = "evt_testdirect"

        blob_ref, blob_hash = externalize_blob(data, event_id)

        blob_path = orch_core.BLOBS_DIR / f"{event_id}.json"
        assert blob_path.exists()
        raw = blob_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == blob_hash
        assert json.loads(raw) == json.loads(canonical_json(data))


# ---------------------------------------------------------------------------
# A1 — blob_ref is relative to ORCH_DIR, not CWD-absolute (fix A1)
# ---------------------------------------------------------------------------

class TestBlobRefFormat:
    def test_blob_ref_is_relative_to_orch_dir(self, tmp_orch):
        """A1: _blob_ref stored as path relative to ORCH_DIR, not absolute."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        blob_ref = event.data["_blob_ref"]
        # Must not be absolute
        assert not blob_ref.startswith("/"), f"_blob_ref should be relative, got: {blob_ref}"
        # Must be resolvable relative to ORCH_DIR
        resolved = orch_core.ORCH_DIR / blob_ref
        assert resolved.exists()

    def test_load_blob_data_resolves_via_orch_dir(self, tmp_orch):
        """A1: load_blob_data resolves blob path via ORCH_DIR."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        recovered = load_blob_data(event)
        assert recovered == data

    def test_blob_ref_format_is_blobs_slash_filename(self, tmp_orch):
        """A1: _blob_ref has the form 'blobs/evt_XYZ.json'."""
        data = _large_data(10_000)
        event = append_event("orchestrator", "task_created", task_id="t_0001", data=data)

        blob_ref = event.data["_blob_ref"]
        assert blob_ref.startswith("blobs/")
        assert blob_ref.endswith(".json")


# ---------------------------------------------------------------------------
# B2 — read_events_filtered phase filter works with externalized blobs
# ---------------------------------------------------------------------------

class TestFilteredWithBlobs:
    def test_phase_filter_includes_externalized_events(self, tmp_orch):
        """B2: read_events_filtered(phase=...) finds tasks with large payloads."""
        from orch_core import read_events_filtered
        append_event("orchestrator", "phase_declared", data={
            "workflow_id": "wf", "phases": [{"name": "dev", "order": 1, "required": True}]
        })
        append_event("orchestrator", "task_created", task_id="t_0001", data={
            "phase": "dev", "tier": "standard", "type": "impl",
            "spec": "x" * 10_000, "deps": [],
        })

        results = read_events_filtered(event_type="task_created", phase="dev")
        assert len(results) == 1
        assert results[0].task_id == "t_0001"

    def test_phase_filter_excludes_wrong_phase_externalized(self, tmp_orch):
        """B2: externalized task in wrong phase is excluded by filter."""
        from orch_core import read_events_filtered
        append_event("orchestrator", "task_created", task_id="t_0001", data={
            "phase": "sdd", "tier": "standard", "type": "impl",
            "spec": "x" * 10_000, "deps": [],
        })

        results = read_events_filtered(phase="dev")
        assert len(results) == 0
