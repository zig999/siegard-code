# Core Concepts

Fundamental structures and terms used throughout the Dev Team Agents system.

## Central structures

### CLAUDE.md

Project-level configuration file. Contains essential fields that agents read to determine behavior:

- `domain:` -- Defines whether the project is `frontend`, `backend`, or `fullstack` (determines pipeline routing)
- `stack:` -- Technology stack used in the project (read by agents, never hardcoded)
- `specs_dir:` -- Path where specifications are stored

The agents adapt their behavior based on what is declared in CLAUDE.md. The system does not impose a specific stack -- it reads the project configuration and adjusts accordingly.

### SPECS_DIR

Root directory for all specifications. Resolved from:
1. `specs_dir:` field in CLAUDE.md *(canonical source)*
2. Command argument *(fallback with warning)*

No default — the command stops if neither is available.

### SESSIONS_DIR

Root directory for development sessions. Resolved from:
1. `sessions_dir:` field in CLAUDE.md *(mandatory)*
2. Command argument *(fallback)*

No default — the command stops if `sessions_dir:` is not configured.

### SESSION

Name of the current working session. Always the last argument in commands. Creates a subdirectory under SESSIONS_DIR.

### {SESSIONS_DIR}/{SESSION}/

Working directory for the current session. Contains the backlog, delivery files, QA reports, and orchestrator logs. Created automatically on first command execution.

### {SPECS_DIR}

Root directory for all approved specifications. Organized by domain for backend and by feature/flow for frontend. Contains `_global/`, `domains/`, `front/`, `_templates/`, `_meta/`, and `_validation/` subdirectories.

### _temp/

Archive directory within `{SESSIONS_DIR}/{SESSION}/`. Temporary artifacts are moved here after they have been consumed (never deleted, always archived).

## Variable resolution priority

When a variable can be resolved from multiple sources, the system follows this priority:

1. **CLAUDE.md field** -- Value declared in the project configuration *(canonical source)*
2. **Command argument** -- Explicit value passed in the slash command *(fallback with warning)*
3. **Stop and request** -- If neither is available, the command halts with a clear error message

## Source repository vs target project

- **Source repository** (`dev-team/`) -- Where agents are developed and maintained. Contains the `dist/` directory with installable artifacts
- **Target project** -- Any project where the agents are installed by copying `dist/.claude/`. Contains its own `CLAUDE.md` with project-specific configuration

Agents are always executed in the context of the target project, never in the source repository.
