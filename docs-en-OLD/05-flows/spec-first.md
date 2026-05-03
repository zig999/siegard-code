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
5.5. **error.code sync check** — Orchestrator verifies all `error.code` values from `.back.md` files are registered in the global catalog before Front Spec Agent starts; missing codes are registered by the Spec Writer first
6. Front Spec Agent produces feature specs, component specs, and flows (after ALL back specs valid AND error.code catalog is complete)
7. Validator performs final cross-reference check (including BDD coverage and component spec coverage)
8. Handoff packages artifacts for Dev team (includes `feature.spec.md`, `component.spec.md`, `decisions.md`)

### Phase 2: Development (`/u-dev`)

**Backend (`domain: backend`):**
1. Orchestrator reads `decisions.md` (session-start rule)
2. Planner creates backlog from approved specs (Task Contracts with `execution_contract` YAML)
3. Developer implements each Task Contract
4. QA validates and approves

**Frontend (`domain: frontend`):**
1. Orchestrator reads `decisions.md` (session-start rule)
2. Planner creates backlog from approved specs + runs Component Spec Gate (Step 4B)
3. UI Agent generates visual specifications (uses `feature.spec.md` — §9 BDD as acceptance contract)
4. Developer implements each Task Contract (Props Contract from `component.spec.md` is binding)
5. QA validates: §9 BDD scenarios first (primary gate), then Task Contract `validation.criteria`

**Fullstack (`domain: fullstack`):**
1. Planner creates unified backlog with `scope:` per Task Contract
2. Phase 1 — Backend Task Contracts are implemented and tested
3. BE→FE handoff generated (`handoff-be-to-fe.md`)
4. Phase 2 — Frontend Task Contracts are implemented and tested (same FE flow above)
5. Phase 3 — E2E integration validation (if cross-domain Task Contracts exist)

### Phase 3: Delivery

- Code committed via push-merge protocol
- Temporary artifacts archived to `_temp/`
- Orchestrator log records completion
