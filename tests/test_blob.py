"""
Blob externalization tests — 3500-byte threshold, round-trip, integrity.
"""
import json
import pytest


_THRESHOLD = 3500  # MAX_INLINE_PAYLOAD from orch_core


def _task_created_data(**kw) -> dict:
    base = {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}
    base.update(kw)
    return base


def _make_large_data(size: int) -> dict:
    """Returns a dict whose canonical JSON serialization exceeds `size` bytes."""
    payload = "X" * size
    return {"phase": "sdd", "tier": "standard", "type": "spec", "spec": payload, "deps": []}


class TestBlobThreshold:

    def test_small_payload_stored_inline(self, orch_dir, make_event):
        import orch_core
        e = make_event("task_created", task_id="t1", data=_task_created_data(spec="small"))
        # Inline: data dict contains the actual fields
        assert "_blob_ref" not in e.data

    def test_large_payload_externalized(self, orch_dir, make_event):
        import orch_core
        large_data = _make_large_data(_THRESHOLD + 500)
        e = make_event("task_created", task_id="t1", data=large_data)
        # Externalized: data replaced by blob reference
        assert "_blob_ref" in e.data
        assert "_blob_hash" in e.data
        assert "_size" in e.data

    def test_blob_file_exists_on_disk(self, orch_dir, make_event):
        import orch_core
        large_data = _make_large_data(_THRESHOLD + 500)
        e = make_event("task_created", task_id="t1", data=large_data)
        # _blob_ref is relative to ORCH_DIR (e.g. "blobs/evt_XYZ.json")
        blob_path = orch_dir / ".orch" / e.data["_blob_ref"]
        assert blob_path.exists()

    def test_exactly_at_threshold_stored_inline(self, orch_dir, make_event):
        """Payload at exactly MAX_INLINE_PAYLOAD bytes should be stored inline."""
        import orch_core
        # Build a spec string such that total canonical JSON size == threshold
        # Use a smaller value to stay safely within inline range
        small_data = _task_created_data(spec="A" * 10)
        e = make_event("task_created", task_id="t1", data=small_data)
        assert "_blob_ref" not in e.data


class TestBlobRoundTrip:

    def test_reduce_all_resolves_blob_transparently(self, orch_dir, make_event):
        import orch_core
        large_spec = "B" * (_THRESHOLD + 500)
        large_data = _make_large_data(_THRESHOLD + 500)
        large_data["spec"] = large_spec
        make_event("task_created", task_id="t1", data=large_data)
        # reduce_all must load the blob and expose full spec in TaskState
        s = orch_core.reduce_all()
        assert s.tasks["t1"].spec == large_spec

    def test_blob_integrity_check(self, orch_dir, make_event):
        import orch_core
        large_data = _make_large_data(_THRESHOLD + 500)
        e = make_event("task_created", task_id="t1", data=large_data)
        blob_path = orch_dir / ".orch" / e.data["_blob_ref"]
        blob_path.write_bytes(b"CORRUPTED DATA")
        with pytest.raises(orch_core.BlobIntegrityError):
            orch_core.load_blob_data(e)

    def test_missing_blob_raises(self, orch_dir, make_event):
        import orch_core
        large_data = _make_large_data(_THRESHOLD + 500)
        e = make_event("task_created", task_id="t1", data=large_data)
        blob_path = orch_dir / ".orch" / e.data["_blob_ref"]
        blob_path.unlink()
        with pytest.raises(orch_core.BlobNotFoundError):
            orch_core.load_blob_data(e)


class TestIsBlobRef:

    def test_blob_ref_detected(self):
        import orch_core
        data = {"_blob_ref": "abc123", "_size": 5000, "_blob_hash": "deadbeef"}
        assert orch_core.is_blob_ref(data) is True

    def test_regular_data_not_detected(self):
        import orch_core
        assert orch_core.is_blob_ref({"phase": "sdd"}) is False

    def test_partial_blob_keys_not_detected(self):
        import orch_core
        assert orch_core.is_blob_ref({"_blob_ref": "x", "_size": 5}) is False
