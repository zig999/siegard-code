"""Layer Hard Receipt — handoff_receipt is a logged EventType (task 08).

A3-F5: receipts lived only in session/spec side-files (no EventType, no reducer),
so the Spec->Dev loop-closure / orphan-delivery audit was unenforceable. Now
handoff_receipt is a first-class log event with required fields, and consumed/
orphan state is derived from the log (P1/P12) — same pattern as spec_pipeline_return.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dist" / ".claude" / "lib"))


class TestHandoffReceiptEvent:
    def test_receipt_is_event_type(self):
        import orch_core
        assert "handoff_receipt" in orch_core.EventType.values()

    def test_receipt_requires_fields(self, orch_dir, make_event):
        import orch_core
        try:
            make_event("handoff_receipt", data={})
            assert False, "expected EventValidationError"
        except orch_core.EventValidationError as exc:
            msg = str(exc)
            assert "manifest_id" in msg or "manifest_sha256" in msg or "consumed_by" in msg

    def test_valid_receipt_appends(self, orch_dir, make_event):
        ev = make_event("handoff_receipt", data={
            "manifest_id": "HANDOFF-1", "manifest_sha256": "a" * 64, "consumed_by": "u-be-orchestrator"})
        assert ev.event_type == "handoff_receipt"

    def test_consumed_manifest_ids_derived_from_log(self, orch_dir, make_event):
        import orch_core
        make_event("handoff_receipt", data={
            "manifest_id": "HANDOFF-1", "manifest_sha256": "a" * 64, "consumed_by": "u-be-orchestrator"})
        make_event("handoff_receipt", data={
            "manifest_id": "HANDOFF-2", "manifest_sha256": "b" * 64, "consumed_by": "u-fe-orchestrator"})
        consumed = orch_core.consumed_manifest_ids(list(orch_core.read_events()))
        assert consumed == {"HANDOFF-1", "HANDOFF-2"}

    def test_receipt_is_audit_marker_not_state_mutation(self, orch_dir, make_event):
        # The reducer treats it as an audit marker (no state effect) but advances last_seq.
        import orch_core
        make_event("phase_declared", data={"workflow_id": "w", "phases": [{"name": "dev", "order": 2, "required": True}]})
        ev = make_event("handoff_receipt", data={
            "manifest_id": "HANDOFF-1", "manifest_sha256": "a" * 64, "consumed_by": "u-be-orchestrator"})
        st = orch_core.reduce_all()
        assert st.last_seq == ev.seq          # last_seq advanced
        # no spurious task/phase created by the receipt
        assert "HANDOFF-1" not in st.tasks
