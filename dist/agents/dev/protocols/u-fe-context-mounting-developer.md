## Context Mounting — Developer

**Agent:** `.claude/agents/dev/u-fe-developer.md`

### Step 0 — Create isolated worktree (mandatory before invoking the Developer)

Execute before building the prompt. Ensures filesystem isolation between parallel Developers without nesting worktrees.

1. Resolve the real repo root, regardless of the Orchestrator's current cwd:
   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   ```

2. Determine the branch prefix based on Task Contract type:
   - New feature -> `feat/TC-XX`
   - Bugfix -> `fix/TC-XX`
   - Refactoring -> `refactor/TC-XX`
   - Enhancement -> `feat/TC-XX`

3. Create worktree with absolute path and dedicated branch:
   ```bash
   git -C "$REPO_ROOT" worktree add "$REPO_ROOT/.claude/worktrees/TC-XX" -b feat/TC-XX
   ```

4. Include in the Developer activation prompt (right after the task instruction):
   ```
   Worktree: {REPO_ROOT}/.claude/worktrees/TC-XX
   Branch: feat/TC-XX (already created — do not run git checkout -b)
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
## Target Task Contract (extracted from backlog.md)
[complete TC-XX block: title, acceptance criteria, type, estimate, dependencies, affected components]

## UI Spec — screens for this Task Contract (extracted from ui-epic-XX.md)
[only the "### Screen: [Name]" sections for the target Task Contract]
```

### Design System (selective context)

The design system is a directory with specialized files. **Never pass all files** — select based on Task Contract type.

**Before injecting any design system file, extract from `CLAUDE.md`:**

| Field | Location in CLAUDE.md | Used for |
|---|---|---|
| `design_system.path` | header | Resolves the path to `tokens.md`, `components.md`, etc. |
| `design_system.token_prefix` | header | CSS custom property prefix for design tokens (e.g. `"--color-"`) |
| `design_system.component_library` | header | Reference exact component names in the prompt |
| `design_system.enforce_tokens` | header | If `false`, downgrade token violations from BUG to Warning in the prompt |
| `design_system.motion_policy` | header | If `strict`, explicitly instruct the Developer that `--duration-*` and `--ease-*` tokens are required on all transitions; if `permissive`, only `transition: all` is banned |
| `design_system.color_mode` | header | Pass to Developer so conditional dark/light logic is applied correctly |

> `design_system` block is optional. If absent or partially filled, apply the canonical defaults defined in the `CLAUDE.md` template comment block: `path = {specs_dir}/front/design-system/`, `token_prefix = "--color-"`, `color_mode = both`, `component_library = none`, `enforce_tokens = true`, `motion_policy = strict`.

**Always include:**
```
## Design System — Rules (extracted from {SPECS_DIR}/front/design-system-rules.md)
[full content — this is the compact summary, ~100-150 lines]

## Design System — Config (extracted from CLAUDE.md design_system block)
component_library: {value}
enforce_tokens: {value}
motion_policy: {value}
color_mode: {value}
```

**Include conditionally, based on the Task Contract's screen type:**

| Screen type / Task Contract | Additional file |
|---|---|
| Any screen with visual styles | `design-system/tokens.md` (colors, spacing, typography) |
| Dashboard, metrics, charts | `design-system/composition.md` (effects, hierarchy, layout) |
| Screen with complex components (DataGrid, MetricCard, Sidebar) | `design-system/components.md` (slot × state catalog) |
| Visual adjustment, accessibility | `design-system/implementation.md` (QA checklist, animations) |

> **Rule:** if the Task Contract type is Visual adjustment, include `implementation.md` + `tokens.md`. If it is New feature with UI, include `tokens.md` + the relevant files for the involved components.

### Spec-first mode (additional context when {SPECS_DIR} exists)

> **If the Task Contract's `execution_contract.input_references` is populated:** use it as the primary guide for extraction — map each listed reference to its section and inject it. Only fall back to the default inference rules below if `input_references` is empty or absent.

Add to the prompt:
```
## Feature Spec (from {SPECS_DIR}/front/features/{feature}.feature.spec.md)
[§1 Consumed Endpoints — operationIds this feature is authorized to call; do not call others]
[§4 Response transforms — if the sub-section exists, include it; it defines mandatory transformations the Developer must implement]
[§4 Composed models — if the sub-section exists, include it]
[§7 Component adapters — if the sub-section exists, include it; it defines prop-level mapping from API response to component Props Contract]
[§9 BDD Scenarios — feature invariants; your implementation must not break any of them]

## API Contract — consumed endpoints (extracted from {SPECS_DIR}/domains/{domain}/openapi.yaml)
[only the endpoints this Task Contract consumes, with response schemas]

## Error Codes (extracted from {SPECS_DIR}/_global/error-codes.md)
[only the error.code values mapped in this Task Contract's features]

## Component Specs (mandatory if this Task Contract uses components from src/components/)
[for each component listed in §7 of the relevant feature.spec.md:]
[§2 Props Contract + §3 Component States + §4 Events Emitted + §5 Variants
 from {SPECS_DIR}/front/components/{name}.component.spec.md]
[§6 Do/Don't must be read directly by the Developer from the full file — do not summarize]

## Active Decisions (filtered — from {SPECS_DIR}/decisions.md)
[only DEC-NN entries with Status: Active that affect this Task Contract's route or components]
```

> **Traceability rule:** include UC-NN, UI-NN, and FEAT-NN identifiers so the Developer can reference them in tests and the delivery file.

> **Contract rules:** (1) §9 BDD Scenarios are feature invariants — a Task Contract that breaks any §9 scenario will be rejected by QA regardless of Task Contract-level AC status. (2) component.spec.md §2 Props Contract is binding — do not add or remove props without opening a spec CR.


**UI spec naming convention:** `{SESSIONS_DIR}/{SESSION}/ui-epic-XX.md` (e.g., EPIC-01 -> `ui-epic-01.md`).
