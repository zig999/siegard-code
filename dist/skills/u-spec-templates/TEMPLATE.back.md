# {Domain} -- Back-end Spec

> Stack: {language/framework} | DB: {database} | Version: {1.0.0} | Status: draft | review | approved | Layer: permanent
> Business spec: `{domain}.spec.md`

---

## 1. Stack and Patterns

> Declare only values that differ from or extend CLAUDE.md. Use `"CLAUDE.md default"` for aspects already covered there.

| Aspect | Value | Note |
|--------|-------|------|
| Framework | {value} | {override reason \| "CLAUDE.md default"} |
| ORM | {value} | {override reason \| "CLAUDE.md default"} |
| Migration strategy | {value} | {override reason \| "CLAUDE.md default"} |
| Architecture pattern | {value} | {override reason \| "CLAUDE.md default"} |

---

## 2. Data Model

### Table: {name}

> Exact database types (varchar(255), integer, uuid, timestamp). Every field has a description.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|

### Indexes

> Justify each index with the query it optimizes. Corresponds to predictable queries from openapi.yaml endpoints.

| Table | Fields | Type | Justification |
|-------|--------|------|---------------|

### Relationships

> FK + on-delete strategy. Cross-domain: via ID only — never nested objects.

| From | To | Type | FK | On Delete |
|------|----|------|----|-----------|

---

## 3. Business Rules (BR)

> Every BR references a UC from .spec.md. BR without UC = orphan (Validator blocking).

### BR-01 -- {Name}
**Related UC:** UC-{NN}
**Where to validate:** {controller \| service \| middleware}
**Description:** {objective and testable rule}
**Error returned:** HTTP {status} -- error.code: `{CODE}`

---

## 4. State Machine (ST)

> Corresponds to .spec.md state machine — add technical guards not in the business spec. Remove section if not applicable.

### ST-01 -- {Entity}
| From | To | Event | Guard | UC |
|------|----|-------|-------|----|

---

## 5. Domain Events (EV)

> Concrete JSON example in payload. Unknown consumer = Warning.

### EV-01 -- {event.name}
**Dispatched when:** {condition}
**Payload:**
```json
{
  "field": "type",
  "example": "value"
}
```
**Consumers:** {services that listen}

---

## 6. External Integrations

> Timeout and fallback required per integration. No fallback = operational risk — document the decision.

| Service | Type | Purpose | Timeout | Fallback |
|---------|------|---------|---------|----------|

---

## 7. Known Technical Constraints

> Write "No constraints identified." if empty.

---

## 8. Out of Scope

> What this back-end does NOT do in this version. Mandatory.

- {what this back-end does not do}

---

## Changelog

> Mandatory — never remove previous entries.

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Back Spec Agent | initial | Initial version | -- |
