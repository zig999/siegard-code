# Protocol: Spec Versioning

## Purpose
Define clear versioning rules for all spec documents, ensuring traceability and breaking change control.

## Semantic Versioning for Specs

Every spec follows `MAJOR.MINOR.PATCH`:

### PATCH (0.0.x)
Changes that DO NOT affect existing implementation:
- Typo or formatting corrections
- Description or example improvements
- Clarification of existing rule without behavior change
- Addition of example where there was none

### MINOR (0.x.0)
Changes that ADD without breaking:
- New use case (UC)
- New endpoint
- New **optional** field in an existing schema
- New business rule (BR) for new functionality
- New state in a state machine (without affecting existing transitions)
- New error.code

### MAJOR (x.0.0)
Changes that BREAK existing contracts:
- Removal of a field, endpoint, or UC
- Type change of an existing field
- Contract change (request/response) of an existing endpoint
- Removal or change of a state machine transition
- Change of meaning of an existing error.code
- Business rule change that alters existing flow behavior

## Document Status

```
draft --> review --> approved --> deprecated
                       |
                       +--> (via CR) --> draft (new version)
```

| Transition | Who | When |
|------------|-----|------|
| draft -> review | Spec Writer | When finishing writing/rewriting |
| review -> approved | Spec Reviewer | When approving without blocking issues |
| review -> draft | Spec Reviewer | When rejecting (returns to Writer) |
| approved -> draft (new version) | Orchestrator | When opening a Change Request |
| approved -> deprecated | Orchestrator | When replaced by a major version |

## Rules

### Never edit an approved spec without a CR
A spec with `approved` status can only be changed via a formal Change Request:
1. Orchestrator opens CR-NN
2. Status changes to `draft` on the new version
3. Pipeline runs again (full or fast-track)

### Reference version
When `.back.md` is written, it must declare in the header:
```
> Business spec: {domain}.spec.md (version {x.y.z})
```
This allows tracing against which version of the business spec it was written.

### Post-handoff compatibility
If a spec has already been delivered to the implementation group:
- **Patch:** can be delivered as a diff, implementation updates without rework
- **Minor:** deliver diff + instructions about what is new
- **Major:** requires new full handoff + impact assessment on existing code

## Changelog

Every spec file must have a `## Changelog` section at the end:

```markdown
## Changelog
| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | 2026-03-21 | Spec Writer | initial | Initial version | -- |
| 1.1.0 | 2026-03-22 | Spec Writer | minor | New endpoint GET /tasks/stats | CR-01 |
| 2.0.0 | 2026-03-25 | Spec Writer | major | Removal of `legacy_id` field | CR-03 |
```

Fields:
- **Version:** new version after the change
- **Date:** date of the change (ISO format)
- **Author:** agent that made the change
- **Type:** `initial`, `patch`, `minor`, `major`
- **Description:** change summary in 1 sentence
- **CR:** Change Request number (or `--` if initial version)

## Change Request (CR)

### Format
```markdown
# CR-{NN}: {title}
> Domain: {domain} | Priority: {P0|P1|P2}
> Origin: {new requirement|reverse feedback|improvement}
> Date: {YYYY-MM-DD}
> Impact: {patch|minor|major}

## Motivation
{Why this change is necessary}

## Proposed Changes
1. {file} — {what changes}
2. {file} — {what changes}

## Impact on dependent specs
| Domain | File | Impact |
|--------|------|--------|

## Impact on existing implementation
{If handoff has already occurred, describe impact on code}
```

### Numbering
- CRs are numbered sequentially per project: CR-01, CR-02, CR-03...
- Recorded in the Orchestrator log
- Referenced in the Changelog of each affected file

### CR YAML Artifact

Every CR must also produce a machine-readable artifact:

**Path:** `{SESSIONS_DIR}/{SESSION}/cr-NN.yaml`
**Schema:** `.claude/skills/u-shared-templates/cr.schema.yaml`
**NN:** sequential number within the session (match CR-NN number)

Create this file immediately when the CR is opened. The handoff gate reads all `cr-NN.yaml` files in the session to check for blocking open CRs before delivering to the Dev group.
