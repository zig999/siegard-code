"""Layer Hard Review Session Guard — cross-workflow task-ID collision (QA suppression fix).

Review task IDs derive from the dev TC number (review_dev_tc_001) and the log
is shared across workflows, so a completed review task from an EARLIER workflow
satisfies the naive "skip if exists" check and silently suppresses QA for the
current one (eternal audit: seqs 155-160 vs 750-756 — E21). The fix is the
Step 3 session-linkage guard: existence alone never skips; the existing task's
spec must belong to .orch/sessions/<workflow_id>/, otherwise a namespaced ID
(review_<workflow_id>_{dev_task_id}) is used. The dev↔review link is the
explicit dev_task_id field in task_created data, never parsed from the ID.
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent
REVIEW = ROOT / "dist/.claude/agents/orchestrator-review.md"


def _src() -> str:
    return REVIEW.read_text(encoding="utf-8")


class TestSessionLinkageGuard:
    def test_skip_is_conditioned_on_session_linkage(self):
        src = _src()
        assert "Session-linkage guard" in src
        assert "do NOT skip on existence alone" in src
        assert ".orch/sessions/<workflow_id>/" in src

    def test_collision_falls_back_to_namespaced_id(self):
        src = _src()
        assert "review_<workflow_id>_{dev_task_id}" in src

    def test_stale_dev_tasks_are_skipped(self):
        """dev_completed_tasks comes from GLOBAL state — deliverables from an
        earlier workflow must not get review tasks in the current one."""
        src = _src()
        assert "belongs to an earlier workflow" in src

    def test_task_created_carries_explicit_dev_task_id(self):
        """The dev↔review correspondence must be a data field, not ID parsing —
        the namespaced fallback breaks prefix-stripping."""
        src = _src()
        assert '"dev_task_id":"<dev_task_id>"' in src

    def test_id_convention_documents_collision_variant(self):
        src = _src()
        convention = src.split("## Task ID convention")[1].split("\n## ")[0]
        assert "review_<workflow_id>_{dev_task_id}" in convention
