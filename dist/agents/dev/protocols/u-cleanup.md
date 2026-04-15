## Cleanup Protocol — `_temp/`

Intermediate files that have already been consumed must be moved to `{SESSIONS_DIR}/{SESSION}/_temp/`. Create the folder if it does not exist. **Never delete — only move.**

**Trigger:** the Orchestrator-Dev executes the cleanup **immediately after each event listed below**, before proceeding to the next decision.

### After Planner completes (`backlog.md` generated)
Move to `_temp/`:
- Any `{SESSIONS_DIR}/{SESSION}/bug##.md` files already consumed by the Planner

### After Task Contract completed (QA approved, status `Done`)
Move to `_temp/`:
- Any `{SESSIONS_DIR}/{SESSION}/bug##.md` that were addressed by the completed Task Contract

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
