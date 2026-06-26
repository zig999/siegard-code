"""
Log integrity tests — SHA-256 hash chain invariants (P1, P3, P5).
"""


def _task_created_data() -> dict:
    return {"phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []}


class TestHashChain:

    def test_first_event_prev_hash_is_genesis(self, orch_dir, make_event):
        import orch_core
        e = make_event("task_created", task_id="t1", data=_task_created_data())
        assert e.prev_hash == "GENESIS"

    def test_second_event_prev_hash_matches_first_hash(self, orch_dir, make_event):
        import orch_core
        e1 = make_event("task_created", task_id="t1", data=_task_created_data())
        e2 = make_event("task_created", task_id="t2", data=_task_created_data())
        assert e2.prev_hash == e1.hash

    def test_hash_is_deterministic(self, orch_dir, make_event):
        import orch_core
        e = make_event("task_created", task_id="t1", data=_task_created_data())
        assert e.hash == e.compute_hash()

    def test_seq_increments(self, orch_dir, make_event):
        import orch_core
        e1 = make_event("task_created", task_id="t1", data=_task_created_data())
        e2 = make_event("task_created", task_id="t2", data=_task_created_data())
        e3 = make_event("task_created", task_id="t3", data=_task_created_data())
        assert e1.seq == 1
        assert e2.seq == 2
        assert e3.seq == 3
