## Context Mounting — Developer (Backend)

**Agent:** `.claude/agents/dev/u-be-developer.md`

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
- .claude/agents/dev/u-be-developer.md

[task instruction]
```

> **Note:** the skills `u-be-development` and `u-be-standards` are embedded in the agent's system prompt (`u-be-developer.md`). **DO NOT** re-inject them in the activation prompt.

### Context extraction (token reduction)

**Never pass entire files** when only a section is relevant.

Copy into the prompt (do not pass the file):
```
## Target Story (extracted from backlog.md)
[complete US-XX block: title, narrative (As/I want/So that), ALL acceptance criteria, type, estimate, dependencies, affected modules]
```

### Spec-first mode (when {SPECS_DIR} exists with approved status)

Extract from the spec package the sections relevant to this Story:

```
## API Contract — endpoints for this Story (extracted from {SPECS_DIR}/domains/{domain}/openapi.yaml)
[only the paths/operationIds whose functionality corresponds to this Story]
[include schemas referenced by these endpoints]

## Back Spec — rules and model (extracted from {SPECS_DIR}/domains/{domain}/back/{domain}.back.md)
[BRs referenced by this Story's UCs — e.g., BR-01, BR-02]
[relevant STs — state machine if the Story changes state]
[relevant EVs — events dispatched by this Story's actions]
[Data model — tables touched by this Story]

## Error Codes (extracted from {SPECS_DIR}/_global/error-codes.md)
[only the error.code used by this Story's endpoints]
```

> **Traceability rule:** when mounting context, include spec identifiers (UC-NN, BR-NN) so the Developer can reference them in tests and comments.

### Feature/Improve mode (when {SPECS_DIR} does not exist)

Keep the previous flow — without API Contract or Back Spec sections.

> **When to omit API Contract:** if the Story type is Refactoring (no contract change) or Bugfix (no API impact), do not include the spec sections.
