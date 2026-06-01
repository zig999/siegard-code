"""Layer Hard Dispatch Audit — dispatch_decision shape validation (task 12, Option B).

A1-F3: dispatch_decision was emitted by orchestrators but its payload was neither
shape-validated nor uniform (dev used batch_members/constraints; sdd/review used
batch/constraints). Option B (user-chosen): validate the structure at append
({phase, batch, rationale, constraints}) and uniformize the dev payload. The
ordering hard-enforcement (task_claimed must follow a dispatch_decision) is a
deferred follow-up — a hard precondition would break ~20 test files.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))


class TestDispatchDecisionSchema:
    def test_requires_fields(self, orch_dir, make_event):
        import orch_core
        try:
            make_event("dispatch_decision", data={"phase": "dev"})
            assert False, "expected EventValidationError"
        except orch_core.EventValidationError as exc:
            assert any(k in str(exc) for k in ("batch", "rationale", "constraints"))

    def test_valid_appends(self, orch_dir, make_event):
        ev = make_event("dispatch_decision", data={
            "phase": "dev", "batch": ["t1"], "rationale": "ready-queue top-2",
            "constraints": {"max_batch": 2}})
        assert ev.event_type == "dispatch_decision"

    def test_dispatch_decision_has_required_fields_entry(self):
        from orch_core import EventType, _REQUIRED_DATA_FIELDS
        req = _REQUIRED_DATA_FIELDS.get(EventType.DISPATCH_DECISION.value)
        assert req == {"phase", "batch", "rationale", "constraints"}

    def test_dev_orchestrator_emits_batch_key(self):
        # the dev dispatch_decision payload must use `batch` (not batch_members),
        # so its runtime emission satisfies the new required fields.
        src = (ROOT / "dist/.claude/agents/orchestrator-dev.md").read_text(encoding="utf-8")
        assert '"batch_members"' not in src, "dev dispatch_decision must not use batch_members"
        dd_lines = [l for l in src.splitlines() if '"rationale"' in l and '"phase":"dev"' in l]
        assert dd_lines and all('"batch"' in l for l in dd_lines), "dev dispatch_decision must use 'batch'"
