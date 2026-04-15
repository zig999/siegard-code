## API Contracts Protocol

**Ownership:** the Developer records consumed contracts in `docs/api-contracts.md` during implementation. QA validates whether new contracts were documented (see `.claude/skills/u-fe-qa-docs/SKILL.md` — "Documentation verification").

**Updates:** when a Task Contract consumes an already-documented endpoint but with a different contract than recorded, the Developer must update `docs/api-contracts.md` on the same Task Contract branch and record the change in `tc-XX-delivery.md`.

---

## Contract entry format

Each endpoint consumed by the frontend must be recorded in `docs/api-contracts.md` with the following structure:

```yaml
- endpoint: GET /api/users/{id}
  task_contract: TC-XX
  version: "2026-04-09"
  request:
    path_params:
      id: string (UUID)
    headers:
      Authorization: Bearer <token>
      X-Trace-Id: string
  response:
    success:
      status: 200
      body: UserDTO  # reference to OpenAPI schema or inline type
    errors:
      - status: 404
        error_code: USER_NOT_FOUND
      - status: 401
        error_code: UNAUTHORIZED
  breaking_change: false
  notes: ""
```

---

## Breaking change detection

A change to an existing contract entry is a **breaking change** when it:
- Removes or renames a required request field
- Removes or renames a response field consumed by the frontend
- Changes a field type (e.g., `string` → `number`)
- Changes HTTP method or route

**When a breaking change is detected:**
1. Do not silently update the entry — flag it in `tc-XX-delivery.md` under `spec_divergences`
2. Record as `BREAKING: <description>` in `docs/api-contracts.md` with the Task Contract reference
3. Notify the Orchestrator — this may require a backend Task Contract or a spec CR

Non-breaking additions (new optional fields, new error codes for existing endpoints) can be updated without escalation.

---

## Version pinning

Each entry records the `version` date of the contract as known at implementation time. If the backend uses OpenAPI, record the schema version or git SHA in `CLAUDE.md` under `api_schema_version`.

---

## QA validation

QA verifies during full mode (Phase 2, documentation check) that:
- [ ] Every endpoint consumed by the Task Contract has an entry in `docs/api-contracts.md`
- [ ] Entries for modified endpoints reflect the current contract
- [ ] Breaking changes are flagged — not silently overwritten
- [ ] `X-Trace-Id` forwarding is present in request headers (links to observability check)

Missing or stale entries are logged as Quality BUG (Low). Breaking changes recorded without escalation are logged as Quality BUG (High).
