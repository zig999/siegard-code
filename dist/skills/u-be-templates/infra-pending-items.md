# Template: us-XX-infra-pending-items.md

Save to `{SESSIONS_DIR}/{SESSION}/us-XX-infra-pending-items.md`:

```markdown
# Infrastructure Pending Items: US-XX — [Story Title]

**Date:** YYYY-MM-DD
**Story:** US-XX
**Overall status:** Partial block | Implementable with mocks | Total block

---

## Summary

[Brief description of what the Story needs from infrastructure and the current state]

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
