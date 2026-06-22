#!/usr/bin/env python3
"""
gc_worktrees.py — Garbage-collect integrated per-TC worktrees and branches (SIEGARD-08).

The dev phase creates one worktree + branch per Task Contract under
`.orch/worktrees/<task_id>` (feat/TC-*, fix/TC-*, refactor/TC-*). Step 5.6
integrates and removes them on the success path; this script reclaims any that
survived an abnormal exit (crash, abort, non-retryable failure) so worktrees and
branches do not accumulate across runs.

Safety: only **merged** worktrees/branches are removed. A worktree whose branch
is NOT merged into the integration branch holds un-integrated work and is KEPT
(surfaced under `kept_unmerged`) — GC never destroys unintegrated commits.

Dry-run by default; pass --confirm to actually remove. Mirrors purge.py's gate.

Usage:
    python3 .claude/scripts/gc_worktrees.py [--json]            # dry-run
    python3 .claude/scripts/gc_worktrees.py --confirm [--json]  # execute

Environment:
    ORCH_PROJECT_DIR   — project root / git repo (default: ".")
    ORCH_MAIN_BRANCH   — integration branch (default: "main"; --main-branch overrides)

Exit codes:
    0  Success (removed, or dry-run with nothing to do).
    2  Dry-run completed with candidates pending (--confirm not provided).
    3  Missing/invalid argument or precondition failure (active workers).
    4  Error (not a git repo, git failure).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_PROJECT_DIR = Path(os.environ.get("ORCH_PROJECT_DIR", "."))
_TC_BRANCH_RE = re.compile(r"^(?:feat|fix|refactor)/TC[-/]", re.IGNORECASE)


def _git(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=str(_PROJECT_DIR), capture_output=True, text=True
    )
    return proc.returncode, proc.stdout.strip()


def _is_git_repo() -> bool:
    rc, out = _git(["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out == "true"


def _active_workers() -> int:
    """Best-effort: number of tasks in `claimed` status. Running GC while workers
    append corrupts the log (same gate as purge.py). 0 if no log / orch_core."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
        from orch_core import TaskStatus, reduce_all  # noqa: E402
        state = reduce_all()
        return sum(1 for t in state.tasks.values() if t.status == TaskStatus.CLAIMED)
    except Exception:  # noqa: BLE001  (no log / not initialized → treat as none)
        return 0


def _merged_branches(main: str) -> set[str]:
    rc, out = _git(["branch", "--merged", main, "--format=%(refname:short)"])
    if rc != 0:
        return set()
    return {b.strip() for b in out.splitlines() if b.strip()}


def _worktrees(main_root: str) -> list[dict]:
    """Returns [{path, branch}] for every worktree other than the main one."""
    rc, out = _git(["worktree", "list", "--porcelain"])
    if rc != 0:
        return []
    entries: list[dict] = []
    cur: dict = {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur:
                entries.append(cur)
            cur = {"path": line[len("worktree "):].strip(), "branch": None}
        elif line.startswith("branch "):
            ref = line[len("branch "):].strip()
            cur["branch"] = ref.replace("refs/heads/", "")
    if cur:
        entries.append(cur)
    return [e for e in entries if e["path"] != main_root]


def plan(main: str) -> dict:
    main_root = _git(["rev-parse", "--show-toplevel"])[1]
    merged = _merged_branches(main)

    # Only per-TC worktrees are GC targets. A merged TC worktree is removed; an
    # unmerged one is KEPT (holds un-integrated work). Non-TC worktrees are left
    # untouched — not this tool's concern.
    remove_worktrees: list[dict] = []
    kept_unmerged: list[dict] = []
    for wt in _worktrees(main_root):
        branch = wt.get("branch")
        if not (branch and _TC_BRANCH_RE.match(branch)):
            continue
        (remove_worktrees if branch in merged else kept_unmerged).append(wt)

    # Every merged TC branch is deletable: a kept (unmerged) worktree's branch is
    # by definition not in `merged`, and removed worktrees free their branch
    # before deletion (execute() removes worktrees first, then prunes).
    delete_branches = [b for b in merged if _TC_BRANCH_RE.match(b) and b != main]
    return {
        "remove_worktrees": remove_worktrees,
        "delete_branches": sorted(delete_branches),
        "kept_unmerged": kept_unmerged,
    }


def execute(p: dict) -> None:
    for wt in p["remove_worktrees"]:
        _git(["worktree", "remove", "--force", wt["path"]])
    _git(["worktree", "prune"])
    for b in p["delete_branches"]:
        _git(["branch", "-D", b])


def main() -> int:
    parser = argparse.ArgumentParser(description="GC integrated per-TC worktrees/branches.")
    parser.add_argument("--confirm", action="store_true", help="Perform removals (default: dry-run).")
    parser.add_argument("--main-branch", default=os.environ.get("ORCH_MAIN_BRANCH", "main"))
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if not _is_git_repo():
        out = {"status": "error", "reason": "not_a_git_repo", "detail": str(_PROJECT_DIR)}
        print(json.dumps(out) if args.as_json else f"error: {out['detail']} is not a git repo", file=sys.stderr)
        return 4

    active = _active_workers()
    if active:
        out = {"status": "error", "reason": "active_workers", "claimed": active}
        print(json.dumps(out) if args.as_json else f"error: {active} active worker(s) — refusing to GC", file=sys.stderr)
        return 3

    p = plan(args.main_branch)
    candidates = len(p["remove_worktrees"]) + len(p["delete_branches"])

    if not args.confirm:
        result = {"status": "dry_run", "dry_run": True, **p, "candidates": candidates}
        print(json.dumps(result) if args.as_json else json.dumps(result, indent=2))
        return 0 if candidates == 0 else 2

    execute(p)
    result = {
        "status": "ok",
        "dry_run": False,
        "removed_worktrees": [w["path"] for w in p["remove_worktrees"]],
        "deleted_branches": p["delete_branches"],
        "kept_unmerged": p["kept_unmerged"],
    }
    print(json.dumps(result) if args.as_json else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "reason": "internal_error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(4)
