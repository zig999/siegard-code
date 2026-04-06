## Cleanup Protocol — `_temp/`

Intermediate files that have already been consumed must be moved to `{SESSIONS_DIR}/{SESSION}/_temp/`. Create the folder if it does not exist. **Never delete — only move.**

**Trigger:** the Orchestrator-Dev executes the cleanup **immediately after each event listed below**, before proceeding to the next decision.

### After Planner completes (`backlog.md` generated)
Move to `_temp/`:
- `{SESSIONS_DIR}/{SESSION}/improve*.md` (if they exist — already consumed by the Planner and incorporated into the backlog)

### After Story completed (QA approved, status `Done`)
Move to `_temp/`:
- Any `{SESSIONS_DIR}/{SESSION}/bug##.md` or `{SESSIONS_DIR}/{SESSION}/improve##.md` that were addressed by the completed Story

> **Do not move `us-XX-delivery.md` and `us-XX-qa.md` at this point.** These files are needed for the Epic integration QA (see epic-integration protocol). They will be moved after Epic completion.

### After Epic completed (integration approved)
Move to `_temp/`:
- Epic design spec (`ui-epic-XX.md` for frontend, `epic-XX-integration-qa.md` for backend)
- All `{SESSIONS_DIR}/{SESSION}/us-XX-delivery.md` from the Epic's Stories
- All `{SESSIONS_DIR}/{SESSION}/us-XX-qa.md` from the Epic's Stories
