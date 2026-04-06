# Push/Merge Protocol

Git operations executed after QA approves a Story.

## Flow

```
git add -> git commit (standardized message) -> git push -> git merge (if configured)
```

## Standardized commit message

Commit messages follow a consistent format that includes:
- Story identifier (us-XX)
- Brief description of what was implemented
- Reference to the Epic

## When merge is executed

The merge step (`git merge`) is only executed if the project has configured merge behavior in CLAUDE.md. Otherwise, only `add`, `commit`, and `push` are performed.

## Trigger

Activated by the Dev orchestrator immediately after QA approval, before cleanup.
