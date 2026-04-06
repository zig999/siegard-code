# {DomainName} -- Business Specification

> Version: {1.0.0} | Status: {draft|review|approved}
> Technical contract: openapi.yaml

## 1. Overview
<!-- INSTRUCTION: 3 to 5 objective sentences. Answer: what is this domain, what problem does it solve, what are the primary entities. Do not use jargon without defining it in the glossary. -->

## 2. Actors
<!-- INSTRUCTION: List all actors that interact with this domain. Each actor must have explicit permissions — do not use "full access" or "regular user". -->
| Actor | Description | Permissions |
|-------|------------|-------------|
| {Actor} | {description} | {what they can do} |

## 3. Use Cases
<!-- INSTRUCTION: One UC per actor intent. Every UC must have: main flow (happy path), at least 1 alternative flow (error or deviation), and related endpoint with operationId. Alternative flows must cover ALL errors from the endpoint. -->

### UC-01 -- {Name}
**Actor:** {who} | **Pre:** {verifiable condition} | **Post:** {observable change}

**Main flow:**
1. ...
2. ...

**Alternative flows:**
- `2a` {condition} -> {behavior}

**Related endpoints:** `POST /api/v1/{resource}` (operationId: `{id}`)

## 4. Business Rules
<!-- INSTRUCTION: Each rule must be programmatically testable. Avoid "adequate", "reasonable", "when necessary". Define concrete limits. -->

### BR-01 -- {Rule Name}
<!-- Describe the rule objectively. Use table for state machine. -->

## 5. State Machine
<!-- INSTRUCTION: Include only if the primary entity has a lifecycle (e.g., order, task, user). Remove this entire section if not applicable. Use ASCII diagram + transition table. Every transition must reference the UC that triggers it. -->

```
[state-1] --event--> [state-2] --event--> [state-3]
```

| From | Event | To | Condition | UC |
|------|-------|----|-----------|----|

## 6. Error Behaviors
<!-- INSTRUCTION: List ALL HTTP statuses >= 400 from all endpoints. Each error must have an error.code registered in the global catalog. Do not leave any error status unmapped. -->
| Situation | HTTP | error.code | Description |
|-----------|------|------------|-------------|
| {situation} | {4xx} | `{CODE}` | {when it occurs} |

## 7. Cross-Domain Dependencies
<!-- INSTRUCTION: List all domains that this domain consumes from, produces data for, or synchronizes with. Dependencies must be bidirectional — if this domain lists "auth", the "auth" domain must list this one. If there are no dependencies, write "None". -->
| Domain | Type | Description |
|--------|------|-------------|
| {domain} | {consumes|produces|synchronizes} | {how they relate} |

## 8. Out of Scope
<!-- INSTRUCTION: List features that might be expected in this domain but are NOT included. Include reason or future version. Section is mandatory even if empty — in that case write "No exclusions in this version." -->
- {feature} -- {reason or future version}

## 9. Local Glossary
<!-- INSTRUCTION: Terms specific to this domain that are not in the global glossary. If a term is already in the global one, do not repeat here. -->
| Term | Definition |
|------|-----------|
| {Term} | {definition} |

## Changelog
<!-- INSTRUCTION: Mandatory. Never remove previous entries. Always add a new line when modifying. -->
| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Spec Writer | initial | Initial version | -- |
