"""R10 — `/u-spec` entry guard.

`/u-spec` builds EVERY domain by design, and `scope.py` returns `scoped: false`
for the `u-spec` trigger, so `orchestrator-sdd` dispatches the full back leg for
every domain it scans. Correct on an empty repository; on a populated one an
addition silently becomes a full re-spec that outruns the per-session subagent
spawn budget and dies mid-pipeline with no terminal event.

Nothing distinguished the two cases before this guard.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import get_dist_dir

dist = get_dist_dir()
SCRIPT = dist / "skills" / "phase-sdd-rules" / "scripts" / "check_spec_entry.py"
COMMAND = dist / "commands" / "u-spec.md"


def _run(specs_dir, project_dir=None):
    args = [sys.executable, str(SCRIPT), "--specs-dir", str(specs_dir)]
    if project_dir is not None:
        args += ["--project-dir", str(project_dir)]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
    payload = json.loads(proc.stdout) if proc.stdout.strip() else json.loads(proc.stderr)
    return proc.returncode, payload


def _domain(specs_dir: Path, slug: str, kind="openapi"):
    d = specs_dir / "domains" / slug
    d.mkdir(parents=True, exist_ok=True)
    if kind == "openapi":
        (d / "openapi.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
    elif kind == "spec":
        (d / f"{slug}.spec.md").write_text("# spec\n", encoding="utf-8")
    return d


class TestEntryClassification:
    def test_missing_specs_dir_is_greenfield(self, tmp_path):
        rc, out = _run(tmp_path / "nope")
        assert rc == 0 and out["entry"] == "greenfield"
        assert out["domain_count"] == 0

    def test_empty_domains_dir_is_greenfield(self, tmp_path):
        (tmp_path / "domains").mkdir(parents=True)
        rc, out = _run(tmp_path)
        assert rc == 0 and out["entry"] == "greenfield"

    def test_scaffolded_domain_without_spec_is_greenfield(self, tmp_path):
        """An empty directory is not a spec — it must not block the entry point."""
        (tmp_path / "domains" / "billing").mkdir(parents=True)
        rc, out = _run(tmp_path)
        assert rc == 0 and out["entry"] == "greenfield"
        assert out["domains"] == []

    def test_openapi_marks_non_greenfield(self, tmp_path):
        _domain(tmp_path, "billing", "openapi")
        rc, out = _run(tmp_path)
        assert rc == 3 and out["entry"] == "non_greenfield"
        assert out["domains"] == ["billing"]

    def test_spec_md_marks_non_greenfield(self, tmp_path):
        _domain(tmp_path, "auth", "spec")
        rc, out = _run(tmp_path)
        assert rc == 3 and out["domains"] == ["auth"]

    def test_domains_are_sorted_and_complete(self, tmp_path):
        for slug in ("pso", "assyst", "fsm"):
            _domain(tmp_path, slug)
        rc, out = _run(tmp_path)
        assert rc == 3
        assert out["domains"] == ["assyst", "fsm", "pso"]
        assert out["domain_count"] == 3

    def test_relative_specs_dir_resolves_against_project_dir(self, tmp_path):
        _domain(tmp_path / "docs" / "specs", "billing")
        rc, out = _run("docs/specs", project_dir=tmp_path)
        assert rc == 3 and out["domains"] == ["billing"]


class TestCostProjection:
    def test_projection_scales_with_domain_count(self, tmp_path):
        for slug in ("a", "b", "c"):
            _domain(tmp_path, slug)
        _, out = _run(tmp_path)
        # 3 domains x 4 back-leg stages + triage + compliance
        assert out["projected"]["workers"] == 14
        assert out["projected"]["wall_clock_minutes"] == 14 * 6

    def test_greenfield_projects_only_the_global_workers(self, tmp_path):
        _, out = _run(tmp_path)
        assert out["projected"]["workers"] == 2

    def test_seven_domain_repo_projects_the_measured_blowup(self, tmp_path):
        """The production case: 7 domains -> 30 workers, ~3 h, spawn budget dead."""
        for slug in ("assyst", "diag-composite", "fsm", "mwo-catalog",
                     "preventive-scan", "pso", "troubleshooting-engine"):
            _domain(tmp_path, slug)
        rc, out = _run(tmp_path)
        assert rc == 3
        assert out["projected"]["workers"] == 30
        assert out["projected"]["wall_clock_minutes"] == 180


class TestExitCodeIsTheContract:
    """The command must branch on the exit code, never on prose (R01's lesson)."""

    def test_blocking_exit_code_is_three(self, tmp_path):
        _domain(tmp_path, "billing")
        rc, _ = _run(tmp_path)
        assert rc == 3, "3 distinguishes 'blocked by policy' from 1 ('script broke')"

    @pytest.mark.parametrize("token", [
        "check_spec_entry.py",
        "E_USE_IMPROVE",
        "--respec-all",
        "exit 3",
        "exit 0",
    ])
    def test_command_documents_the_guard(self, token):
        assert token in COMMAND.read_text(encoding="utf-8"), (
            f"/u-spec must wire the entry guard: '{token}' missing"
        )

    def test_command_reads_exit_code_not_json_prose(self):
        text = COMMAND.read_text(encoding="utf-8")
        assert "Act on the **exit code**" in text
