"""
Tests for review-phase exit criteria scripts (Level A).

Scripts under test:
  - check_all_qa_verdicts_approved.py
  - check_no_open_critical_findings.py
  - check_documentation_verified.py
  - check_no_orphan_placeholders.py
"""
import pytest
import orch_core
from orch_core import append_event

from .conftest import REVIEW_SCRIPTS, phase_env, run_check  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _review_phase(wf_id="wf_review_test"):
    append_event("orchestrator", "phase_declared", data={
        "workflow_id": wf_id,
        "phases": [{"name": "review", "order": 1, "required": True}],
    })
    append_event("orchestrator", "phase_entered", data={"phase": "review", "order": 1, "workflow_id": "wf-fix"})


def _review_task(task_id):
    append_event("orchestrator", "task_created", task_id=task_id, data={
        "phase": "review", "tier": "standard", "type": "qa",
        "spec": f"delivery/{task_id}.md", "deps": [],
    })


def _complete_review(task_id, project_dir, verdict="approved",
                     has_critical=False, doc_verified=True):
    """Complete a review task and create a qa-report artifact."""
    qa_dir = project_dir / "specs" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_path = qa_dir / f"{task_id}-qa.md"

    content = f"# QA Report: {task_id}\n\n"
    content += f"verdict: {verdict}\n"
    if has_critical:
        content += "severity: critical\n"
    content += f"documentation_verified: {'true' if doc_verified else 'false'}\n"
    qa_path.write_text(content)

    rel = str(qa_path.relative_to(project_dir))
    append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
        "phase": "review", "worker_type": "qa", "worker_id": f"w_{task_id}",
    })
    append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
        "phase": "review", "artifacts": [rel], "summary": "qa done",
    })
    return rel


# ---------------------------------------------------------------------------
# check_all_qa_verdicts_approved.py
# ---------------------------------------------------------------------------

class TestAllQaVerdictsApproved:
    def test_no_review_tasks_is_not_met(self, phase_env):
        _review_phase()
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["criterion"] == "all_qa_verdicts_approved"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_verdict_rejected_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, verdict="rejected")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is False
        assert any(
            n["verdict_found"] == "rejected"
            for n in result["evidence"]["not_approved"]
        )

    def test_verdict_approved_is_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, verdict="approved")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["approved"] == 1

    def test_verdict_approved_with_reservations_is_not_met(self, phase_env):
        # approved_with_reservations is no longer a valid verdict — binary verdict only
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, verdict="approved_with_reservations")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is False
        assert len(result["evidence"]["not_approved"]) == 1

    def test_mixed_approved_and_rejected_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _review_task("review_dev_tc_002")
        _complete_review("review_dev_tc_001", phase_env, verdict="approved")
        _complete_review("review_dev_tc_002", phase_env, verdict="rejected")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["approved"] == 1
        assert len(result["evidence"]["not_approved"]) == 1

    def test_all_approved_is_met(self, phase_env):
        _review_phase()
        for i in range(1, 4):
            _review_task(f"review_dev_tc_{i:03d}")
            _complete_review(f"review_dev_tc_{i:03d}", phase_env, verdict="approved")
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["approved"] == 3

    def test_verdict_field_absent_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        # Write qa file without verdict field
        qa_dir = phase_env / "specs" / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        qa_path = qa_dir / "review_dev_tc_001-qa.md"
        qa_path.write_text("# QA Report\n\nsummary: reviewed\n")
        append_event("worker", "task_claimed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review", "worker_type": "qa", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review",
            "artifacts": [str(qa_path.relative_to(phase_env))],
            "summary": "done",
        })
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is False

    def test_template_frontmatter_artifact_is_met(self, phase_env):
        """SIEGARD BUG-2: an artifact produced from the official template (YAML
        frontmatter `verdict:` + bold human label) passes the gate without manual
        editing — the exact failure mode the forensic report flagged."""
        _review_phase()
        _review_task("review_dev_tc_001")
        qa_dir = phase_env / "specs" / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        qa_path = qa_dir / "review_dev_tc_001-qa.md"
        qa_path.write_text(
            "---\n"
            "task_id: review_dev_tc_001\n"
            "verdict: approved\n"
            "documentation_verified: true\n"
            "---\n\n"
            "# QA Report: review_dev_tc_001\n\n"
            "**Verdict:** Approved\n"
        )
        append_event("worker", "task_claimed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review", "worker_type": "qa", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review", "artifacts": [str(qa_path.relative_to(phase_env))],
            "summary": "done",
        })
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["approved"] == 1

    def test_legacy_bold_only_verdict_is_met(self, phase_env):
        """SIEGARD BUG-2 (defensive net): even a legacy `**Verdict:** Approved` line
        with no frontmatter is now read as approved instead of 'unknown'."""
        _review_phase()
        _review_task("review_dev_tc_001")
        qa_dir = phase_env / "specs" / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        qa_path = qa_dir / "review_dev_tc_001-qa.md"
        qa_path.write_text("# QA Report\n\n**Verdict:** Approved\n")
        append_event("worker", "task_claimed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review", "worker_type": "qa", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review", "artifacts": [str(qa_path.relative_to(phase_env))],
            "summary": "done",
        })
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is True

    def test_arch_review_artifact_does_not_block_qa_verdict(self, phase_env):
        """SIEGARD BUG-2 (extension): an architecture-review task is a review-phase
        task whose artifact carries findings, not an approved/rejected verdict. The
        qa-verdict gate scopes to qa-type tasks and must IGNORE it — otherwise the
        verdict-less arch.yaml reads as 'unknown' and blocks with a spurious E08
        (forensic report seq 69). Arch/sec severity is governed by no_open_critical."""
        _review_phase()
        _review_task("review_dev_tc_001")  # type: qa
        _complete_review("review_dev_tc_001", phase_env, verdict="approved")
        # Architecture-review task — completed, artifact has no `verdict` field.
        append_event("orchestrator", "task_created", task_id="review_arch_001", data={
            "phase": "review", "tier": "standard", "type": "architecture-review",
            "spec": "delivery/tc_001.md", "deps": [],
        })
        reviews_dir = phase_env / "specs" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        arch_path = reviews_dir / "review_arch_001-arch.yaml"
        arch_path.write_text("scan:\n  id: ARCH-1\nfindings:\n  - id: AFND-001\n    severity: P1\n")
        append_event("worker", "task_claimed", task_id="review_arch_001", attempt=1, data={
            "phase": "review", "worker_type": "architecture-review", "worker_id": "w_arch",
        })
        append_event("worker", "task_completed", task_id="review_arch_001", attempt=1, data={
            "phase": "review", "artifacts": [str(arch_path.relative_to(phase_env))],
            "summary": "arch done",
        })
        result = run_check(REVIEW_SCRIPTS["check_verdicts"], phase_env)
        assert result["met"] is True
        # Only the qa artifact is counted — the arch artifact is out of scope.
        assert result["evidence"]["total"] == 1
        assert result["evidence"]["approved"] == 1


# ---------------------------------------------------------------------------
# check_no_open_critical_findings.py
# ---------------------------------------------------------------------------

class TestNoOpenCriticalFindings:
    def test_no_review_tasks_is_met(self, phase_env):
        _review_phase()
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["criterion"] == "no_open_critical_findings"
        assert result["met"] is True
        assert result["evidence"]["total"] == 0

    def test_no_critical_severity_is_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, has_critical=False)
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["clean"] == 1

    def test_critical_finding_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, has_critical=True)
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is False
        assert any(
            v["reason"] == "critical_finding_present"
            for v in result["evidence"]["with_critical"]
        )

    def test_one_critical_one_clean_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _review_task("review_dev_tc_002")
        _complete_review("review_dev_tc_001", phase_env, has_critical=False)
        _complete_review("review_dev_tc_002", phase_env, has_critical=True)
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["clean"] == 1
        assert len(result["evidence"]["with_critical"]) == 1

    def _complete_arch_review(self, task_id, project_dir, severity):
        """Complete an architecture-review task with a finding at the given P-severity."""
        append_event("orchestrator", "task_created", task_id=task_id, data={
            "phase": "review", "tier": "standard", "type": "architecture-review",
            "spec": "delivery/tc_001.md", "deps": [],
        })
        reviews_dir = project_dir / "specs" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        arch_path = reviews_dir / f"{task_id}-arch.yaml"
        arch_path.write_text(
            "scan:\n  id: ARCH-1\nfindings:\n"
            f"  - id: AFND-001\n    pattern: circular_dependency\n    severity: {severity}\n"
        )
        append_event("worker", "task_claimed", task_id=task_id, attempt=1, data={
            "phase": "review", "worker_type": "architecture-review", "worker_id": f"w_{task_id}"})
        append_event("worker", "task_completed", task_id=task_id, attempt=1, data={
            "phase": "review", "artifacts": [str(arch_path.relative_to(project_dir))],
            "summary": "arch done"})

    def test_architecture_p0_finding_blocks(self, phase_env):
        """A1 (Lote 2): a P0 architecture finding (critical-equivalent on the P0/P1/P2
        scale) must block — the gate previously matched only `severity: critical` and
        missed the entire architecture scale."""
        _review_phase()
        self._complete_arch_review("review_arch_001", phase_env, "P0")
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is False
        assert any(v["reason"] == "critical_finding_present"
                   for v in result["evidence"]["with_critical"])

    def test_architecture_p1_finding_does_not_block(self, phase_env):
        """A1 (Lote 2): P1 (high-equivalent) is NOT a critical finding — a gate named
        'no_open_critical_findings' does not block on it."""
        _review_phase()
        self._complete_arch_review("review_arch_002", phase_env, "P1")
        result = run_check(REVIEW_SCRIPTS["check_critical"], phase_env)
        assert result["met"] is True


# ---------------------------------------------------------------------------
# check_documentation_verified.py
# ---------------------------------------------------------------------------

class TestDocumentationVerified:
    def test_no_review_tasks_is_not_met(self, phase_env):
        _review_phase()
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["criterion"] == "documentation_verified"
        assert result["met"] is False
        assert result["evidence"]["total"] == 0

    def test_field_absent_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        qa_dir = phase_env / "specs" / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        qa_path = qa_dir / "review_dev_tc_001-qa.md"
        qa_path.write_text("verdict: approved\n")
        append_event("worker", "task_claimed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review", "worker_type": "qa", "worker_id": "w_001",
        })
        append_event("worker", "task_completed", task_id="review_dev_tc_001", attempt=1, data={
            "phase": "review",
            "artifacts": [str(qa_path.relative_to(phase_env))],
            "summary": "done",
        })
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["field_absent"] == 1

    def test_documentation_verified_false_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, doc_verified=False)
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is False
        assert len(result["evidence"]["verified_false"]) == 1

    def test_documentation_verified_true_is_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _complete_review("review_dev_tc_001", phase_env, doc_verified=True)
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["verified_true"] == 1

    def test_all_verified_is_met(self, phase_env):
        _review_phase()
        for i in range(1, 3):
            _review_task(f"review_dev_tc_{i:03d}")
            _complete_review(f"review_dev_tc_{i:03d}", phase_env, doc_verified=True)
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["verified_true"] == 2

    def test_one_true_one_false_is_not_met(self, phase_env):
        _review_phase()
        _review_task("review_dev_tc_001")
        _review_task("review_dev_tc_002")
        _complete_review("review_dev_tc_001", phase_env, doc_verified=True)
        _complete_review("review_dev_tc_002", phase_env, doc_verified=False)
        result = run_check(REVIEW_SCRIPTS["check_docs"], phase_env)
        assert result["met"] is False
        assert result["evidence"]["verified_true"] == 1
        assert len(result["evidence"]["verified_false"]) == 1


# ---------------------------------------------------------------------------
# check_no_orphan_placeholders.py  (R2 — orphan placeholder gate)
# ---------------------------------------------------------------------------

class TestNoOrphanPlaceholders:
    def _src(self, project_dir, rel, content):
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_empty_project_is_met(self, phase_env):
        # No source roots present → vacuously met (additive gate, fail-open on empty).
        result = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env)
        assert result["criterion"] == "no_orphan_placeholders"
        assert result["met"] is True
        assert result["evidence"]["scanned"] == 0

    def test_clean_source_is_met(self, phase_env):
        self._src(phase_env, "frontend/src/features/curation/CurationPage.tsx",
                  "export function CurationPage() {\n  return <DecisionPanel />;\n}\n")
        result = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["scanned"] == 1
        assert result["evidence"]["hits"] == []

    def test_headline_placeholder_blocks(self, phase_env):
        # The exact SIEGARD D1 failure: the entry surface shipped a placeholder.
        self._src(phase_env, "frontend/src/features/curation/CurationPage.tsx",
                  "/** Placeholder DecisionPanel — TC-05 swaps the inner content. */\n"
                  "export function CurationPage() {\n"
                  "  return <p>Painel de decisão em construção (TC-05).</p>;\n"
                  "}\n")
        result = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env)
        assert result["met"] is False
        markers_hit = {h["marker"] for h in result["evidence"]["hits"]}
        assert "swaps the inner content" in markers_hit
        assert "em construção" in markers_hit
        assert all(h["file"].endswith("CurationPage.tsx") for h in result["evidence"]["hits"])

    def test_todo_tc_marker_blocks(self, phase_env):
        self._src(phase_env, "src/widget.ts", "// TODO: TC-09 wire the real store\nexport const x = 1;\n")
        result = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env)
        assert result["met"] is False
        assert any(h["line"] == 1 for h in result["evidence"]["hits"])

    def test_test_files_are_skipped(self, phase_env):
        # A marker inside a test fixture is not a shipped surface — must not block.
        self._src(phase_env, "frontend/src/CurationPage.test.tsx",
                  "it('renders', () => { /* em construção */ });\n")
        self._src(phase_env, "frontend/src/__tests__/foo.ts", "// swaps the inner content\n")
        result = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env)
        assert result["met"] is True

    def test_excluded_dirs_are_skipped(self, phase_env):
        self._src(phase_env, "src/node_modules/dep/index.js", "// em construção\n")
        self._src(phase_env, "src/real.ts", "export const ok = true;\n")
        result = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["scanned"] == 1

    def test_extra_marker_env_blocks(self, phase_env):
        self._src(phase_env, "src/page.tsx", "// stub: pending implementation\nexport const p = 1;\n")
        # default markers do not include "stub:" — clean until the project adds it.
        clean = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env)
        assert clean["met"] is True
        blocked = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env,
                            extra_env={"ORCH_PLACEHOLDER_EXTRA_MARKERS": "stub:"})
        assert blocked["met"] is False

    def test_scan_paths_env_scopes_scan(self, phase_env):
        self._src(phase_env, "legacy/old.ts", "// em construção\n")  # outside scoped root
        self._src(phase_env, "frontend/src/new.ts", "export const n = 1;\n")
        result = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env,
                           extra_env={"ORCH_PLACEHOLDER_SCAN_PATHS": "frontend/src"})
        assert result["met"] is True
        assert result["evidence"]["scanned"] == 1

    def test_non_source_extension_ignored(self, phase_env):
        self._src(phase_env, "src/README.md", "Section em construção\n")
        result = run_check(REVIEW_SCRIPTS["check_placeholders"], phase_env)
        assert result["met"] is True
        assert result["evidence"]["scanned"] == 0
