# {DomainName} -- Business Specification

> Version: {1.0.0} | Status: draft | review | approved | Layer: permanent
> Technical contract: `openapi.yaml`

---

## 1. Overview

| Aspect | Value |
|--------|-------|
| Objective | {one sentence: what business problem this domain solves} |
| Core entity | {primary domain entity name} |
| Bounded context | {what this domain owns} |
| Out of scope | {what this domain does NOT own — cross-reference §8} |

---

## 2. Actors

> Actor permissions must be explicit — never "full access" or "regular user".

| Actor | Description | Permissions |
|-------|------------|-------------|
| {Actor} | {description} | {what they can do} |

---

## 3. Use Cases

> 1 UC per actor intent. Each UC: main flow + at least 1 alternative flow + related operationId. Alternative flows cover ALL errors from the endpoint.

### UC-01 -- {Name}
**Actor:** {who} | **Pre:** {verifiable condition} | **Post:** {observable change}

**Main flow:**
1. ...
2. ...

**Alternative flows:**
- `2a` {condition} -> {behavior}

**Related endpoint:** operationId: `{id}`

---

## 4. Business Rules

> Each rule: programmatically testable, concrete limits. No "adequate", "reasonable", "when necessary". Every BR references a UC.

### BR-01 -- {Rule Name}
{objective and testable description}

---

## 5. State Machine

> Only for entities with a lifecycle. Remove section if not applicable.

```
[state-1] --event--> [state-2] --event--> [state-3]
```

| From | Event | To | Condition | UC |
|------|-------|----|-----------|----|

---

## 6. Error Behaviors

> All HTTP statuses >= 400 from all endpoints. Every error.code registered in the global catalog.

| Situation | HTTP | error.code | Description |
|-----------|------|------------|-------------|
| {situation} | {4xx} | `{CODE}` | {when it occurs} |

---

## 7. Cross-Domain Dependencies

> Bidirectional — if this domain lists X, X must list this domain.

| Domain | Type | Description |
|--------|------|-------------|
| {domain} | {consumes \| produces \| synchronizes} | {how they relate} |

---

## 8. Out of Scope

> Mandatory — write "No exclusions in this version." if empty.

- {feature} -- {reason or future version}

---

## 9. Local Glossary

> Domain-specific terms not in the global glossary.

| Term | Definition |
|------|-----------|
| {Term} | {definition} |

---

## Changelog

> Mandatory — never remove previous entries.

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Spec Writer | initial | Initial version | -- |
