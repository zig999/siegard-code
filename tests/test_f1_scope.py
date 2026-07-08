"""F1 — change scope: an /u-improve gates and dispatches only the domains it touches.

A breaking one-domain /u-improve is legitimately classified `full`/`standard`.
Standard mode used to treat every on-disk domain as `new` (full pipeline for all)
and the exit gate + handoff scan required EVERY domain VALID — so a one-domain
change cascaded across the project and a stale INVALID/handoff_allowed:false in an
untouched domain blocked an unrelated change (the F3 symptom).

scope.py derives the affected-domain set from triage.affected_specs; the gate
(check_all_domains_validated) and the handoff scan (generate_handoff_manifest)
restrict themselves to it. u-spec / greenfield keep the global behavior.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "dist/.claude/skills/phase-sdd-rules/scripts"
DEV_SCRIPTS = ROOT / "dist/.claude/skills/phase-dev-rules/scripts"
WID = "wf-test"


def _run(script: str, project_dir: Path, *args: str):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs"}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, env=env,
    )


def _domain(specs: Path, name: str, *, status: str = "VALID", handoff: str | None = None):
    d = specs / "domains" / name
    (d / "back").mkdir(parents=True, exist_ok=True)
    (d / "openapi.yaml").write_text(
        f"openapi: 3.0.3\ninfo:\n  title: {name}\n  version: 1.0.0\npaths: {{}}\n")
    (d / f"{name}.spec.md").write_text(f"# {name}\n\n> Version: 1.0.0\n")
    (d / "back" / f"{name}.back.md").write_text(f"# {name} back\n\n> Version: 1.0.0\n")
    val = specs / "_validation"
    val.mkdir(parents=True, exist_ok=True)
    ho = handoff if handoff is not None else ("true" if status == "VALID" else "false")
    (val / f"{name}-validation-result.yaml").write_text(
        f"domain: {name}\nstatus: {status}\nblocking_count: 0\nhandoff_allowed: {ho}\n")


def _triage(project_dir: Path, *, trigger: str, affected: list[str]):
    sess = project_dir / ".orch" / "sessions" / WID
    sess.mkdir(parents=True, exist_ok=True)
    (sess / "triage.json").write_text(json.dumps({
        "workflow_id": WID, "trigger": trigger, "greenfield": trigger == "u-spec",
        "type": "spec_change_required", "mode_hint": "full",
        "affected_specs": [{"path": f"specs/domains/{d}/openapi.yaml"} for d in affected],
    }))


def _build(tmp_path: Path, domains: dict, *, trigger: str, affected: list[str]) -> Path:
    specs = tmp_path / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    (specs / "error-codes.md").write_text("# Error Codes\n")
    for name, kw in domains.items():
        _domain(specs, name, **kw)
    _triage(tmp_path, trigger=trigger, affected=affected)
    return specs


# --------------------------------------------------------------------------- #
# scope.py                                                                     #
# --------------------------------------------------------------------------- #
class TestScope:
    def test_improve_returns_affected_domains(self, tmp_path):
        _triage(tmp_path, trigger="u-improve", affected=["ifs-integration"])
        out = json.loads(_run("scope.py", tmp_path, "--workflow-id", WID).stdout)
        assert out["scoped"] is True
        assert out["domains"] == ["ifs-integration"]

    def test_uspec_is_unscoped(self, tmp_path):
        _triage(tmp_path, trigger="u-spec", affected=[])
        out = json.loads(_run("scope.py", tmp_path, "--workflow-id", WID).stdout)
        assert out["scoped"] is False
        assert out["domains"] is None

    def test_front_only_improve_is_unscoped(self, tmp_path):
        # affected_specs with no domains/<slug>/ path → cannot narrow → global.
        sess = tmp_path / ".orch" / "sessions" / WID
        sess.mkdir(parents=True)
        (sess / "triage.json").write_text(json.dumps({
            "workflow_id": WID, "trigger": "u-improve",
            "affected_specs": [{"path": "specs/front/front.md"}],
        }))
        out = json.loads(_run("scope.py", tmp_path, "--workflow-id", WID).stdout)
        assert out["scoped"] is False

    def test_missing_triage_is_unscoped(self, tmp_path):
        out = json.loads(_run("scope.py", tmp_path, "--workflow-id", WID).stdout)
        assert out["scoped"] is False


# --------------------------------------------------------------------------- #
# check_all_domains_validated.py — scoped gate                                 #
# --------------------------------------------------------------------------- #
class TestScopedGate:
    def test_untouched_invalid_domain_does_not_block_improve(self, tmp_path):
        # ifs-integration (touched) VALID; assyst-delivery (untouched) INVALID.
        _build(tmp_path, {
            "ifs-integration": {"status": "VALID"},
            "assyst-delivery": {"status": "INVALID"},
        }, trigger="u-improve", affected=["ifs-integration"])
        r = _run("check_all_domains_validated.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        out = json.loads(r.stdout)
        assert out["met"] is True
        assert out["evidence"]["scoped"] is True
        # the untouched INVALID is surfaced for audit, not blocking
        names = [f["file"] for f in out["evidence"]["out_of_scope_invalid"]]
        assert "assyst-delivery-validation-result.yaml" in names

    def test_touched_invalid_domain_blocks(self, tmp_path):
        _build(tmp_path, {
            "ifs-integration": {"status": "INVALID"},
            "assyst-delivery": {"status": "VALID"},
        }, trigger="u-improve", affected=["ifs-integration"])
        r = _run("check_all_domains_validated.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 1
        out = json.loads(r.stdout)
        assert out["met"] is False
        names = [f["file"] for f in out["evidence"]["failing"]]
        assert "ifs-integration-validation-result.yaml" in names

    def test_uspec_stays_global(self, tmp_path):
        # No scoping for u-spec: an INVALID domain blocks even if "not targeted".
        _build(tmp_path, {
            "auth": {"status": "VALID"},
            "billing": {"status": "INVALID"},
        }, trigger="u-spec", affected=[])
        r = _run("check_all_domains_validated.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 1
        assert json.loads(r.stdout)["evidence"]["scoped"] is False

    def test_no_workflow_id_is_global_backcompat(self, tmp_path):
        _build(tmp_path, {
            "auth": {"status": "VALID"},
            "billing": {"status": "INVALID"},
        }, trigger="u-improve", affected=["auth"])
        r = _run("check_all_domains_validated.py", tmp_path)  # no --workflow-id
        assert r.returncode == 1  # global: billing INVALID blocks
        assert json.loads(r.stdout)["evidence"]["scoped"] is False


# --------------------------------------------------------------------------- #
# generate_handoff_manifest.py — scoped approval scan                          #
# --------------------------------------------------------------------------- #
class TestScopedHandoff:
    def test_untouched_false_does_not_block(self, tmp_path):
        # assyst-delivery (untouched) has a stale handoff_allowed:false; the improve
        # touches only ifs-integration → manifest must still generate (fix F1/F3).
        specs = _build(tmp_path, {
            "ifs-integration": {"status": "VALID", "handoff": "true"},
            "assyst-delivery": {"status": "VALID", "handoff": "false"},
        }, trigger="u-improve", affected=["ifs-integration"])
        r = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        assert json.loads(r.stdout)["status"] == "ok"
        assert (specs / "handoff-manifest.yaml").exists()

    def test_touched_false_blocks(self, tmp_path):
        specs = _build(tmp_path, {
            "ifs-integration": {"status": "VALID", "handoff": "false"},
        }, trigger="u-improve", affected=["ifs-integration"])
        r = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert r.returncode != 0
        assert json.loads(r.stdout)["reason"] == "approval_blocked"
        assert not (specs / "handoff-manifest.yaml").exists()

    def test_uspec_false_still_blocks_global(self, tmp_path):
        specs = _build(tmp_path, {
            "auth": {"status": "VALID", "handoff": "true"},
            "billing": {"status": "VALID", "handoff": "false"},
        }, trigger="u-spec", affected=[])
        r = _run("generate_handoff_manifest.py", tmp_path, "--workflow-id", WID)
        assert r.returncode != 0
        assert json.loads(r.stdout)["reason"] == "approval_blocked"
        assert not (specs / "handoff-manifest.yaml").exists()


# --------------------------------------------------------------------------- #
# check_error_codes_synced.py — scoped error-code gate (L1)                    #
# --------------------------------------------------------------------------- #
def _write_code(specs: Path, domain: str, code: str):
    (specs / "domains" / domain / "openapi.yaml").write_text(
        f"openapi: 3.0.3\ninfo:\n  title: {domain}\n  version: 1.0.0\n"
        f"paths: {{}}\nx-errors:\n  - code: {code}\n")


class TestScopedErrorCodes:
    def test_untouched_domain_orphan_code_does_not_block_improve(self, tmp_path):
        # legacy (untouched) references E4102, never registered — pre-existing
        # defect of an untouched domain must not block this change (L1 / F3).
        specs = _build(tmp_path, {
            "billing": {"status": "VALID"},
            "legacy": {"status": "VALID"},
        }, trigger="u-improve", affected=["billing"])
        _write_code(specs, "legacy", "E4102")
        r = _run("check_error_codes_synced.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        out = json.loads(r.stdout)
        assert out["met"] is True
        assert out["evidence"]["scoped"] is True
        assert out["evidence"]["missing_codes"] == []
        assert out["evidence"]["out_of_scope_missing"] == ["E4102"]

    def test_touched_domain_orphan_code_blocks(self, tmp_path):
        specs = _build(tmp_path, {
            "billing": {"status": "VALID"},
            "legacy": {"status": "VALID"},
        }, trigger="u-improve", affected=["billing"])
        _write_code(specs, "billing", "E4103")
        r = _run("check_error_codes_synced.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 1
        out = json.loads(r.stdout)
        assert out["met"] is False
        assert out["evidence"]["missing_codes"] == ["E4103"]

    def test_code_shared_between_scopes_blocks(self, tmp_path):
        # A code referenced by an in-scope AND an out-of-scope file is gated.
        specs = _build(tmp_path, {
            "billing": {"status": "VALID"},
            "legacy": {"status": "VALID"},
        }, trigger="u-improve", affected=["billing"])
        _write_code(specs, "billing", "E4104")
        _write_code(specs, "legacy", "E4104")
        r = _run("check_error_codes_synced.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 1
        out = json.loads(r.stdout)
        assert out["evidence"]["missing_codes"] == ["E4104"]
        assert out["evidence"]["out_of_scope_missing"] == []

    def test_non_domain_file_code_always_blocks(self, tmp_path):
        # A code in a file outside domains/<slug>/ cannot be attributed — conservative.
        specs = _build(tmp_path, {
            "billing": {"status": "VALID"},
        }, trigger="u-improve", affected=["billing"])
        (specs / "flows").mkdir()
        (specs / "flows" / "checkout.md").write_text("error_code: E4105\n")
        r = _run("check_error_codes_synced.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 1
        assert json.loads(r.stdout)["evidence"]["missing_codes"] == ["E4105"]

    def test_registered_code_in_untouched_domain_stays_ok(self, tmp_path):
        specs = _build(tmp_path, {
            "billing": {"status": "VALID"},
            "legacy": {"status": "VALID"},
        }, trigger="u-improve", affected=["billing"])
        _write_code(specs, "legacy", "E4106")
        (specs / "error-codes.md").write_text("# Error Codes\n\n- E4106 — legacy error\n")
        r = _run("check_error_codes_synced.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        out = json.loads(r.stdout)
        assert out["evidence"]["out_of_scope_missing"] == []

    def test_uspec_stays_global(self, tmp_path):
        specs = _build(tmp_path, {
            "auth": {"status": "VALID"},
            "billing": {"status": "VALID"},
        }, trigger="u-spec", affected=[])
        _write_code(specs, "billing", "E4107")
        r = _run("check_error_codes_synced.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 1
        out = json.loads(r.stdout)
        assert out["evidence"]["scoped"] is False
        assert out["evidence"]["missing_codes"] == ["E4107"]

    def test_no_workflow_id_is_global_backcompat(self, tmp_path):
        specs = _build(tmp_path, {
            "billing": {"status": "VALID"},
            "legacy": {"status": "VALID"},
        }, trigger="u-improve", affected=["billing"])
        _write_code(specs, "legacy", "E4108")
        r = _run("check_error_codes_synced.py", tmp_path)  # no --workflow-id
        assert r.returncode == 1  # global: legacy orphan code blocks
        assert json.loads(r.stdout)["evidence"]["scoped"] is False


# --------------------------------------------------------------------------- #
# identify_invalid_domains.py — scoped repair targets (L3)                     #
# --------------------------------------------------------------------------- #
def _validation_md(specs: Path, domain: str, status: str):
    val = specs / "_validation"
    val.mkdir(parents=True, exist_ok=True)
    (val / f"{domain}-validation.md").write_text(
        f"# Validation — {domain}\n\nstatus: {status}\n")


class TestScopedRepairTargets:
    def test_untouched_invalid_domain_not_a_repair_target(self, tmp_path):
        # Stale INVALID in untouched domain must NOT enter this workflow's
        # repair dispatch (L3): the scoped gate already ignores it.
        specs = _build(tmp_path, {
            "billing": {"status": "INVALID"},
            "legacy": {"status": "INVALID"},
        }, trigger="u-improve", affected=["billing"])
        _validation_md(specs, "billing", "INVALID")
        _validation_md(specs, "legacy", "INVALID")
        r = _run("identify_invalid_domains.py", tmp_path, "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        out = json.loads(r.stdout)
        assert out["invalid_domains"] == ["billing"]
        assert out["out_of_scope_invalid"] == ["legacy"]
        assert out["scoped"] is True
        assert "legacy" not in out["defect_origins"]

    def test_uspec_stays_global(self, tmp_path):
        specs = _build(tmp_path, {
            "auth": {"status": "VALID"},
            "billing": {"status": "INVALID"},
        }, trigger="u-spec", affected=[])
        _validation_md(specs, "billing", "INVALID")
        r = _run("identify_invalid_domains.py", tmp_path, "--workflow-id", WID)
        out = json.loads(r.stdout)
        assert out["invalid_domains"] == ["billing"]
        assert out["out_of_scope_invalid"] == []
        assert out["scoped"] is False

    def test_no_workflow_id_is_global_backcompat(self, tmp_path):
        specs = _build(tmp_path, {
            "billing": {"status": "INVALID"},
            "legacy": {"status": "INVALID"},
        }, trigger="u-improve", affected=["billing"])
        _validation_md(specs, "billing", "INVALID")
        _validation_md(specs, "legacy", "INVALID")
        r = _run("identify_invalid_domains.py", tmp_path)  # no --workflow-id
        out = json.loads(r.stdout)
        assert out["invalid_domains"] == ["billing", "legacy"]
        assert out["scoped"] is False


# --------------------------------------------------------------------------- #
# check_backlog_scope.py — post-planner scope guard (L4)                       #
# --------------------------------------------------------------------------- #
def _run_dev(script: str, project_dir: Path, *args: str):
    env = {**os.environ, "ORCH_PROJECT_DIR": str(project_dir), "SPECS_DIR": "specs"}
    return subprocess.run(
        [sys.executable, str(DEV_SCRIPTS / script), *args],
        capture_output=True, text=True, env=env,
    )


def _backlog(project_dir: Path, tcs: list[dict]) -> Path:
    """Write backlog.json + a tc-NNN.md per entry (spec_refs in the body)."""
    bdir = project_dir / ".orch" / "sessions" / WID / "backlog"
    bdir.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, tc in enumerate(tcs, 1):
        tc_file = bdir / f"tc-{i:03d}.md"
        refs = "\n".join(f"- path: specs/domains/{d}/openapi.yaml"
                         for d in tc.get("domains", []))
        tc_file.write_text(
            f"# TC-{i:03d} — {tc.get('title', 'task')}\n\n"
            f"## Spec inputs\n{refs or '- path: specs/front/front.md'}\n")
        entries.append({
            "task_id": f"dev_tc_{i:03d}",
            "spec": str(tc_file.relative_to(project_dir)),
            "deps": [], "tier": "standard", "type": "impl",
            "title": tc.get("title", "task"),
        })
    path = bdir / "backlog.json"
    path.write_text(json.dumps(entries))
    return path


class TestBacklogScopeGuard:
    def test_out_of_scope_tc_blocks_with_named_violation(self, tmp_path):
        # L4 core case: improve scoped to billing; planner planned a legacy TC.
        _triage(tmp_path, trigger="u-improve", affected=["billing"])
        backlog = _backlog(tmp_path, [
            {"title": "in scope", "domains": ["billing"]},
            {"title": "re-broadened", "domains": ["legacy"]},
        ])
        r = _run_dev("check_backlog_scope.py", tmp_path,
                     "--backlog", str(backlog), "--workflow-id", WID)
        assert r.returncode == 1
        out = json.loads(r.stdout)
        assert out["status"] == "blocked"
        assert out["scope_domains"] == ["billing"]
        assert len(out["violations"]) == 1
        v = out["violations"][0]
        assert v["task_id"] == "dev_tc_002"
        assert v["out_of_scope_domains"] == ["legacy"]

    def test_all_in_scope_passes(self, tmp_path):
        _triage(tmp_path, trigger="u-improve", affected=["billing", "auth"])
        backlog = _backlog(tmp_path, [
            {"title": "a", "domains": ["billing"]},
            {"title": "b", "domains": ["auth", "billing"]},
        ])
        r = _run_dev("check_backlog_scope.py", tmp_path,
                     "--backlog", str(backlog), "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        assert json.loads(r.stdout)["violations"] == []

    def test_mixed_refs_with_one_in_scope_allowed(self, tmp_path):
        # Out-of-scope mention alongside an in-scope target = context, not work.
        _triage(tmp_path, trigger="u-improve", affected=["billing"])
        backlog = _backlog(tmp_path, [
            {"title": "integration note", "domains": ["billing", "legacy"]},
        ])
        r = _run_dev("check_backlog_scope.py", tmp_path,
                     "--backlog", str(backlog), "--workflow-id", WID)
        assert r.returncode == 0, r.stdout

    def test_tc_without_domain_refs_allowed(self, tmp_path):
        # Front-only / infra TC — cannot attribute → never blocked.
        _triage(tmp_path, trigger="u-improve", affected=["billing"])
        backlog = _backlog(tmp_path, [{"title": "front-only", "domains": []}])
        r = _run_dev("check_backlog_scope.py", tmp_path,
                     "--backlog", str(backlog), "--workflow-id", WID)
        assert r.returncode == 0, r.stdout

    def test_uspec_greenfield_trivially_ok(self, tmp_path):
        _triage(tmp_path, trigger="u-spec", affected=[])
        backlog = _backlog(tmp_path, [{"title": "anything", "domains": ["x", "y"]}])
        r = _run_dev("check_backlog_scope.py", tmp_path,
                     "--backlog", str(backlog), "--workflow-id", WID)
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["scoped"] is False
        assert out["tcs_checked"] == 0

    def test_missing_triage_trivially_ok(self, tmp_path):
        backlog = _backlog(tmp_path, [{"title": "t", "domains": ["legacy"]}])
        r = _run_dev("check_backlog_scope.py", tmp_path,
                     "--backlog", str(backlog), "--workflow-id", WID)
        assert r.returncode == 0
        assert json.loads(r.stdout)["scoped"] is False

    def test_unreadable_backlog_blocks_as_planner_defect(self, tmp_path):
        _triage(tmp_path, trigger="u-improve", affected=["billing"])
        r = _run_dev("check_backlog_scope.py", tmp_path,
                     "--backlog", str(tmp_path / "nope.json"),
                     "--workflow-id", WID)
        assert r.returncode == 1
        assert json.loads(r.stdout)["reason"] == "backlog_unreadable"

    def test_unreadable_tc_file_allowed_but_surfaced(self, tmp_path):
        _triage(tmp_path, trigger="u-improve", affected=["billing"])
        backlog = _backlog(tmp_path, [{"title": "ok", "domains": ["billing"]}])
        entries = json.loads(backlog.read_text())
        entries.append({"task_id": "dev_tc_099", "spec": "backlog/gone.md",
                        "deps": [], "tier": "standard", "type": "impl"})
        backlog.write_text(json.dumps(entries))
        r = _run_dev("check_backlog_scope.py", tmp_path,
                     "--backlog", str(backlog), "--workflow-id", WID)
        assert r.returncode == 0, r.stdout
        assert json.loads(r.stdout)["unreadable"] == ["backlog/gone.md"]
