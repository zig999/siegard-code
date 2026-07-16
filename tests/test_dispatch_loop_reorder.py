"""Recommendation #4, 2026-07-15 workflow audit (A1 — "busy-spin backoff + lost
retry"), applied identically across all four phase orchestrators.

The "Stop conditions" bullet list (esp. "No tasks with status=ready -> proceed to
next Step") used to appear BEFORE the mutations (DLQ cascade, stale reaping,
retry re-queue) that could turn a due SCHEDULED task into READY. An LLM following
the prompt top-to-bottom evaluated the stale, pre-mutation state and bailed to the
exit-criteria step without ever promoting the due retry — which then bounced back
("non-terminal tasks remain -> return to Step 5") until the 30-iteration safety
cap fired a spurious error, even though the underlying retry mechanism was healthy
and just needed the mutation to run first.

Fixed by moving the iteration-cap check to the top (cheapest, checked first) and
the ready/terminal stop conditions to AFTER the DLQ cascade + heartbeat/stale
reaping + the new deterministic requeue_due_tasks.py call — which also closes a
second gap: a worker-reported task_failed whose batch-scoped retry/DLQ step never
ran because the orchestrator's turn ended first now gets resolved here instead of
stalling forever.

These are prompt-level contracts (the orchestrator-*.md files are executed by the
LLM, not by this test suite), so this gate asserts the wiring is present in the
shipped artifacts — matching the house pattern in test_f2_handoff_mode.py.
"""
import re

from conftest import get_dist_dir

dist = get_dist_dir()

_FILES = {
    "dev": dist / "agents" / "orchestrator-dev.md",
    "review": dist / "agents" / "orchestrator-review.md",
    "test": dist / "agents" / "orchestrator-test.md",
    "sdd": dist / "agents" / "orchestrator-sdd.md",
}
_TEXT = {name: path.read_text(encoding="utf-8") for name, path in _FILES.items()}


class TestRequeueScriptCalledBeforeStopConditions:
    def test_each_orchestrator_calls_requeue_due_tasks(self):
        for name, text in _TEXT.items():
            assert "requeue_due_tasks.py" in text, (
                f"orchestrator-{name}.md must delegate retry/DLQ requeue to the "
                "deterministic script instead of prompt-composed backoff math"
            )

    def test_each_call_is_scoped_to_its_own_phase(self):
        for name, text in _TEXT.items():
            assert f"--phase {name}" in text, (
                f"orchestrator-{name}.md's requeue_due_tasks.py call must scope to "
                f"--phase {name}"
            )

    def test_requeue_precedes_stop_conditions_in_each_file(self):
        for name, text in _TEXT.items():
            requeue_pos = text.index("requeue_due_tasks.py")
            # The literal "Stop conditions" (or, for sdd, the workflow-scoped variant)
            # header must appear textually AFTER the requeue call, not before.
            stop_match = re.search(r"\*\*Stop conditions", text)
            assert stop_match is not None, f"orchestrator-{name}.md: no Stop conditions header found"
            assert requeue_pos < stop_match.start(), (
                f"orchestrator-{name}.md: requeue_due_tasks.py must run BEFORE the "
                "stop-condition check — checking against pre-mutation state is "
                "exactly the busy-spin bug this fix closes"
            )

    def test_iteration_cap_checked_before_any_mutation(self):
        for name, text in _TEXT.items():
            iter_match = re.search(r"Iteration ≥ 30", text)
            assert iter_match is not None, f"orchestrator-{name}.md: no iteration cap found"
            requeue_pos = text.index("requeue_due_tasks.py")
            assert iter_match.start() < requeue_pos, (
                f"orchestrator-{name}.md: the iteration-cap check must be the first "
                "thing evaluated each pass, before any mutation spends the budget"
            )

    def test_backoff_wait_stops_cleanly_instead_of_spinning(self):
        for name, text in _TEXT.items():
            assert "earliest_pending_retry_at" in text, (
                f"orchestrator-{name}.md must recognize 'waiting on a due-but-future "
                "retry' as a clean stop, not keep spinning toward the iteration cap"
            )
            assert "waiting on scheduled retry backoff" in text

    def test_sdd_protects_rejection_cycle_task_types(self):
        text = _TEXT["sdd"]
        assert "--protect-task-types spec-writer,spec-validator" in text, (
            "sdd's rejection-cycle check (spec-validator >= 2 attempts) escalates at "
            "a LOWER threshold than the tier's generic max_attempts (3) — without "
            "this exclusion requeue_due_tasks.py would rescheduled it instead, "
            "silently skipping the human escalation"
        )


class TestWaitWindowWiring:
    """--wait-window 90 (2026-07-15 post-fix audit, "double-resume tax"): each
    orchestrator's requeue call must wait out a near-due backoff in-turn instead
    of stopping "blocked on backoff" ~30s before the retry is due — that stop
    cost a full supervisor cycle (heartbeat threshold + tick interval, 15-25 min)
    or a second human invocation just to run the promotion."""

    def test_each_requeue_call_passes_wait_window(self):
        for name, text in _TEXT.items():
            call_lines = "\n".join(
                line for line in text.splitlines()
                if "requeue_due_tasks.py" in line or "--wait-window" in line
            )
            assert "--wait-window 90" in call_lines, (
                f"orchestrator-{name}.md's requeue_due_tasks.py call must pass "
                "--wait-window 90"
            )

    def test_output_contract_documents_waited_seconds(self):
        for name, text in _TEXT.items():
            assert "waited_seconds" in text, (
                f"orchestrator-{name}.md must document the waited_seconds output "
                "field so the LLM does not treat the extra key as an error"
            )
