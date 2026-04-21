## Cleanup Protocol — `_temp/`

Intermediate files that have already been consumed must be moved to `{SESSIONS_DIR}/{SESSION}/_temp/`. Create the folder if it does not exist. **Never delete — only move.**

**Trigger:** the Orchestrator-Dev executes the cleanup **immediately after each event listed below**, before proceeding to the next decision.

### After Planner completes (`backlog.md` generated)
No intermediate input files to move — `/u-improve` writes the `improve_scope` block directly into `log-orchestrator-dev.md` (no standalone input artifact).

### After Task Contract completed (QA approved, status `Done`)
No per-TC input files to move. The `improve_scope_status: consumed` marker in the session log is the source of truth.

> **Do not move `tc-XX-delivery.md` and `tc-XX-qa.md` at this point.** These files are needed for the Epic integration QA (see epic-integration protocol). They will be moved after Epic completion.

### After Epic completed (integration approved)
Move to `_temp/`:
- Epic design spec (`ui-epic-XX.md` for frontend, `epic-XX-integration-qa.md` for backend)
- All `{SESSIONS_DIR}/{SESSION}/tc-XX-delivery.md` from the Epic's Task Contracts
- All `{SESSIONS_DIR}/{SESSION}/tc-XX-qa.md` from the Epic's Task Contracts

## Ephemeral artifacts — never commit

The following are ephemeral by nature and must **not** be committed to the repository:

| Artifact | Rule |
|----------|------|
| Files under `{RUNTIME_DIR}/` | Gitignored — never stage |
| Raw CI/test runner output | Discard after QA analysis — summarize in qa-report only |
| Agent execution traces or debug logs | Do not persist to repo |

Add to project `.gitignore` on session bootstrap if not already present:
```
docs/runtime/
```
