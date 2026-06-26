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
    -> UI-01: loading state (feature.spec.md §2)
    -> UI-04: error handling (feature.spec.md §6)
```

### Checklist per layer

**For each UC in .spec.md:**
- [ ] Endpoint exists in openapi.yaml
- [ ] At least 1 BR in .back.md references this UC
- [ ] UI handling exists for each HTTP status of the endpoint
- [ ] Errors have mapping in feature.spec.md (§6)

**For each BR in .back.md:**
- [ ] References an existing UC
- [ ] error.code in global catalog
- [ ] HTTP status matches openapi.yaml

**For each UI-NN in .feature.spec.md (§2):**
- [ ] Referenced endpoints exist in openapi.yaml
- [ ] Mapped error.codes exist in global catalog
- [ ] Minimum states: loading, success, error, empty

## Error Code Consistency

1. Same `error.code` = same HTTP status across all files
2. Same `error.code` = compatible description across all layers
3. Every used `error.code` must exist in the global catalog
4. Procedure: collect from openapi -> spec -> back -> feature.spec -> validate intersection

## FL-NN vs feature.spec.md §3 Consistency

Cross-check between navigation rules in `flow.md §4` and state transitions in `feature.spec.md §3`.

**For each FL-NN in flow.md §4:**

| Check | Severity |
|-------|----------|
| FL-NN `Behavior` involves redirect to feature B, but `feature.spec.md §3` for the source feature has no row with a matching `Side Effect: redirect → {feature B route}` | warning |
| FL-NN `Condition` references a UI state (e.g., "user is unauthenticated") that is not defined in `feature.spec.md §2` for the source feature — and is not covered by `front.md §5` (Global Error Handling) | warning |
| FL-NN references a route that has no corresponding `.feature.spec.md` | blocking |

**For each redirect Side Effect in feature.spec.md §3:**

| Check | Severity |
|-------|----------|
| Side Effect is a cross-feature redirect (to a different route) with no FL-NN in any flow covering this transition — and the destination route is not handled globally in `front.md §5` | warning |

**Procedure:**
1. For each flow, build a map: `{source_feature_route} → {FL-NN condition} → {destination_route}`
2. For each source feature in the map, read `feature.spec.md §3` and extract Side Effects containing redirects
3. Cross-reference: every FL-NN redirect must appear as a Side Effect; every cross-feature §3 redirect must have a FL-NN or `front.md §5` entry
4. Mismatches → warning entries in the Inconsistencies table

---

## Orphan Spec Detection

- BR references nonexistent UC
- UI references nonexistent operationId
- FL references feature without .feature.spec.md
- EV without declared consumer (warning)
- Referenced domain does not exist or is in draft

## Dependency Validation

1. Referenced domain must exist
2. Referenced domain must be `approved`
3. Bidirectional dependencies (A lists B, B lists A)
4. Circular: flag as warning (non-blocking)

## Component Adapter Completeness (§7)

Executed during front phase validation for each component listed in §7 of a feature spec.

| Check | Severity |
|-------|----------|
| Component in §7 has a `component.spec.md` AND adapter block is absent AND at least one prop does not map directly (same name, same type) from API response | blocking |
| Adapter prop not declared in the component's `component.spec.md §2` Props Contract | blocking |
| Component in §7 qualifies for a spec (used in 2+ features or complex logic) but has no `component.spec.md` | warning |

**Direct mapping rule:** a prop is considered directly mapped when: the API response field name equals the prop name AND the type is compatible without casting. Any rename, cast, derive, concat, or flatten requires an explicit adapter entry.

---

## HTTP Verb vs Soft-Delete Cross-Check

Executed during full validation (when both `.back.md` and `openapi.yaml` are ready).

| Check | Severity |
|-------|----------|
| `.back.md` declares soft-delete strategy AND `openapi.yaml` uses `DELETE` for that endpoint without a corresponding `PATCH` or `POST` endpoint for the state transition | blocking |
| `openapi.yaml` uses `DELETE` AND `.back.md` declares the entity as deactivatable/archivable without a BR justifying hard delete | blocking |

---

## Incremental Validation

| Trigger | What to validate |
|---------|-----------------|
| .back.md ready | UC <-> BR, error codes back <-> catalog |
| .feature.spec.md ready | UI states (§2), error mapping (§6), fetching (§4), component adapters (§7) |
| All ready | Full validation across all layers |

## Report Format

```markdown
# Validation: {domain} v{version}
> Validator: Spec Validator | Date: {date}
> Status: VALID | INVALID

## Coverage Map
| UC | Endpoint | BR | UI (feature.spec) | FL (flow) | Status |
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
| `Severity` | `blocking` (prevents handoff) or `warning` (informational) |
| `Selected` | `[ ]` (not selected) or `[x]` (selected for correction) |

**Additional section at the end:**
```markdown
## Triage History
| Date | Selected items | Activated agents | Result |
|------|---------------|-----------------|--------|
```

Full format details: see `protocols/u-spec-validation-triage.md`
