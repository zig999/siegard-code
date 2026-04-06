# {Domain} -- Back-end Spec

> Stack: {language/framework} | DB: {database} | Version: {1.0.0}
> Business spec: {domain}.spec.md (version {x.y.z})

## 1. Stack and Patterns
<!-- INSTRUCTION: Define framework, ORM, migration strategy, architecture (MVC, Clean, Hexagonal). Base on the project's CLAUDE.md. If the project already has established patterns, reference them — do not redefine. -->

## 2. Data Model

### Table: {name}
<!-- INSTRUCTION: One subsection per table. Include all fields with exact database types (varchar(255), integer, uuid, timestamp, etc.). Every field must have a description. -->
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|

### Indexes
<!-- INSTRUCTION: Justify each index with the query it optimizes. Indexes should correspond to predictable queries from the openapi.yaml endpoints. -->
| Table | Fields | Type | Justification |
|-------|--------|------|---------------|

### Relationships
<!-- INSTRUCTION: Define FK and on delete strategy. Relationships between domains are via ID, never nested objects. -->
| From | To | Type | FK | On Delete |
|------|----|------|----|-----------|

## 3. Business Rules (BR)
<!-- INSTRUCTION: Every BR must reference a UC from .spec.md. If there is no corresponding UC, the BR is orphaned — flag to the Validator. -->

### BR-01 -- {Name}
**Related UC:** UC-{NN}
**Where to validate:** {controller|service|middleware}
**Description:** {objective and testable rule}
**Error returned:** HTTP {status} -- error.code: `{CODE}`

## 4. State Machine (ST)
<!-- INSTRUCTION: Must correspond to the state machine in .spec.md. Add guards (technical conditions) that were not at the business level. Remove this section if not applicable. -->

### ST-01 -- {Entity}
| From | To | Event | Guard | UC |
|------|----|-------|-------|----|

## 5. Domain Events (EV)
<!-- INSTRUCTION: Payload must have a concrete JSON example (not abstract). Consumers must be known services. If no consumer is identified, register as a warning. -->

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

## 6. External Integrations
<!-- INSTRUCTION: For each integration, define timeout and fallback. An integration without fallback is an operational risk — document the decision if there is none. -->
| Service | Type | Purpose | Timeout | Fallback |
|---------|------|---------|---------|----------|

## 7. Known Technical Constraints
<!-- INSTRUCTION: Infrastructure limitations, performance, dependencies that the implementation group needs to know. If no constraints, write "No constraints identified." -->

## 8. Out of Scope (back)
<!-- INSTRUCTION: What this back-end does NOT do in this version. Section is mandatory. -->
- {what this back-end does not do in this version}

## Changelog
<!-- INSTRUCTION: Mandatory. Never remove previous entries. -->
| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Back Spec Agent | initial | Initial version | -- |
