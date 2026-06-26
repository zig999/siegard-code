---
description: Scans documentation files for historical noise (incident narratives, version comparisons, decision logs, deprecated sections) and removes them, leaving only current-state content. Usage: /u-doc-cleanup [report|clean] [path ...]
---

Read the following file:
1. .claude/skills/u-doc-cleanup/SKILL.md

## Argument resolution

Extract from `$ARGUMENTS`:

| Argument | Values | Default |
|----------|--------|---------|
| `MODE` | `report` \| `clean` | `report` |
| `SCOPE` | One or more file or directory paths (space-separated) | Default scope defined in SKILL.md |

**MODE semantics:**
- `report` — Scan and emit findings. No files are modified.
- `clean` — Scan, report, confirm with user, then rewrite files removing identified noise.

If no arguments are provided, run in `report` mode against the default scope.

## Execution

Follow the workflow defined in `.claude/skills/u-doc-cleanup/SKILL.md` exactly.

Pass resolved `MODE` and `SCOPE` to the skill execution flow.
