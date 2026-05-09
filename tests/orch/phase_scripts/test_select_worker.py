"""
Tests for all four select_worker.py scripts (Level A — pure routing tables).

No log fixture is needed; these scripts are stateless.
"""
import pytest
from .conftest import DEV_SCRIPTS, SDD_SCRIPTS, REVIEW_SCRIPTS, TEST_SCRIPTS, run_select


# ---------------------------------------------------------------------------
# DEV — select_worker.py
# ---------------------------------------------------------------------------

class TestDevSelectWorker:
    def test_impl_be(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "impl", "be")
        assert r["worker"] == "u-be-developer"
        assert r["phase"] == "dev"

    def test_impl_fe(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "impl", "fe")
        assert r["worker"] == "u-fe-developer"

    def test_impl_fullstack_falls_back_to_be(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "impl", "fullstack")
        assert r["worker"] == "u-be-developer"

    def test_planning_be(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "planning", "be")
        assert r["worker"] == "u-be-planner"

    def test_planning_fe(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "planning", "fe")
        assert r["worker"] == "u-fe-planner"

    def test_planning_fullstack_falls_back_to_be(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "planning", "fullstack")
        assert r["worker"] == "u-be-planner"

    def test_spec_be(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "spec", "be")
        assert r["worker"] == "u-be-developer"

    def test_spec_fe(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "spec", "fe")
        assert r["worker"] == "u-fe-spec-writer"

    def test_unknown_task_type_returns_default(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "unknown-type", "be")
        assert "worker" in r
        assert r["worker"] == "u-be-developer"

    def test_output_has_required_fields(self):
        r = run_select(DEV_SCRIPTS["select_worker"], "impl", "be")
        assert "worker" in r
        assert "task_type" in r
        assert "stack" in r
        assert "phase" in r
        assert r["task_type"] == "impl"
        assert r["stack"] == "be"


# ---------------------------------------------------------------------------
# SDD — select_worker.py
# ---------------------------------------------------------------------------

class TestSddSelectWorker:
    def test_spec_writer(self):
        r = run_select(SDD_SCRIPTS["select_worker"], "spec-writer")
        assert r["worker"] == "u-spec-writer"
        assert r["phase"] == "sdd"

    def test_spec_reviewer(self):
        r = run_select(SDD_SCRIPTS["select_worker"], "spec-reviewer")
        assert r["worker"] == "u-spec-reviewer"

    def test_spec_back(self):
        r = run_select(SDD_SCRIPTS["select_worker"], "spec-back")
        assert r["worker"] == "u-spec-back"

    def test_spec_front(self):
        r = run_select(SDD_SCRIPTS["select_worker"], "spec-front")
        assert r["worker"] == "u-spec-front"

    def test_spec_validator(self):
        r = run_select(SDD_SCRIPTS["select_worker"], "spec-validator")
        assert r["worker"] == "u-spec-validator"

    def test_spec_compliance(self):
        r = run_select(SDD_SCRIPTS["select_worker"], "spec-compliance")
        assert r["worker"] == "u-spec-compliance"

    def test_unknown_type_returns_default(self):
        r = run_select(SDD_SCRIPTS["select_worker"], "unknown")
        assert r["worker"] == "u-spec-writer"

    def test_output_has_required_fields(self):
        r = run_select(SDD_SCRIPTS["select_worker"], "spec-writer")
        assert "worker" in r
        assert "task_type" in r
        assert "phase" in r


# ---------------------------------------------------------------------------
# REVIEW — select_worker.py
# ---------------------------------------------------------------------------

class TestReviewSelectWorker:
    def test_qa_be(self):
        r = run_select(REVIEW_SCRIPTS["select_worker"], "qa", "be")
        assert r["worker"] == "u-be-qa-docs"
        assert r["phase"] == "review"

    def test_qa_fe(self):
        r = run_select(REVIEW_SCRIPTS["select_worker"], "qa", "fe")
        assert r["worker"] == "u-fe-qa-docs"

    def test_qa_fullstack_falls_back_to_be(self):
        r = run_select(REVIEW_SCRIPTS["select_worker"], "qa", "fullstack")
        assert r["worker"] == "u-be-qa-docs"

    def test_architecture_review_is_stack_independent(self):
        r_be = run_select(REVIEW_SCRIPTS["select_worker"], "architecture-review", "be")
        r_fe = run_select(REVIEW_SCRIPTS["select_worker"], "architecture-review", "fe")
        assert r_be["worker"] == "u-architecture-reviewer"
        assert r_fe["worker"] == "u-architecture-reviewer"

    def test_security_review_is_stack_independent(self):
        r_be = run_select(REVIEW_SCRIPTS["select_worker"], "security-review", "be")
        r_fe = run_select(REVIEW_SCRIPTS["select_worker"], "security-review", "fe")
        assert r_be["worker"] == "u-security-reviewer"
        assert r_fe["worker"] == "u-security-reviewer"

    def test_unknown_qa_type_returns_default(self):
        r = run_select(REVIEW_SCRIPTS["select_worker"], "unknown-review")
        assert r["worker"] == "u-be-qa-docs"


# ---------------------------------------------------------------------------
# TEST — select_worker.py
# ---------------------------------------------------------------------------

class TestTestSelectWorker:
    def test_test_run_be(self):
        r = run_select(TEST_SCRIPTS["select_worker"], "test-run", "be")
        assert r["worker"] == "u-test-runner"
        assert r["phase"] == "test"

    def test_test_run_fe(self):
        r = run_select(TEST_SCRIPTS["select_worker"], "test-run", "fe")
        assert r["worker"] == "u-test-runner"

    def test_test_run_fullstack(self):
        r = run_select(TEST_SCRIPTS["select_worker"], "test-run", "fullstack")
        assert r["worker"] == "u-test-runner"

    def test_unknown_type_returns_default(self):
        r = run_select(TEST_SCRIPTS["select_worker"], "unknown")
        assert r["worker"] == "u-test-runner"

    def test_output_has_required_fields(self):
        r = run_select(TEST_SCRIPTS["select_worker"], "test-run", "be")
        assert {"worker", "task_type", "stack", "phase"} <= r.keys()
