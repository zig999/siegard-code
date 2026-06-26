"""
SIEGARD-08 — gc_worktrees.py: GC integrated per-TC worktrees/branches.

Merged worktrees/branches are reclaimed; unmerged ones are kept (never destroy
unintegrated work). Dry-run by default; --confirm executes.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "scripts" / "gc_worktrees.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True)


def _run_gc(repo: Path, *flags: str) -> tuple[dict, int]:
    env = {**os.environ, "ORCH_PROJECT_DIR": str(repo)}
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", *flags],
        cwd=str(repo), capture_output=True, text=True, env=env,
    )
    out = (p.stdout or p.stderr).strip()
    return json.loads(out), p.returncode


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitignore").write_text(".orch/\n")
    (tmp_path / "README.md").write_text("init\n")
    _git(tmp_path, "add", ".gitignore", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "init")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / ".orch" / "worktrees").mkdir(parents=True)
    return tmp_path


def _add_worktree(repo: Path, task_id: str, merge: bool) -> Path:
    wt = repo / ".orch" / "worktrees" / task_id
    _git(repo, "worktree", "add", "-q", "-b", f"feat/TC-{task_id}", str(wt), "main")
    (wt / f"{task_id}.txt").write_text("work\n")
    _git(wt, "add", f"{task_id}.txt")
    _git(wt, "commit", "-q", "-m", f"{task_id} work")
    if merge:
        _git(repo, "merge", "-q", "--no-ff", "-m", f"integrate {task_id}", f"feat/TC-{task_id}")
    return wt


def test_dryrun_lists_merged_worktree_as_candidate(repo):
    _add_worktree(repo, "T1", merge=True)
    out, rc = _run_gc(repo)
    assert rc == 2  # candidates pending, not confirmed
    assert out["dry_run"] is True
    assert any("T1" in w["path"] for w in out["remove_worktrees"])
    assert "feat/TC-T1" in out["delete_branches"]


def test_confirm_removes_merged_worktree_and_branch(repo):
    wt = _add_worktree(repo, "T1", merge=True)
    out, rc = _run_gc(repo, "--confirm")
    assert rc == 0 and out["status"] == "ok"
    assert not wt.exists(), "merged worktree dir should be removed"
    # branch deleted
    branches = subprocess.run(["git", "branch"], cwd=str(repo), capture_output=True, text=True).stdout
    assert "feat/TC-T1" not in branches


def test_unmerged_worktree_is_kept(repo):
    wt = _add_worktree(repo, "T2", merge=False)
    out, rc = _run_gc(repo, "--confirm")
    assert rc == 0
    assert wt.exists(), "unmerged worktree must NOT be destroyed"
    assert any("T2" in k["path"] for k in out["kept_unmerged"])
    branches = subprocess.run(["git", "branch"], cwd=str(repo), capture_output=True, text=True).stdout
    assert "feat/TC-T2" in branches


def test_nothing_to_do_is_clean_exit(repo):
    out, rc = _run_gc(repo)
    assert rc == 0 and out["candidates"] == 0


def test_not_a_git_repo_errors(tmp_path):
    out, rc = _run_gc(tmp_path)
    assert rc == 4 and out["reason"] == "not_a_git_repo"
