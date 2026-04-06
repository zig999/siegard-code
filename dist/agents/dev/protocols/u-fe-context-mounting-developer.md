## Context Mounting — Developer

**Agent:** `.claude/agents/dev/u-fe-developer.md`

### Step 0 — Create isolated worktree (mandatory before invoking the Developer)

Execute before building the prompt. Ensures filesystem isolation between parallel Developers without nesting worktrees.

1. Resolve the real repo root, regardless of the Orchestrator's current cwd:
   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   ```

2. Determine the branch prefix based on Story type:
   - New feature -> `feat/US-XX`
   - Bugfix -> `fix/US-XX`
   - Refactoring -> `refactor/US-XX`
   - Enhancement -> `feat/US-XX`

3. Create worktree with absolute path and dedicated branch:
   ```bash
   git -C "$REPO_ROOT" worktree add "$REPO_ROOT/.claude/worktrees/US-XX" -b feat/US-XX
   ```

4. Include in the Developer activation prompt (right after the task instruction):
   ```
   Worktree: {REPO_ROOT}/.claude/worktrees/US-XX
   Branch: feat/US-XX (already created — do not run git checkout -b)
   Work exclusively in this directory.
   ```

> **Why not use `isolation: "worktree"` in the Agent tool:** the Agent tool resolves the worktree path relative to the current agent's cwd, not the repo root. If the Orchestrator is running inside a worktree, this would create nested worktrees. Manual creation with an absolute path eliminates this risk.

### Activation prompt structure

```
Read in parallel:
- CLAUDE.md
- [relevant data — see extraction below]
- .claude/agents/dev/u-fe-developer.md

[task instruction]
```

> **Note:** the skills `u-fe-development` and `u-fe-standards` are embedded in the agent's system prompt (`u-fe-developer.md`). **DO NOT** re-inject them in the activation prompt.

### Context extraction (token reduction)

**Never pass entire files** when only a section is relevant.

Copy into the prompt (do not pass the file):
```
## Target Story (extracted from backlog.md)
[complete US-XX block: title, narrative, acceptance criteria, type, estimate, dependencies, affected components]

## UI Spec — screens for this Story (extracted from ui-epic-XX.md)
[only the "### Screen: [Name]" sections for the target Story]
```

### Design System (selective context)

The design system is a directory with specialized files. **Never pass all files** — select based on Story type.

**Always include:**
```
## Design System — Rules (extracted from {SPECS_DIR}/front/design-system-rules.md)
[full content — this is the compact summary, ~100-150 lines]
```

**Include conditionally, based on the Story's screen type:**

| Screen type / Story | Additional file |
|---|---|
| Any screen with visual styles | `design-system/tokens.md` (colors, spacing, typography) |
| Dashboard, metrics, charts | `design-system/composition.md` (effects, hierarchy, layout) |
| Screen with complex components (DataGrid, MetricCard, Sidebar) | `design-system/components.md` (slot × state catalog) |
| Visual adjustment, accessibility | `design-system/implementation.md` (QA checklist, animations) |

> **Rule:** if the Story type is Visual adjustment, include `implementation.md` + `tokens.md`. If it is New feature with UI, include `tokens.md` + the relevant files for the involved components.

### Spec-first mode (additional context when {SPECS_DIR} exists)

Add to the prompt:
```
## API Contract — consumed endpoints (extracted from {SPECS_DIR}/domains/{domain}/openapi.yaml)
[only the endpoints this screen consumes, with response schemas]

## Error Codes (extracted from {SPECS_DIR}/_global/error-codes.md)
[only the error.code mapped in this Story's screens]
```

> **Traceability rule:** include UC-NN and UI-NN identifiers so the Developer can reference them in tests.

**UI spec naming convention:** `{SESSIONS_DIR}/{SESSION}/ui-epic-XX.md` (e.g., EPIC-01 -> `ui-epic-01.md`).
