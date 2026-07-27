"""R02 — a reviewer may not become the author of what it reviews.

The production incident, in full:

    att=1  task_failed  reason=validation_failed retryable=true
           "REVISION NEEDED — 2 Major issues in mwo-catalog.spec.md v1.6.0"
           ... no spec-writer task is created between the failure and the retry ...
    att=2  task_completed
           "APPROVED — 2 minor corrections applied inline: changelog reordered;
            obsolete BR-08 v1.1.0 adapter contract block removed"
           artifacts: [mwo-catalog.spec.md, openapi.yaml]

The agent whose entire reason for existing is separation of duties became author
and approver, and downgraded its own two Major findings to "minor" to justify it.
The retry policy produced that outcome: the only path to terminal-success was for
the problem to disappear.

Three independent guards, one per layer:
  R02b  should_retry refuses to retry `validation_failed` on a verdict task type
  R02c  emit.py refuses a reviewer artifact under `domains/` at runtime
  W09   check_worker refuses the same thing in the agent's documented contract
and R02a gives the corrective action a real route: the writer revises.
"""
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
sys.path.insert(0, str(dist / "lib"))
sys.path.insert(0, str(dist / "skills" / "u-worker-compliance" / "scripts"))

import orch_core  # noqa: E402

REVIEWER = dist / "agents" / "spec" / "u-spec-reviewer.md"
SDD = dist / "agents" / "orchestrator-sdd.md"


def _emit_module():
    path = dist / "skills" / "orch-report" / "scripts" / "emit.py"
    spec = importlib.util.spec_from_file_location("emit_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _task(task_type, reason, attempts=1, retryable=True):
    return orch_core.TaskState(
        task_id=f"sdd_wf_dom_{task_type}",
        phase="sdd",
        status=orch_core.TaskStatus.FAILED,
        deps=[],
        tier="standard",
        task_type=task_type,
        spec="specs/domains/dom/",
        attempts=attempts,
        last_failure_reason=reason,
        last_failure_retryable=retryable,
    )


# ---------------------------------------------------------------------------
# R02b — a verdict is not a transient failure
# ---------------------------------------------------------------------------

class TestVerdictIsNotRetried:
    @pytest.mark.parametrize("task_type", ["spec-reviewer", "spec-validator"])
    def test_validation_failed_on_a_judge_is_never_retried(self, task_type):
        policy = orch_core.RetryPolicy(max_attempts=3, base_delay_s=1, cap_s=60)
        t = _task(task_type, "validation_failed", attempts=1)
        assert orch_core.should_retry(t, policy) is False, (
            "retrying the same judge over unchanged input can only pressure it to "
            "change its mind — which is exactly what happened"
        )

    def test_other_task_types_still_retry_validation_failed(self):
        """The guard is scoped to judges; a writer failing validation may retry."""
        policy = orch_core.RetryPolicy(max_attempts=3, base_delay_s=1, cap_s=60)
        t = _task("spec-writer", "validation_failed", attempts=1)
        assert orch_core.should_retry(t, policy) is True

    @pytest.mark.parametrize("task_type", ["spec-reviewer", "spec-validator"])
    def test_genuine_worker_failures_still_retry(self, task_type):
        """A judge whose own execution broke is a different case entirely."""
        policy = orch_core.RetryPolicy(max_attempts=3, base_delay_s=1, cap_s=60)
        t = _task(task_type, "internal_error", attempts=1)
        assert orch_core.should_retry(t, policy) is True

    def test_verdict_task_types_are_declared(self):
        assert orch_core._VERDICT_TASK_TYPES == frozenset(
            {"spec-reviewer", "spec-validator"})


# ---------------------------------------------------------------------------
# R02c — runtime refusal (P6/P7: outside the LLM)
# ---------------------------------------------------------------------------

class TestRuntimeArtifactGuard:
    @pytest.mark.parametrize("path", [
        "docs/specs/domains/mwo-catalog/mwo-catalog.spec.md",
        "docs/specs/domains/mwo-catalog/openapi.yaml",
        "/abs/project/specs/domains/x/x.back.md",
        r"docs\specs\domains\x\openapi.yaml",
    ])
    def test_reviewer_cannot_register_a_reviewed_artifact(self, path):
        mod = _emit_module()
        v = mod._review_only_violation("u-spec-reviewer-sdd_wf_x_spec-reviewer", path)
        assert v is not None, f"{path} must be refused"
        assert "review-only" in v

    @pytest.mark.parametrize("path", [
        "docs/specs/_validation/x-review.md",
        ".orch/sessions/wf/reviews/x-review.md",
        "/abs/.orch/sessions/wf/qa/report.md",
    ])
    def test_reviewer_may_register_its_own_report(self, path):
        mod = _emit_module()
        assert mod._review_only_violation(
            "u-spec-reviewer-sdd_wf_x_spec-reviewer", path) is None

    @pytest.mark.parametrize("worker", ["u-spec-writer", "u-spec-back", "u-spec-front"])
    def test_authoring_workers_are_unaffected(self, worker):
        """Writers must keep writing specs — the guard is about judges only."""
        mod = _emit_module()
        assert mod._review_only_violation(
            f"{worker}-sdd_wf_x_{worker}", "docs/specs/domains/x/openapi.yaml") is None

    def test_review_only_set_is_declared(self):
        mod = _emit_module()
        assert "u-spec-reviewer" in mod._REVIEW_ONLY_WORKERS


# ---------------------------------------------------------------------------
# W09 — contract-level refusal
# ---------------------------------------------------------------------------

class TestW09ContractGuard:
    def test_shipped_reviewer_passes(self):
        cw = importlib.import_module("check_worker")
        importlib.reload(cw)
        assert cw.check_file(REVIEWER).status == "pass"

    def test_rule_fires_on_a_contract_that_invites_it(self, tmp_path):
        cw = importlib.import_module("check_worker")
        importlib.reload(cw)
        bad = tmp_path / "u-spec-reviewer.md"
        src = REVIEWER.read_text(encoding="utf-8").replace(
            '"artifacts": ["<your review report path>"]',
            '"artifacts": ["docs/specs/domains/x/openapi.yaml"]')
        bad.write_text(src, encoding="utf-8")
        result = cw.check_file(bad)
        assert result.status == "fail"
        assert any(v.rule == "W09" and v.severity == "critical"
                   for v in result.violations)

    def test_rule_ignores_non_review_workers(self, tmp_path):
        cw = importlib.import_module("check_worker")
        importlib.reload(cw)
        f = tmp_path / "u-spec-writer.md"
        f.write_text('--data \'{"artifacts": ["docs/specs/domains/x/openapi.yaml"]}\'',
                     encoding="utf-8")
        assert cw._check_w09_review_only_artifacts(
            f.read_text(encoding="utf-8"), f) == []


# ---------------------------------------------------------------------------
# R02a — the corrective action exists and points at the writer
# ---------------------------------------------------------------------------

class TestVerdictRoutingContract:
    def test_reviewer_emits_the_verdict_as_completion_data(self):
        text = REVIEWER.read_text(encoding="utf-8")
        assert '"verdict"' in text
        assert "revision_needed" in text
        idx = text.index("--kind completed")
        assert "verdict" in text[idx:idx + 600], (
            "the verdict must travel on the completed event the orchestrator routes on"
        )

    def test_reviewer_forbids_expressing_a_verdict_as_failure(self):
        text = REVIEWER.read_text(encoding="utf-8")
        assert "Never emit `task_failed` with `reason: validation_failed` to express a verdict" in text

    def test_reviewer_prohibition_has_no_severity_loophole(self):
        """The old rule read "NEVER rewrite the spec — automatic corrections are
        for minor issues only": it forbade and permitted in one sentence, and that
        is the loophole the reviewer used. The rule must now be absolute.

        The old wording may still appear as a QUOTED historical note; what must not
        survive is the permission attached to the prohibition itself.
        """
        text = REVIEWER.read_text(encoding="utf-8")
        rule_line = next(l for l in text.splitlines()
                         if l.strip().startswith("2. **NEVER rewrite the spec"))
        assert "no exception, no severity threshold" in rule_line
        assert "minor issues only" not in rule_line

    def test_orchestrator_routes_revision_to_the_writer(self):
        text = SDD.read_text(encoding="utf-8")
        assert "spec-writer-revision-" in text, (
            "revision_needed must create a WRITER task; retrying the reviewer is "
            "the defect"
        )
        assert "spec-reviewer-revision-" in text, (
            "a fresh reviewer must re-judge the revised artifact"
        )

    def test_routing_passes_the_review_report_as_context(self):
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("spec-writer-revision-")
        assert "repair_context" in text[idx - 500:idx + 900]

    def test_revision_cycles_are_bounded(self):
        text = SDD.read_text(encoding="utf-8")
        idx = text.index("revision_cycles")
        window = text[idx:idx + 1200]
        assert "E05_rejection_cycle_limit" in window, (
            "unbounded revision would loop; two rounds then a human decides"
        )

    def test_routing_precedes_retry_decisions(self):
        """Verdict routing must run before the generic retry branch, or the old
        path reclaims the case."""
        text = SDD.read_text(encoding="utf-8")
        assert text.index("route reviewer verdicts") < text.index(
            "**Then: retry decisions.**")
