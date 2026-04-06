# Template: us-XX-delivery.md (Backend)

Save to `{SESSIONS_DIR}/{SESSION}/us-XX-delivery.md`:

```markdown
# Delivery: US-XX — [Title]

**Date:** YYYY-MM-DD
**Status:** Implemented | Implemented with caveats

## What was done
[Description in natural language — what the system does now that it did not do before]

## Files created
- `path/file.ts` — [file responsibility]

## Files modified
- `path/other.ts` — [what changed and why]

## Migrations created
- `migrations/YYYYMMDDHHMMSS-description.ts` — [what the migration does]

## Acceptance criteria — traceability
- [x] Given X, When Y, Then Z -> implemented in `file.ts`, function `funcName()`
- [ ] Given A, When B, Then C -> **not implemented** — reason: [explanation]

## Edge cases handled
- Null input in `createUser()` -> returns 400 with validation
- Duplicate resource -> returns 409 Conflict

## Points of attention for QA
- [behaviors that deserve special attention during testing]

## Infrastructure dependencies
- **Report:** `us-XX-infra-pending-items.md` | No pending items
- **Mocks created:** [list of mock files] | None

## Technical debt generated
- [list] | None

## Tests written

| File | Covers |
|---|---|
| `__tests__/unit/user.service.spec.ts` | Acceptance criteria 1 and 2; edge case: null input |
| `__tests__/integration/user.integration.spec.ts` | Criterion 3; edge case: duplicate |
```
