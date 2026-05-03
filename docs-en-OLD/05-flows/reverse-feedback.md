# Reverse Feedback Flow

When a Developer discovers a problem in the specification during implementation.

## When to use

- Developer finds that a spec is infeasible to implement as written
- Implementation reveals a missing use case or business rule
- API contract needs adjustment based on implementation reality

## How it works

### Option 1: Formal spec correction

1. Developer generates `feedback-NN.md` describing the problem
2. Run `/u-spec` -- The orchestrator classifies this as **reverse feedback** mode
3. Writer corrects the affected specs
4. Reviewer validates the corrections
5. Validator performs cross-reference check
6. Development resumes with corrected specs

### Option 2: Accepted divergence

If the divergence is acceptable (e.g., performance optimization that slightly differs from spec):
1. Register the divergence in `spec-divergences.md`
2. Document the reason and impact
3. Continue implementation with the accepted divergence

## When to choose each option

| Scenario | Recommended option |
|----------|-------------------|
| Spec is wrong or incomplete | Formal correction |
| Spec is correct but impractical | Formal correction |
| Minor implementation detail differs | Accepted divergence |
| Performance optimization changes approach | Accepted divergence |
