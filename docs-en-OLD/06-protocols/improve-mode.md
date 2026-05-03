# Improve Mode Protocol

Pipeline for incremental improvements that don't require full specification.

## Pre-evaluation

Before starting, the orchestrator evaluates the improvement's impact:
- **Affects API contract?** -> Suggest `/u-spec` first
- **Implementation-only?** -> Proceed with simplified Dev pipeline

## Pipeline

1. Planner generates Task Contracts from `improve##.md`
2. Developer implements each Task Contract
3. QA validates
4. **Post-Task Contract spec evaluation** -- Orchestrator checks if the improvement requires updating existing specs

## Post-Task Contract spec evaluation

After QA approves, the orchestrator evaluates whether the implemented improvement:
- Changed any API behavior
- Added new endpoints or fields
- Modified existing business rules

If yes, it flags the spec for update. This evaluation is mandatory but doesn't always result in spec changes.

## When to suggest /u-spec first

The orchestrator suggests running `/u-spec` before `/u-dev` when:
- The improvement adds or removes API endpoints
- The improvement changes request/response schemas
- The improvement modifies authentication or authorization behavior
