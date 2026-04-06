# Bug Mode Protocol

Specialized pipeline for handling bugs, with two variants based on bug type.

## Pipeline selection

| Bug type | Pipeline |
|----------|----------|
| **Visual/UI adjustment** | Lean pipeline |
| **Incorrect behavior / integration error / unknown** | Full pipeline |

## Lean pipeline

For visual/UI bugs only:
- Developer implements fix directly (no Planner, no TDD)
- Visual QA only (no full test suite)
- Faster turnaround

## Full pipeline

For behavioral, integration, or unknown bugs:
- Planner generates fix Stories with priority classification
- Developer implements with TDD approach
- Full QA validation

## Priority classification

| Priority | Description | Treatment |
|----------|-------------|-----------|
| **P0** | Critical -- blocks core functionality | Processed first |
| **P1** | High -- major feature broken | Processed after P0 |

## Quality gate

The `bug reproducao` (reproduction steps) field must be filled before the Developer starts work. This ensures:
- The bug can be verified as fixed
- Regression tests can be written from reproduction steps
