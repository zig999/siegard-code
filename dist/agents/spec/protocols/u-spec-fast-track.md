# Protocol: Fast-Track for Minor Changes

## Purpose
Define a simplified flow for low-impact changes to already-approved specs, avoiding the full 7-step pipeline for trivial modifications.

## When to use fast-track

### Eligible for fast-track (Minor/Patch)
- Typo or formatting correction
- Description or example improvement
- Addition of an **optional** field to an existing schema
- Addition of a new endpoint that does not affect existing endpoints
- Addition of a new independent UC
- Addition of a new error.code without affecting existing ones

### NOT eligible (requires full flow)
- Removal of a field, endpoint, or UC
- Type change of an existing field
- Contract change (request/response) of an existing endpoint
- Business rule change that affects an existing flow
- State machine change (addition/removal of transition)
- Any change that breaks existing consumers

## Fast-track flow

```
1. Orchestrator classifies the demand as minor/patch
   |
2. Spec Writer updates ONLY the affected files
   - Increments version (minor or patch)
   - Updates Changelog
   |
3. Spec Reviewer performs FOCUSED review
   - Reviews only the diff (changed areas)
   - Verifies correct version increment
   - Verifies Changelog updated
   - Does NOT re-review unaffected sections
   |
4. Spec Validator performs INCREMENTAL validation
   - Validates cross-references only for affected areas
   - If the change does not affect .back.md, does not require rewrite
   |
5. Orchestrator delivers diff to the implementation group
   - Package contains only changed files + minimal context
```

## Change propagation

When a minor/patch change in `.spec.md` or `openapi.yaml` affects other files:

| Change | Propagates to .back.md? | Propagates to screens? |
|--------|------------------------|------------------------|
| New optional field | Yes (data model) | Yes (if on screen) |
| New endpoint | Yes (new BR) | Yes (new screen or state) |
| New UC | Yes (new BRs) | Depends |
| Description correction | No | No |
| New error.code | No (if already in catalog) | Yes (mapping) |

### Propagation validation by the Reviewer

The Spec Reviewer MUST verify that the Writer applied the propagation rules correctly. In step 3 (focused review), in addition to the diff, the Reviewer must:

1. **Check the table above** for the type of change made
2. **Verify that affected files were updated** per the table:
   - If the change requires propagation to `.back.md` and the Writer did not update -> **REJECTED** with instruction: "Missing propagation to .back.md per fast-track propagation table"
   - If the change requires propagation to screens and the Writer did not update -> **REJECTED** likewise
3. **Verify that unaffected files were NOT modified** — Writer must not touch areas outside scope

> If the Reviewer detects that the change should have propagated but did not, they return to the Writer with the list of missing files — they do not attempt to fix it themselves.

## Record

Every fast-track change must be recorded in the Orchestrator log with:
- Type: `fast-track:minor` or `fast-track:patch`
- Affected files
- Justification for using fast-track
