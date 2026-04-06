---
name: u-fullstack-coordination
description: Protocol for coordinating BE→FE handoff and E2E integration validation in fullstack sessions. Loaded by u-fullstack-orchestrator.md during phase transitions and Phase 3.
user-invocable: false
---

# Protocol: Fullstack Coordination

## Purpose
Defines the handoff process between backend and frontend phases, and the E2E integration validation for fullstack development sessions.

---

## 1. BE → FE Handoff

When Phase 1 (Backend) completes and Phase 2 (Frontend) is about to start:

### 1.1 Validate BE completion

Before activating the FE orchestrator, confirm:

- [ ] All `scope: backend` stories have status `Done` in `backlog.md`
- [ ] All `scope: both` stories (BE portion) have status `Done`
- [ ] No stories are in `Blocked — Escalation` status
- [ ] `log-be.md` contains completion entries for all BE stories

If any BE story is not `Done`:
- If `Blocked — Escalation`: escalate to the human — do not start FE phase
- If `In testing` or `In development`: wait for the BE orchestrator to finish

### 1.2 Prepare FE context

Collect from completed BE stories:

1. **Implemented endpoints** — list all routes/endpoints created or modified, with their HTTP methods and response shapes
2. **Database changes** — list migrations, new tables/columns, schema changes
3. **API contracts** — confirm that `openapi.yaml` in `{SPECS_DIR}/domains/` reflects the implemented state
4. **Known deviations** — any `spec-divergences.md` entries from BE stories

Write a handoff summary to `{SESSIONS_DIR}/{SESSION}/handoff-be-to-fe.md`:

```markdown
# BE → FE Handoff — {SESSION}

_Generated on: YYYY-MM-DD HH:MM_

## Implemented endpoints

| Story | Endpoint | Method | Status |
|-------|----------|--------|--------|
| US-XX | /api/resource | GET, POST | Done |
| US-YY | /api/resource/:id | GET, PUT, DELETE | Done |

## Database changes
- [migration/table/column changes]

## API contract status
- `{SPECS_DIR}/domains/{domain}/openapi.yaml` — [up to date | has divergences]

## Known deviations
- [list from spec-divergences.md, or "none"]

## Notes for FE team
- [any BE-side constraints the FE should be aware of]
```

### 1.3 Pass handoff to FE orchestrator

When activating `u-fe-orchestrator-core`, include in the prompt:

> "Read `{SESSIONS_DIR}/{SESSION}/handoff-be-to-fe.md` for the list of implemented backend endpoints and any deviations from the original spec. Use actual endpoint responses as ground truth — `openapi.yaml` is the contract, but the handoff file reflects what was actually implemented and tested."

---

## 2. Scope filtering rules

### 2.1 How domain orchestrators filter the backlog

The unified `backlog.md` contains stories with `scope:` fields. Each domain orchestrator processes only its slice:

**Backend orchestrator receives:**
> "From `backlog.md`, process only stories where `scope: backend`. For stories where `scope: both`, process only if the story ID matches the BE portion (the Planner splits `scope: both` into linked pairs). Ignore all `scope: frontend` stories."

**Frontend orchestrator receives:**
> "From `backlog.md`, process only stories where `scope: frontend`. For stories where `scope: both`, process only if the story ID matches the FE portion AND its BE dependency has status `Done`. Ignore all `scope: backend` stories."

### 2.2 Status updates in the unified backlog

Both orchestrators write to the same `backlog.md`. To avoid conflicts:

- Each orchestrator updates **only** the status of stories in its scope
- The meta-orchestrator validates consistency after each phase completes
- If a status conflict is detected (same story modified by both), the meta-orchestrator escalates to the human

---

## 3. E2E Integration Validation

### 3.1 When to run

E2E validation is recommended when:
- At least one story has `scope: both` (cross-domain interaction)
- Frontend stories consume endpoints that were implemented in Phase 1
- The project has E2E test infrastructure (Cypress, Playwright, etc.)

### 3.2 Validation checklist

For each cross-domain interaction:

```markdown
## E2E Validation — {SESSION}

### Cross-domain stories

| FE Story | BE Story | Endpoint | Interaction | Status |
|----------|----------|----------|-------------|--------|
| US-YY | US-XX | POST /api/resource | Form submission → API call → DB write → response | [ ] |
| US-WW | US-ZZ | GET /api/list | Page load → API call → render list | [ ] |

### Validation steps

For each row:
1. **Contract match:** FE request shape matches BE expected input
2. **Response handling:** FE correctly handles all response codes (200, 400, 404, 500)
3. **Data flow:** data written by BE is correctly read and displayed by FE
4. **Error states:** FE displays appropriate messages for BE error responses
5. **Auth/session:** if endpoints require auth, FE sends correct tokens
```

### 3.3 Execution

The meta-orchestrator does NOT run E2E tests itself. It:

1. Generates the validation checklist above
2. Presents it to the human
3. If the project has E2E test infrastructure, suggests:
   ```
   E2E test infrastructure detected ({tool}).

   Options:
   1. Run existing E2E tests: {command}
   2. Generate new E2E tests for cross-domain stories
   3. Manual validation only

   Choose [1 / 2 / 3]:
   ```
4. For option 2: activates the FE QA agent with the E2E checklist as input
5. For option 1: runs the test command and reports results
6. For option 3: the human validates manually and confirms

### 3.4 E2E report

Write results to `{SESSIONS_DIR}/{SESSION}/e2e-validation.md`:

```markdown
# E2E Integration Validation — {SESSION}

_Executed on: YYYY-MM-DD HH:MM_
_Method: [automated | manual | mixed]_

## Results

| FE Story | BE Story | Contract | Responses | Data flow | Errors | Auth | Verdict |
|----------|----------|----------|-----------|-----------|--------|------|---------|
| US-YY | US-XX | PASS | PASS | PASS | PASS | N/A | PASS |
| US-WW | US-ZZ | PASS | FAIL | — | — | — | FAIL |

## Failures
- **US-WW ↔ US-ZZ:** FE expects `{ items: [] }` but BE returns `{ data: [] }` — contract mismatch in GET /api/list response shape

## Recommended actions
- [ ] US-ZZ: update response shape to match openapi.yaml (BE fix)
- [ ] Re-run E2E after fix
```

### 3.5 Handling E2E failures

If E2E validation finds issues:

1. Classify the failure:
   - **Contract mismatch** (BE response ≠ spec) → reopen BE story for fix
   - **FE integration bug** (FE misreads correct response) → reopen FE story for fix
   - **Spec ambiguity** (both sides implemented differently) → escalate to human

2. Reactivate the appropriate domain orchestrator for the fix:
   - BE fix → Phase 1 resumes for the specific story
   - FE fix → Phase 2 resumes for the specific story

3. After fix, re-run E2E validation for the affected stories only

---

## 4. Merge coordination

In fullstack sessions, the merge strategy depends on the project structure:

### 4.1 Monorepo (single repo, BE + FE)

- All stories are on branches in the same repo
- Merge order: BE stories first, then FE stories
- After all merges, run E2E validation on the merged branch

### 4.2 Multi-repo (separate BE and FE repos)

- BE stories are merged to the BE repo
- FE stories are merged to the FE repo
- E2E validation runs against both repos (requires both services running)

The meta-orchestrator detects the project structure by checking:
- Single `package.json` / `pyproject.toml` at root → likely monorepo
- Separate directories with independent package managers → likely monorepo with workspaces
- `CLAUDE.md` specifies `repos:` or `workspaces:` → use the declared structure

Always confirm the merge strategy with the human before proceeding.
