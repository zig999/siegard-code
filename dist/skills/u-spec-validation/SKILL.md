---
name: u-spec-validation
description: Cross-validation skill for specs - cross-reference, error code consistency, state coverage, and orphan spec detection.
user-invocable: false
---

# SKILL: Cross-Validation of Specs

## Purpose
Provide the Spec Validator with rules for verifying consistency across all documents in a domain.

## Cross-Reference: UC -> Endpoint -> BR -> UI

Every use case must have complete coverage:

```
UC-01 (spec.md)
  -> operationId: createTask (openapi.yaml)
    -> BR-01: title validation (back.md)
    -> UI-01: loading state (screen.md)
    -> UI-04: error handling (screen.md)
```

### Checklist per layer

**For each UC in .spec.md:**
- [ ] Endpoint exists in openapi.yaml
- [ ] At least 1 BR in .back.md references this UC
- [ ] UI handling exists for each HTTP status of the endpoint
- [ ] Errors have mapping in screen.md

**For each BR in .back.md:**
- [ ] References an existing UC
- [ ] error.code in global catalog
- [ ] HTTP status matches openapi.yaml

**For each UI in .screen.md:**
- [ ] Referenced endpoints exist in openapi.yaml
- [ ] Mapped error.codes exist in global catalog
- [ ] Minimum states: loading, success, error, empty

## Error Code Consistency

1. Same `error.code` = same HTTP status across all files
2. Same `error.code` = compatible description across all layers
3. Every used `error.code` must exist in the global catalog
4. Procedure: collect from openapi -> spec -> back -> screen -> validate intersection

## Orphan Spec Detection

- BR references nonexistent UC
- UI references nonexistent operationId
- FL references screen without .screen.md
- EV without declared consumer (alert)
- Referenced domain does not exist or is in draft

## Dependency Validation

1. Referenced domain must exist
2. Referenced domain must be `approved`
3. Bidirectional dependencies (A lists B, B lists A)
4. Circular: flag as alert (non-blocking)

## Incremental Validation

| Trigger | What to validate |
|---------|-----------------|
| .back.md ready | UC <-> BR, error codes back <-> catalog |
| .screen.md ready | UI states, error mapping, fetching |
| All ready | Full validation across all layers |

## Report Format

```markdown
# Validation: {domain} v{version}
> Validator: Spec Validator | Date: {date}
> Status: VALID | INVALID

## Coverage Map
| UC | Endpoint | BR | UI (screen) | FL (flow) | Status |
|----|----------|----|-------------|-----------|--------|

## Inconsistencies
| # | Type | Source File | Target File | Description |
|---|------|------------|-------------|-------------|

## Error Codes
| error.code | openapi | spec | back | front/screen | Status |
|------------|---------|------|------|-------------|--------|

## Dependencies
| Domain | Exists | Status | Bidirectional |
|--------|--------|--------|---------------|

## Result
- [ ] UC coverage complete
- [ ] Error codes consistent
- [ ] No orphan specs
- [ ] Dependencies valid
```

### Extended format (with triage support)

When the report is persisted to a file for triage (`{SPECS_DIR}/_validation/{domain}-validation.md`), include additional fields:

**Additional header:**
```
> Triage: PENDING | IN_PROGRESS | COMPLETED
```

**Extended Inconsistencies table:**
```markdown
| # | Type | Source File | Target File | Description | Agent | Severity | Selected |
|---|------|------------|-------------|-------------|-------|----------|----------|
```

| Field | Values |
|-------|--------|
| `Agent` | Back Spec Agent, Front Spec Agent, Spec Writer, `-- (external)` |
| `Severity` | `blocking` (prevents handoff) or `alert` (informational) |
| `Selected` | `[ ]` (not selected) or `[x]` (selected for correction) |

**Additional section at the end:**
```markdown
## Triage History
| Date | Selected items | Activated agents | Result |
|------|---------------|-----------------|--------|
```

Full format details: see `protocols/u-spec-validation-triage.md`
