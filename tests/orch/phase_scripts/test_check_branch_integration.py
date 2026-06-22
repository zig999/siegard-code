"""
SIEGARD-04/05/06 — git-state exit criteria / preconditions.

Each checker is invoked as a subprocess (via run_check) against a throwaway git
repo built in tmp_path. The checkers read git state only (no orchestration log),
so tmp_path is used directly instead of the tmp_orch fixture.

  - check_all_branches_integrated.py  (dev exit / SIEGARD-04)
  - check_sdd_artifacts_committed.py   (sdd exit / SIEGARD-05)
  - check_qa_on_integrated_main.py     (review entry / SIEGARD-06)
"""
import subprocess
from pathlib import Path

import pytest

from .conftest import SKILLS_DIR, run_check  # noqa: F401

DEV_INTEGRATED = SKILLS_DIR / "phase-dev-rules" / "scripts" / "check_all_branches_integrated.py"
SDD_COMMITTED = SKILLS_DIR / "phase-sdd-rules" / "scripts" / "check_sdd_artifacts_committed.py"
QA_ON_MAIN = SKILLS_DIR / "phase-review-rules" / "scripts" / "check_qa_on_integrated_main.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo on `main` with one commit and .orch/ gitignored."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitignore").write_text(".orch/\n")
    (tmp_path / "README.md").write_text("init\n")
    _git(tmp_path, "add", ".gitignore", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "init")
    _git(tmp_path, "branch", "-M", "main")
    return tmp_path


def _make_tc_branch(repo: Path, name: str, fname: str) -> None:
    """Create a TC branch with one commit, then return to main (not merged)."""
    _git(repo, "checkout", "-q", "-b", name)
    (repo / fname).write_text("work\n")
    _git(repo, "add", fname)
    _git(repo, "commit", "-q", "-m", f"{name} work")
    _git(repo, "checkout", "-q", "main")


# ── SIEGARD-04 — all_branches_integrated_to_main ────────────────────────────

class TestAllBranchesIntegrated:
    def test_clean_main_no_branches_is_met(self, repo):
        out = run_check(DEV_INTEGRATED, repo)
        assert out["status"] == "ok" and out["met"] is True

    def test_merged_tc_branch_is_met(self, repo):
        _make_tc_branch(repo, "feat/TC-01", "a.txt")
        _git(repo, "merge", "-q", "--no-ff", "-m", "integrate TC-01", "feat/TC-01")
        out = run_check(DEV_INTEGRATED, repo)
        assert out["status"] == "ok", out
        assert out["evidence"]["unmerged_tc_branches"] == []

    def test_unmerged_tc_branch_blocks(self, repo):
        _make_tc_branch(repo, "feat/TC-02", "b.txt")
        out = run_check(DEV_INTEGRATED, repo)
        assert out["status"] == "blocked"
        assert "feat/TC-02" in out["evidence"]["unmerged_tc_branches"]

    def test_off_main_blocks(self, repo):
        _git(repo, "checkout", "-q", "-b", "feat/TC-03")
        out = run_check(DEV_INTEGRATED, repo)
        assert out["status"] == "blocked"
        assert out["evidence"]["on_integration_branch"] is False

    def test_dirty_tree_blocks(self, repo):
        (repo / "dirty.txt").write_text("uncommitted\n")
        out = run_check(DEV_INTEGRATED, repo)
        assert out["status"] == "blocked"
        assert out["evidence"]["working_tree_clean"] is False

    def test_not_a_git_repo_errors(self, tmp_path):
        out = run_check(DEV_INTEGRATED, tmp_path)
        assert out["status"] == "error" and out["reason"] == "not_a_git_repo"


# ── SIEGARD-05 — sdd_artifacts_committed ────────────────────────────────────

def _write_manifest(repo: Path, artifact_rel: str) -> None:
    specs = repo / "specs"
    specs.mkdir(exist_ok=True)
    (specs / "handoff-manifest.yaml").write_text(
        "backend_package:\n"
        f"  - path: {artifact_rel}\n"
        "    artifact: openapi\n"
        "    sha256: deadbeef\n"
    )


class TestSddArtifactsCommitted:
    def test_committed_artifact_is_met(self, repo):
        (repo / "specs").mkdir(exist_ok=True)
        (repo / "specs" / "openapi.yaml").write_text("openapi: 3.0.0\n")
        _write_manifest(repo, "specs/openapi.yaml")
        _git(repo, "add", "specs/openapi.yaml", "specs/handoff-manifest.yaml")
        _git(repo, "commit", "-q", "-m", "spec: artifacts")
        out = run_check(SDD_COMMITTED, repo)
        assert out["status"] == "ok", out
        assert out["evidence"]["committed"] == 1

    def test_untracked_artifact_blocks(self, repo):
        (repo / "specs").mkdir(exist_ok=True)
        (repo / "specs" / "openapi.yaml").write_text("openapi: 3.0.0\n")
        _write_manifest(repo, "specs/openapi.yaml")
        _git(repo, "add", "specs/handoff-manifest.yaml")  # manifest committed, artifact NOT
        _git(repo, "commit", "-q", "-m", "spec: manifest only")
        out = run_check(SDD_COMMITTED, repo)
        assert out["status"] == "blocked"
        assert "specs/openapi.yaml" in out["evidence"]["untracked"]

    def test_uncommitted_change_blocks(self, repo):
        (repo / "specs").mkdir(exist_ok=True)
        (repo / "specs" / "openapi.yaml").write_text("openapi: 3.0.0\n")
        _write_manifest(repo, "specs/openapi.yaml")
        _git(repo, "add", "specs/openapi.yaml", "specs/handoff-manifest.yaml")
        _git(repo, "commit", "-q", "-m", "spec: artifacts")
        (repo / "specs" / "openapi.yaml").write_text("openapi: 3.0.1\n")  # modify after commit
        out = run_check(SDD_COMMITTED, repo)
        assert out["status"] == "blocked"
        assert "specs/openapi.yaml" in out["evidence"]["uncommitted_changes"]

    def test_missing_manifest_blocks(self, repo):
        out = run_check(SDD_COMMITTED, repo)
        assert out["status"] == "blocked"
        assert out["evidence"]["reason"] == "manifest_missing"


# ── SIEGARD-06 — qa_runs_on_integrated_main ─────────────────────────────────

class TestQaOnIntegratedMain:
    def test_clean_main_is_met(self, repo):
        out = run_check(QA_ON_MAIN, repo)
        assert out["status"] == "ok" and out["met"] is True

    def test_off_main_blocks(self, repo):
        _git(repo, "checkout", "-q", "-b", "feat/TC-08")
        out = run_check(QA_ON_MAIN, repo)
        assert out["status"] == "blocked"
        assert out["evidence"]["on_integration_branch"] is False

    def test_unmerged_tc_branch_blocks(self, repo):
        _make_tc_branch(repo, "feat/TC-09", "c.txt")
        out = run_check(QA_ON_MAIN, repo)
        assert out["status"] == "blocked"
        assert "feat/TC-09" in out["evidence"]["unmerged_tc_branches"]
