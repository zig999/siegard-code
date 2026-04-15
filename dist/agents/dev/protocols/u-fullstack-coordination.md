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

- [ ] All `scope: backend` task contracts have status `Done` in `backlog.md`
- [ ] No task contracts are in `Blocked — Escalation` status
- [ ] `log-be.md` contains completion entries for all BE task contracts

> **Scope model:** `scope: both` is prohibited in task contracts. Cross-domain features are represented as linked pairs: a `scope: backend` TC (e.g. TC-03) and a `scope: frontend` TC (e.g. TC-04) with `dependencies: [TC-03]`. The FE TC may only start after its BE dependency reaches `Done`.

If any BE story is not `Done`:
- If `Blocked — Escalation`: escalate to the human — do not start FE phase
- If `In testing` or `In development`: wait for the BE orchestrator to finish

### 1.2 Prepare FE context

Collect from completed BE task contracts:

1. **Implemented endpoints** — list all routes/endpoints created or modified, with their HTTP methods and response shapes
2. **Database changes** — list migrations, new tables/columns, schema changes
3. **API contracts** — confirm that `openapi.yaml` in `{SPECS_DIR}/domains/` reflects the implemented state
4. **Known deviations** — any `spec-divergences.md` entries from BE task contracts

Write a handoff summary to `{SESSIONS_DIR}/{SESSION}/handoff-be-to-fe.md`. The file must start with a YAML gate block (inside a yaml code fence) following `.claude/skills/u-shared-templates/be-to-fe-handoff.schema.yaml`, followed by the Markdown body:

````markdown
```yaml
# be-to-fe-handoff
session: {SESSION}
layer: semi-permanent
generated_by: u-fullstack-orchestrator
generated_at: YYYY-MM-DDTHH:MM:SSZ

be_phase_status: complete | complete_with_deviations

endpoints:
  - task_contract: TC-XX
    endpoint: /api/resource
    methods: [GET, POST]
    status: done
  - task_contract: TC-YY
    endpoint: /api/resource/:id
    methods: [GET, PUT, DELETE]
    status: done

api_contract_status: up_to_date | has_deviations
known_deviations_count: 0

database_changes: []

fe_notes: []
```

# BE → FE Handoff — {SESSION}

_Generated on: YYYY-MM-DD HH:MM_

## Implemented endpoints

| Task Contract | Endpoint | Method | Status |
|--------------|----------|--------|--------|
| TC-XX | /api/resource | GET, POST | Done |
| TC-YY | /api/resource/:id | GET, PUT, DELETE | Done |

## Database changes
- [migration/table/column changes]

## API contract status
- `{SPECS_DIR}/domains/{domain}/openapi.yaml` — [up to date | has divergences]

## Known deviations
- [list from spec-divergences.md, or "none"]

## Notes for FE team
- [any BE-side constraints the FE should be aware of]
````

### 1.3 Pass handoff to FE orchestrator

When activating `u-fe-orchestrator-core`, include in the prompt:

> "Read `{SESSIONS_DIR}/{SESSION}/handoff-be-to-fe.md` for the list of implemented backend endpoints and any deviations from the original spec. Use actual endpoint responses as ground truth — `openapi.yaml` is the contract, but the handoff file reflects what was actually implemented and tested."

---

## 2. Scope filtering rules

### 2.1 How domain orchestrators filter the backlog

The unified `backlog.md` contains task contracts with `scope:` fields. Each domain orchestrator processes only its slice:

**Backend orchestrator receives:**
> "From `backlog.md`, process only task contracts where `scope: backend`. Ignore all `scope: frontend` task contracts."

**Frontend orchestrator receives:**
> "From `backlog.md`, process only task contracts where `scope: frontend`. Process a `scope: frontend` TC only if all entries in its `dependencies[]` have status `Done`. Ignore all `scope: backend` task contracts."

> **Split-pair convention:** when the Planner creates a fullstack feature, it generates two linked TCs. Example: TC-03 (`scope: backend`, `dependencies: []`) and TC-04 (`scope: frontend`, `dependencies: [TC-03]`). `scope: both` is prohibited by the task_contract schema — do not create it.

### 2.2 Status updates in the unified backlog

Both orchestrators write to the same `backlog.md`. To avoid conflicts:

- Each orchestrator updates **only** the status of task contracts in its scope
- The meta-orchestrator validates consistency after each phase completes
- If a status conflict is detected (same story modified by both), the meta-orchestrator escalates to the human

---

## 3. E2E Integration Validation

### 3.1 When to run

E2E validation is recommended when:
- At least one linked TC pair shares a `story_ref` field (cross-domain interaction)
- Frontend task contracts consume endpoints that were implemented in Phase 1
- The project has E2E test infrastructure (Cypress, Playwright, etc.)

### 3.2 Validation checklist

For each cross-domain interaction:

```markdown
## E2E Validation — {SESSION}

### Cross-domain task contracts

| FE Task Contract | BE Task Contract | Endpoint | Interaction | Status |
|-----------------|----------------|----------|-------------|--------|
| TC-YY | TC-XX | POST /api/resource | Form submission → API call → DB write → response | [ ] |
| TC-WW | TC-ZZ | GET /api/list | Page load → API call → render list | [ ] |

### Validation steps

For each row:
1. **Contract match:** FE request shape matches BE expected input
2. **Response handling:** FE correctly handles all response codes (200, 400, 404, 500)
3. **Data flow:** data written by BE is correctly read and displayed by FE
4. **Error states:** FE displays the error message returned in the BE response body for each non-2xx status code
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
   2. Generate new E2E tests for cross-domain task contracts
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

| FE Task Contract | BE Task Contract | Contract | Responses | Data flow | Errors | Auth | Verdict |
|-----------------|----------------|----------|-----------|-----------|--------|------|---------|
| TC-YY | TC-XX | PASS | PASS | PASS | PASS | N/A | PASS |
| TC-WW | TC-ZZ | PASS | FAIL | — | — | — | FAIL |

## Failures
- **TC-WW ↔ TC-ZZ:** FE expects `{ items: [] }` but BE returns `{ data: [] }` — contract mismatch in GET /api/list response shape

## Recommended actions
- [ ] TC-ZZ: update response shape to match openapi.yaml (BE fix)
- [ ] Re-run E2E after fix
```

### 3.5 Handling E2E failures

If E2E validation finds issues:

1. Classify the failure:
   - **Contract mismatch** (BE response ≠ spec) → reopen BE story for fix
   - **FE integration bug** (FE misreads correct response) → reopen FE story for fix
   - **Spec ambiguity** (both sides implemented differently) → escalate to human

2. Reactivate the domain orchestrator responsible for the fix:
   - BE fix → Phase 1 resumes for the specific story
   - FE fix → Phase 2 resumes for the specific story

3. After fix, re-run E2E validation for the affected task contracts only

---

## 4. Merge coordination

In fullstack sessions, the merge strategy depends on the project structure:

### 4.1 Monorepo (single repo, BE + FE)

- All task contracts are on branches in the same repo
- Merge order: BE task contracts first, then FE task contracts
- After all merges, run E2E validation on the merged branch

### 4.2 Multi-repo (separate BE and FE repos)

- BE task contracts are merged to the BE repo
- FE task contracts are merged to the FE repo
- E2E validation runs against both repos (requires both services running)

The meta-orchestrator detects the project structure by checking:
- Single `package.json` / `pyproject.toml` at root → likely monorepo
- Separate directories with independent package managers → likely monorepo with workspaces
- `CLAUDE.md` specifies `repos:` or `workspaces:` → use the declared structure

Always confirm the merge strategy with the human before proceeding.
