# Project Configuration

How to configure the target project's `CLAUDE.md` so the agents operate correctly.

## Mandatory fields

| Field | Description | Example |
|-------|-------------|---------|
| `domain:` | `frontend`, `backend`, or `fullstack` -- determines pipeline routing | `domain: backend` |
| `stack:` | Technology stack used in the project | `stack: Node.js, Express, PostgreSQL` |
| `specs_dir:` | Path to the specifications directory | `specs_dir: docs/specs` |
| `sessions_dir:` | Path to the sessions directory | `sessions_dir: docs/sessions` |

## Recommended fields

| Field | Description | Example |
|-------|-------------|---------|
| `personas:` | Actors that interact with the system | `personas: Admin, End user` |
| `conventions:` | Project coding conventions | `conventions: camelCase, feature-based` |
| `architecture:` | High-level architecture description | `architecture: Monolith, REST API` |

## Example configuration -- Backend

```markdown
## Project

domain: backend
stack: [your backend stack here]
specs_dir: docs/specs
sessions_dir: docs/sessions

## Conventions
- [your naming conventions]
- [your architecture patterns]
- [your error handling approach]
```

## Example configuration -- Frontend

```markdown
## Project

domain: frontend
stack: [your frontend stack here]
specs_dir: docs/specs
sessions_dir: docs/sessions

## Conventions
- [your component patterns]
- [your state management approach]
- [your styling approach]
```

## How agents use CLAUDE.md

- **Orchestrator** reads `domain:` to select the correct pipeline (frontend or backend agents)
- **Planner** reads `stack:` and `conventions:` to generate appropriate Task Contracts
- **Developer** reads `stack:` and `conventions:` to write code following project patterns
- **QA** reads `stack:` to select the appropriate testing strategy
- **Reverse Spec Analyzer** reads `stack:` or auto-detects it from source code

The agents do not hardcode any specific technology. They read the project configuration and adapt their behavior accordingly.
