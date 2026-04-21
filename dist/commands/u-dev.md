---
description: Starts the Dev Team for a development session. Usage: /u-dev [SPECS_DIR] [SESSIONS_DIR] {SESSION} (e.g., /u-dev docs/specs fix-error-states)
---

## Variable Resolution

Extract from `$ARGUMENTS`:
- **First argument** = `SPECS_DIR` (optional if `specs_dir:` is set in `CLAUDE.md`)
- **Second argument** = `SESSIONS_DIR` (optional if `sessions_dir:` is set in `CLAUDE.md` or if only 2 args)
- **Last argument** = `SESSION` (development session name)

**Resolving `SPECS_DIR` (priority):**
1. `specs_dir:` field in `CLAUDE.md` (project root) -> use *(canonical source — preferred)*
2. First argument containing `/` or `\` -> use as `SPECS_DIR` *(fallback — warn the human: "specs_dir is not configured in CLAUDE.md. Recommended to add it for consistency across sessions.")*
3. None -> **stop** and request: "Configure `specs_dir:` in CLAUDE.md or provide it as an argument: `/u-dev [specs_dir] [session]`"

**Resolving `SESSIONS_DIR` (priority):**
1. `sessions_dir:` field in `CLAUDE.md` (project root) -> use *(canonical source — preferred)*
2. Second argument containing `/` or `\` (only if 3+ args provided) -> use as `SESSIONS_DIR` *(fallback)*
3. None -> **stop** and request: "Configure `sessions_dir:` in CLAUDE.md before continuing."

**Resolving `SESSION`:**
1. Last argument (string without `/` or `\`)
2. If not provided: check for existing sessions in `{SESSIONS_DIR}`:
   - If found, list and ask: "Existing sessions: {list}. Resume one or create new?"
   - If none found, ask: "Provide the session name (e.g., fix-error-states, feature-xyz):"

Create `{SESSIONS_DIR}/{SESSION}/` if it does not exist.

## Mandatory Session Initialization

Immediately after resolving the session directory, before any other action — including before reading `backlog.md` or activating any agent:

1. Create `{SESSIONS_DIR}/{SESSION}/` if it does not exist.

2. Record a start entry in the session log file:
   - For `domain: frontend` or `domain: backend`: use `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md`
   - For `domain: fullstack`: use `{SESSIONS_DIR}/{SESSION}/log-fullstack.md`
   - If the file **does not exist**: create with the header below
   - If the file **already exists**: append to the end (indicates session resumption — do not overwrite)

   ```markdown
   ## [YYYY-MM-DD HH:MM] — Session started
   **Command:** /u-dev {ARGS}
   **SPECS_DIR:** {SPECS_DIR}
   **SESSIONS_DIR:** {SESSIONS_DIR}
   **Session dir:** {SESSIONS_DIR}/{SESSION}
   **Domain:** {domain value}
   **Mode:** [to be detected]
   ```

> **Rule:** no agent may be activated before this log exists on disk. The session log is the minimum traceability guarantee — without it, there is no way to resume or audit what was done.

## Domain Routing

Read the `domain:` field in `CLAUDE.md` (project root). This field determines which orchestrator and agents will be activated.

| `domain:` value | Orchestrator | Protocols |
|------------------|-------------|-----------|
| `frontend` | `.claude/agents/dev/u-fe-orchestrator-core.md` | `.claude/agents/dev/u-fe-orchestrator-protocols.md` |
| `backend` | `.claude/agents/dev/u-be-orchestrator-core.md` | `.claude/agents/dev/u-be-orchestrator-protocols.md` |
| `fullstack` | `.claude/agents/dev/u-fullstack-orchestrator.md` | `.claude/agents/dev/protocols/u-fullstack-coordination.md` |

> If the `domain:` field does not exist in CLAUDE.md, **stop** and request from the human: "Set the field `domain: frontend`, `domain: backend`, or `domain: fullstack` in CLAUDE.md before continuing."
>
> If the `domain:` field exists but contains a value other than `frontend`, `backend`, or `fullstack`, **stop** and request from the human: "Invalid value for `domain:` in CLAUDE.md: `{value}`. Accepted values are: `frontend`, `backend`, or `fullstack`."

## Files to Read

1. `CLAUDE.md` (project root)
2. Orchestrator based on domain (table above)
3. `{SESSIONS_DIR}/{SESSION}/backlog.md` (if exists — session resumption)
4. `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md` (if exists — session resumption)

### Based on mode:
- **Improve:** read `improve_scope` block from `{SESSIONS_DIR}/{SESSION}/log-orchestrator-dev.md`
  - **Halt-await-spec gate:** if `spec_change_status: pending_spec` is observed, do NOT initialize the orchestrator. Emit a structured halt block to the human (see `u-improve-mode.md` § "Halt-await-spec mode"). Do NOT ask A/B/C-style questions — the pending state is owned by the /u-spec pipeline. Stop immediately.
  - **Failed-spec gate:** if `spec_change_status: failed` is observed, halt with structured `spec_pipeline_failed` and surface `failure_reason` from the latest `spec_pipeline_return` block. Stop immediately.

### Spec Detection
If `{SPECS_DIR}/` exists:

1. Check if any domains have `approved` status in `.spec.md`:
   - **If yes:** inform the human and activate Spec-first mode:
     ```
     Approved specs detected in {SPECS_DIR}/. Spec-first mode activated.
     ```

2. Check if domains only have `draft` status (e.g., generated by `/u-reverse-spec`):
   - **If yes:** inform the human that specs exist but are not approved:
     ```
     Draft specs detected in {SPECS_DIR}/ (possibly generated by /u-reverse-spec).
     Specs need to be reviewed and approved before being consumed by Dev.

     Run: /u-spec [SPECS_DIR] (to review and approve the specs)
     ```
   - **Do not activate Spec-first mode** with draft specs.

### No Input Available
If `{SPECS_DIR}`, improve_scope block in log, and `backlog.md` do not exist:

1. Check if the project has existing source code (package.json, requirements.txt, src/, etc.) but no `{SPECS_DIR}`:
   - **If yes:** suggest reverse engineering:
     ```
     Project with existing code detected, but no spec documentation.

     Recommended:
       /u-reverse-spec [SPECS_DIR] — generate specs from existing code
       /u-spec [SPECS_DIR] — write specs manually from scratch
     ```

2. Otherwise, guide:
   - `/u-spec [SPECS_DIR]` — generate technical specifications
   - `/u-reverse-spec [SPECS_DIR]` — generate specs from existing code
   - `/u-improve [SPECS_DIR] {SESSION}` — register any intentional change (bug fix, tweak, or enhancement) in the session

## Pre-execution Estimate

Before initializing, present an estimate to the human:

```
## Estimate — /u-dev [SPECS_DIR] {SESSION}

Mode: {detected mode} | Domain: {frontend|backend}
Input: {improve_scope: N TCs estimated | {SPECS_DIR}: N domains}
Source: {improve_scope (handoff_manifest_id: HANDOFF-...) | direct | spec-first}

| Stage | Agents | Estimated Tokens | Estimated Time |
|-------|--------|-----------------|----------------|
| Planner | 1 | ~5K | 2-3 min |
| UI Agent | 1 (if FE or fullstack) | ~4K per Epic | 2-3 min |
| Developer | 1 per Task Contract | ~6K per Task Contract | 5-10 min |
| QA | 1 per Task Contract | ~4K per Task Contract | 3-5 min |
| E2E Integration | 1 (if fullstack) | ~3K | 2-4 min |
| **Total** | — | **~{N}K** | **~{N} min** |

Note: Lean Improve mode skips UI Agent (~30% reduction).
Note: Parallel Task Contracts (max 3) reduce total time.
Note: Fullstack mode runs BE phase then FE phase sequentially — total time is additive.

Proceed? [Y / N]
```

**Simplified calculation:**
- Per Task Contract (full): ~14K tokens, ~10-18 min
- Per Task Contract (lean improve): ~10K tokens, ~8-13 min
- Planner overhead: ~5K tokens (once)
- UI Agent overhead: ~4K tokens per Epic (once, if frontend or fullstack)
- E2E Integration overhead: ~3K tokens (once, if fullstack)

---

## Instruction to the Orchestrator

Pass the following variables to the Orchestrator-Dev:
- `SPECS_DIR` = directory for specs and shared artifacts
- `SESSIONS_DIR` = parent directory for development sessions
- the session directory (`{SESSIONS_DIR}/{SESSION}/`) — session directory (backlog, logs, deliverables)
- `SESSION` = session name

The Orchestrator reads specs from `{SPECS_DIR}/` and writes dev artifacts to `{SESSIONS_DIR}/{SESSION}/`.

Use the Orchestrator-Dev Core instructions to coordinate the development cycle.
### Mode Protocols (load based on detection)
- If `improve_scope` block detected in session log: load `.claude/agents/dev/protocols/u-improve-mode.md` — covers bug fixes, tweaks, and enhancements
- Other protocols: load on demand per the domain orchestrator-protocols index
