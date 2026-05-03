# Tech Debt Protocol

Registers technical debt identified during development or epic integration.

## When triggered

- During development: Developer identifies a shortcut or compromise
- During epic integration: QA finds a pattern that works but is suboptimal

## What is recorded

Each tech debt entry in `tech-debt.md` includes:
- **Description** -- What the debt is
- **Reason** -- Why the shortcut was taken
- **Impact** -- What happens if it's not addressed
- **Resolution suggestion** -- How it could be fixed

## Output

`{SESSIONS_DIR}/{SESSION}/tech-debt.md` -- Permanent file that accumulates tech debt entries across the session. Not archived.
