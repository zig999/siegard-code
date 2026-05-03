# Template: tc-XX-infra-pending-items.md

Save to `$SESSION_DIR/pending/$ORCH_TASK_ID-infra-pending.md`:

```markdown
# Infrastructure Pending Items: TC-XX — [Task Contract Title]

**Date:** YYYY-MM-DD
**Layer:** semi-permanent
**Task:** TC-XX
**Overall status:** Partial block | Implementable with mocks | Total block

---

## Summary

[Brief description of what the Task Contract needs from infrastructure and the current state]

---

## Required Dependencies

### 1. [Service/resource name]

| Field | Value |
|---|---|
| Type | Database / Queue / Cache / External API / Storage |
| Expected configuration | [environment variables, connection string, etc.] |
| Status | Available / Partial / Missing |
| Where it was searched | [files, configs, or sources consulted] |

**Details (if Partial or Missing):**
- What is missing or divergent
- Impact on implementation

---

## Actions Taken

| Missing dependency | Action in code |
|---|---|
| Redis cache | In-memory mock with Map() |
| External payment API | Stub returning fixed success |

---

## Recommendations

- [ ] Configure `REDIS_URL` variable in `.env`
- [ ] Add Redis service to docker-compose
```
