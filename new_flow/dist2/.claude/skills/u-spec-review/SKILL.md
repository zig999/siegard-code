---
name: u-spec-review
description: Specification review skill - quality checklists, ambiguity detection, and approval/rejection criteria.
user-invocable: false
---

# SKILL: Specification Review

## Purpose
Provide the Spec Reviewer with checklists and objective criteria for evaluating specs.

## Checklist -- OpenAPI

### Structure
- [ ] `openapi` version present and >= 3.0.0
- [ ] `info` with title, version, and description
- [ ] `servers` with at least 1 entry
- [ ] All `$ref` resolve correctly
- [ ] No orphan schemas (defined but not referenced)

### Endpoints
- [ ] Every endpoint has a unique `operationId`
- [ ] Every endpoint has `tags`, `summary`, `description`
- [ ] HTTP verbs are correct:
  - GET: read-only, no state change
  - POST: creation or named action (e.g., `/archive`, `/cancel`)
  - PUT: full replacement of resource
  - PATCH: partial update or state transition
  - DELETE: permanent removal only — soft delete must use PATCH or POST
- [ ] Responses cover: 200/201, 400, 401, 404, 422, 500 (as applicable)
- [ ] Error response follows standard `ErrorResponse` schema
- [ ] `example` present in every response

### Schemas
- [ ] `required` explicit in every schema
- [ ] Every field has `type` and `description`
- [ ] Dates use `format: date-time`, IDs use `format: uuid`
- [ ] Enums documented
- [ ] No duplicate schemas (use `$ref`)

### Security
- [ ] `securitySchemes` defined if needed
- [ ] `security` applied to endpoints that require auth
- [ ] Public endpoints have explicit `security: []`

## Checklist -- .spec.md

### Completeness
- [ ] Overview with 3-5 sentences
- [ ] Actors table with permissions
- [ ] At least 1 UC with main flow + alternative flow
- [ ] Every UC references an endpoint (operationId)
- [ ] Errors cover all status >= 400 from openapi.yaml
- [ ] Out of Scope present
- [ ] Changelog present

### Consistency UC <-> OpenAPI
- [ ] Every endpoint has at least 1 UC
- [ ] Every UC references a valid operationId
- [ ] UC parameters match the schema
- [ ] UC errors match the endpoint’s status codes

### Writing Quality
- [ ] No ambiguous terms ("may", "generally", "adequate", "etc.")
- [ ] Business rules are testable and objective
- [ ] Preconditions are programmatically verifiable
- [ ] Postconditions describe an observable change

## Ambiguity Detection

| Forbidden term | Replace with |
|----------------|-------------|
| "may" / "might" | "must" (mandatory) or "optionally" |
| "generally" | List all cases |
| "adequate" | Objective criteria |
| "etc." | List all items |
| "similar to" | Reference specific spec |
| "soon" | Specific version or Out of Scope |

## Severity Levels

| Level | Criterion | Action |
|-------|----------|--------|
| **Blocking** | Contradiction, endpoint without UC, invalid schema | REJECTED |
| **Major** | Ambiguity in business rule, unmapped error | REVISION REQUIRED |
| **Minor** | Typo, short description, missing example | Fix and document |

## Report Format

```markdown
# Review: {domain} v{version}
> Reviewer: Spec Reviewer | Date: {date}
> Status: APPROVED | REJECTED | REVISION REQUIRED

## Summary
{1-2 sentences}

## Issues Found
| # | File | Location | Severity | Description | Suggestion |
|---|------|----------|----------|-------------|------------|

## Automatic Corrections Applied
| # | File | What was corrected |
|---|------|--------------------|

## Approval
- [ ] OpenAPI valid
- [ ] UC <-> endpoints coverage complete
- [ ] Error codes in global catalog
- [ ] No blocking ambiguities
```
