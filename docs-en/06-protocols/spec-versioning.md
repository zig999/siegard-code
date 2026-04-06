# Spec Versioning Protocol

Semantic versioning applied to all specifications.

## Version types

| Type | When | Impact | Example |
|------|------|--------|---------|
| **Major** | Breaking change | Consumers must adapt | Remove endpoint, change required field type |
| **Minor** | Additive, non-breaking | Consumers can ignore | New endpoint, optional field |
| **Patch** | No functional impact | Transparent to consumers | Typo fix, clarification |

## How it works

1. Orchestrator classifies the change type
2. Creates a **Change Request** in the orchestrator log
3. Version is bumped in the affected spec files
4. Handoff includes the new version

## Change Request

Recorded in `log-orchestrator-spec.md` with:
- Previous version
- New version
- Change classification (major/minor/patch)
- Affected artifacts
- Reason for change
