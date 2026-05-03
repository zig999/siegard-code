# Template: tc-XX-backend-pending-items.md

Save to `$SESSION_DIR/pending/$ORCH_TASK_ID-backend-pending.md`:

```markdown
# Backend Pending Items: TC-XX — [Task Contract Title]

**Date:** YYYY-MM-DD
**Layer:** semi-permanent
**Task:** TC-XX
**Frontend owner:** Developer Agent
**Overall status:** Partial block | Implementable with mocks | Total block

---

## Summary

[Brief description of what the Task Contract needs from the backend and the current state of dependencies]

---

## Required Endpoints

### 1. [Descriptive operation name]

| Field | Value |
|---|---|
| Method | `GET` / `POST` / `PUT` / `DELETE` / `PATCH` |
| Expected route | `/api/v1/resource` |
| Payload (request) | `{ field: type }` or N/A |
| Expected response | `{ field: type }` |
| Status | Available / Partial / Missing |
| Where it was searched | [files, docs, or sources consulted] |

**Details (if Partial or Missing):**
- What is missing or divergent
- Impact on the frontend (which functionality is compromised)

### 2. [Next endpoint...]

_(repeat for each required endpoint)_

---

## Actions Taken on the Frontend

| Missing endpoint | Action on frontend |
|---|---|
| `POST /api/v1/resource` | Mock created in `services/resource.mock.ts` |
| `GET /api/v1/other` | Static data in `__mocks__/other.json` |

---

## Recommendations for the Backend Team

- [ ] Create endpoint `POST /api/v1/resource` — [description of required contract]
- [ ] Adjust response of `GET /api/v1/other` to include field `newAttribute: string`

---

## Impact on Delivery

- **What works without the backend:** [features that run with mocks]
- **What is blocked:** [features that depend on real integration]
- **When the backend is ready:** remove mocks marked with `// TODO(TC-XX)` and test integration
```
