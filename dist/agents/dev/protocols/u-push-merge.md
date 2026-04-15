## Push and Merge Protocol

The Developer Agent **never pushes**. Push and merge control to `main` is the exclusive responsibility of the Orchestrator-Dev.

### After QA approves a Task Contract

1. Verify that the branch `feat/TC-XX` (or `fix/`, `refactor/`) exists and has local commits
2. Push the branch to the remote:
   ```
   git push -u origin feat/TC-XX
   ```
3. Ask the human if they want to **squash merge** into `main`:
   ```
   Task Contract TC-XX approved by QA.

   Branch: feat/TC-XX
   Commits: [count] local commits

   How would you like to merge into main?

   1. Squash merge — consolidate into a single commit: "feat(TC-XX): [Task Contract title]"
   2. Standard merge — preserve all individual commits
   3. Not now — merge later
   ```
4. After the merge, delete the branch:
   ```
   git branch -d feat/TC-XX
   git push origin --delete feat/TC-XX
   ```

5. Remove the Developer's worktree:
   ```
   git -C "$REPO_ROOT" worktree remove "$REPO_ROOT/.claude/worktrees/TC-XX"
   ```
   If there are uncommitted files in the worktree (unexpected situation), use `--force` and record it in the Orchestrator log.

### Failure handling

- **Push fails (protected branch, permission denied):** inform the human with the error message and await instructions.
- **Merge fails (conflicts):** list the conflicting files and escalate to the human — do not attempt to resolve conflicts automatically.
- **Merge fails (CI/check failed):** inform the human with the check output and await instructions.

### After QA rejects a Task Contract

- **Do not push.** The Developer corrects on the same local branch.
- The cycle repeats until approval.
