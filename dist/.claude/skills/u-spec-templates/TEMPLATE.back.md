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
> `.spec.md` is the single normative source for WHAT each rule is. A back BR never restates
> the rule — it cites its source BR and declares only HOW the rule is enforced.
> Restatement is a Validator finding (`check_br_pairs.py`).

### BR-01 -- {Name}
**Related UC:** UC-{NN}
**Source rule:** `{domain}.spec.md` BR-{NN}
**Where to validate:** {controller \| service \| middleware} · `{path/to/file.ts}` · `{exportedSymbol}` · `{test file that enforces it}` — pointers only; test requirements live in u-be-standards. Never test plans or fixture code here.
**Description:** {HOW the rule is enforced — never the rule itself: technical guards, edge cases (null \| empty \| 0 \| out-of-enum), extension strategy (closed \| append-only \| strategy), implementation artifacts (Zod schema, SQL literal name, helper signature)}
**Error returned:** HTTP {status} -- error.code: `{CODE}` — pointer to the matching `.spec.md` §6 Error Behaviors row; never redeclare the error table here.

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

> Mandatory — one row per version. Entry discipline:
> - `Description` is a single sentence, max 200 characters: what changed and which sections (§) it touched.
> - No incident narratives, no before/after comparisons, no rationale — that detail lives in git history and the orchestration log, never here.
> - Max 10 rows. When adding a row beyond 10, collapse the oldest rows into one `rollup` row: Type `rollup`, Version `<=X.Y.Z`, Description `N entries (X.Y.Z..A.B.C) rolled up; full history in git`.
> - Body sections describe the current state only — version markers (e.g., `(v1.2.0: ...)`) outside this section are review findings.

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Back Spec Agent | initial | Initial version | -- |
