# Spec-first Flow

Complete feature development starting from requirements through specification and implementation.

## When to use

- New feature that needs formal specification
- Major change to existing functionality
- New domain being added to the project

## Command sequence

```
/u-spec {SPECS_DIR} -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
```

## Step-by-step

### Phase 1: Specification (`/u-spec`)

1. Describe the requirement to the Spec Orchestrator
2. Writer creates `openapi.yaml` + `.spec.md`
3. Reviewer approves or requests changes
4. Back Spec Agent produces `.back.md` per domain
5. Validator checks incremental consistency
6. Front Spec Agent produces screens and flows (after ALL back specs valid)
7. Validator performs final cross-reference check
8. Handoff packages artifacts for Dev team

### Phase 2: Development (`/u-dev`)

**Backend (`domain: backend`):**
1. Planner creates backlog from approved specs
2. Developer implements each Story
3. QA validates and approves

**Frontend (`domain: frontend`):**
1. Planner creates backlog from approved specs
2. UI Agent generates visual specifications
3. Developer implements each Story
4. QA validates and approves

**Fullstack (`domain: fullstack`):**
1. Planner creates unified backlog with `scope:` per Story
2. Phase 1 -- Backend stories are implemented and tested
3. BE→FE handoff generated (`handoff-be-to-fe.md`)
4. Phase 2 -- Frontend stories are implemented and tested
5. Phase 3 -- E2E integration validation (if cross-domain stories exist)

### Phase 3: Delivery

- Code committed via push-merge protocol
- Temporary artifacts archived to `_temp/`
- Orchestrator log records completion
