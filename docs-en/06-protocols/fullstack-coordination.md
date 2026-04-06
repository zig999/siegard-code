# Fullstack Coordination Protocol

Coordinates the BE→FE handoff and E2E integration validation in `domain: fullstack` sessions.

## When triggered

- After Phase 1 (Backend) completes in a fullstack session
- Before Phase 2 (Frontend) starts
- After Phase 2 completes (E2E validation assessment)

## BE→FE Handoff

When Phase 1 completes:

1. Validate all BE stories are `Done` (no `Blocked` or `Escalation`)
2. Collect implemented endpoints, database changes, and API contract status
3. Generate `handoff-be-to-fe.md` with:
   - Implemented endpoint table (Story, endpoint, method, status)
   - Database changes
   - Known deviations from spec
   - Notes for the FE phase
4. Pass handoff to the FE orchestrator as additional context

## Scope filtering

The unified `backlog.md` contains stories tagged with `scope:`. Each domain orchestrator processes only its slice:

- **BE orchestrator**: `scope: backend` and `scope: both` (BE portion)
- **FE orchestrator**: `scope: frontend` and `scope: both` (FE portion, after BE dependency is `Done`)

Both orchestrators write to the same `backlog.md`, updating only stories in their scope.

## E2E Integration Validation

After both phases complete, the meta-orchestrator assesses whether E2E validation is needed:

- **Recommended**: stories with `scope: both`, or FE stories consuming endpoints from Phase 1
- **Skippable**: all stories are independent (no cross-domain data flow)

If E2E runs, it checks: contract match, response handling, data flow, error states, and auth/session.

## E2E Failure Handling

1. **Contract mismatch** (BE response != spec) → reopen BE story
2. **FE integration bug** (FE misreads correct response) → reopen FE story
3. **Spec ambiguity** (both sides implemented differently) → escalate to human

## Output

- `handoff-be-to-fe.md` -- BE→FE transition summary
- `e2e-validation.md` -- E2E integration test results (if executed)
