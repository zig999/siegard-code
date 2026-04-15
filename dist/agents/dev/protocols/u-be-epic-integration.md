## Epic Integration Protocol

When all Task Contracts in an Epic reach `Done`:

1. Activate **QA & Docs** in **Epic integration mode** with:
   - `## Mode: epic-integration`
   - `## Target Epic: EPIC-XX — [Name]`
   - All `tc-XX-delivery.md` from the Epic
   - All `tc-XX-qa.md` from the Epic
   - Approved domain specs (if they exist): `{SPECS_DIR}/domains/{domain}/openapi.yaml` + `{SPECS_DIR}/domains/{domain}/back/{domain}.back.md` — contract consistency
   # Skills are embedded in the QA agent — do not re-inject
2. Verifications:
   - [ ] Task Contracts work in sequence (end-to-end flow)
   - [ ] No contract breakage between Task Contracts
   - [ ] API consistency preserved (non-conflicting endpoints)
   - [ ] Cross-Task-Contract regression (shared modules)
3. **Output artifact:** QA generates `{SESSIONS_DIR}/{SESSION}/epic-XX-integration-qa.md` with:
   - Verdict: Approved | Rejected
   - Verification matrix (checklist above with results)
   - Bugs found (if any, using the standard bug template)
   - Recommendation
4. If rejected: technical bug -> Developer (specific Task Contract), UX inconsistency -> human
5. Record as `In testing — integration (round N)` in the log
6. Only mark Epic as `Done` after approval

### Traceability Matrix

After approval, generate `{SESSIONS_DIR}/{SESSION}/traceability-matrix.md`:

```markdown
# Traceability Matrix — Epic {name}

> Date: {YYYY-MM-DD} | Session: {SESSION} | Task Contracts: {N}

## Tracing UC -> Task Contract -> Test -> Code

| UC | Task Contract | Acceptance Criterion | Test File | Main Code | Status |
|----|-------|---------------------|-----------|-----------|--------|

## Tracing BR -> Implementation

| BR | Task Contract | Implemented in | Tested in | Status |
|----|-------|---------------|-----------|--------|

## Coverage

| Metric | Total | Implemented | Tested | Coverage |
|--------|-------|-------------|--------|----------|
| UC | {N} | {N} | {N} | {N}% |
| BR | {N} | {N} | {N} | {N}% |
```

Use `tc-XX-delivery.md` and `tc-XX-qa.md` as sources. Cross-reference with specs if in Spec-first mode.
