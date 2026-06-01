"""Layer Hard Foundation — append-time precondition machinery.

Task 00 of the prod-hardening plan (extras/prod-hardening/tasks/00-foundation.md).
Red phase: the new-API tests must fail before the green phase implements them.

Behavior-neutral by design: with an empty precondition registry, append_event
must behave exactly as before (the full suite stays green).
"""
import sys
from pathlib import Path

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestPreconditionMachinery:
    def test_precondition_violation_is_orcherror(self):
        from orch_core import OrchError, PreconditionViolation

        assert issubclass(PreconditionViolation, OrchError)

    def test_empty_registry_is_noop(self, orch_dir, make_event):
        # With no registered precondition, append_event behaves exactly as before.
        ev = make_event(
            "phase_declared",
            data={
                "workflow_id": "w1",
                "phases": [{"name": "sdd", "order": 1, "required": True}],
            },
        )
        assert ev.seq == 1

    def test_registered_precondition_blocks_append(self, orch_dir, make_event):
        import orch_core

        orch_core.register_precondition(
            "task_progress", lambda data, events: "blocked_for_test"
        )
        try:
            make_event("task_progress", task_id="x", data={"phase": "sdd", "note": "n"})
            assert False, "expected PreconditionViolation"
        except orch_core.PreconditionViolation as exc:
            assert "blocked_for_test" in str(exc)
        finally:
            orch_core.clear_preconditions("task_progress")

    def test_precondition_runs_under_lock_sees_prior_events(self, orch_dir, make_event):
        # The precondition receives the events already in the log (consistency).
        import orch_core

        make_event(
            "phase_declared",
            data={
                "workflow_id": "w",
                "phases": [{"name": "sdd", "order": 1, "required": True}],
            },
        )
        seen = {}

        def _record(data, events):
            seen["count"] = len(events)
            return None  # allow

        orch_core.register_precondition("phase_entered", _record)
        try:
            make_event(
                "phase_entered",
                data={"phase": "sdd", "order": 1, "workflow_id": "w"},
            )
            assert seen["count"] == 1  # saw the prior phase_declared
        finally:
            orch_core.clear_preconditions("phase_entered")

    def test_read_helpers(self, orch_dir, make_event):
        import orch_core

        make_event(
            "phase_declared",
            data={
                "workflow_id": "w",
                "phases": [{"name": "review", "order": 3, "required": True}],
            },
        )
        events = list(orch_core.read_events())
        hit = orch_core.last_event_where(
            events, lambda e: e.event_type == "phase_declared"
        )
        assert hit is not None and hit.event_type == "phase_declared"
        miss = orch_core.last_event_where(
            events, lambda e: e.event_type == "human_response"
        )
        assert miss is None
        assert orch_core.any_event_where(
            events, lambda e: e.event_type == "phase_declared"
        ) is True
        assert orch_core.any_event_where(
            events, lambda e: e.event_type == "human_response"
        ) is False
