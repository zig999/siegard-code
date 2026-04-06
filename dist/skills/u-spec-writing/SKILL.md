---
name: u-spec-writing
description: Specification writing skill - OpenAPI 3.0, domain modeling, use cases, and error mapping.
user-invocable: false
---

# SKILL: Specification Writing

## Purpose
Provide the Spec Writer with the knowledge needed to produce high-quality specs.

## OpenAPI 3.0 -- Quality Checklist

### Mandatory structure
- `openapi: "3.0.3"`
- `info.title`, `info.version`, `info.description`
- `servers` with at least a dev environment
- `paths` with all domain endpoints
- `components.schemas` with all models
- `components.securitySchemes` if authentication exists
- `tags` grouping endpoints by context

### Endpoint rules
- Correct HTTP verbs: GET (read), POST (create), PUT (replace), PATCH (partial), DELETE (remove)
- `operationId` in camelCase, globally unique: `listTasks`, `createTask`, `getTaskById`
- Every response must have a `description`
- Error responses with standard schema:

```yaml
ErrorResponse:
  type: object
  required: [error]
  properties:
    error:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
          example: "RESOURCE_NOT_FOUND"
        message:
          type: string
          example: "Task with id 123 not found"
        details:
          type: object
```

### Schema rules
- `required` fields always explicit
- `format` for typed strings: `date-time`, `email`, `uuid`
- `example` on every schema and property
- `enum` for fields with finite values
- `$ref` to reuse schemas -- never duplicate

## Domain Modeling

### Identify
1. **Entities** -- objects with identity and lifecycle (e.g., User, Task, Order)
2. **Value Objects** -- objects without own identity (e.g., Address, Money)
3. **Aggregates** -- grouping of entities with a root (e.g., Order + OrderItems)
4. **Events** -- facts that occurred in the domain (e.g., TaskCompleted, OrderShipped)

### Rules
- Each domain has at most 1-3 root entities
- Relationships between domains are via ID, never nested objects
- Invariants must be listed explicitly

## Use Cases

### Mandatory structure
1. **Actor** -- who initiates
2. **Precondition** -- what must be true before
3. **Postcondition** -- what changes after
4. **Main flow** -- numbered steps of the happy path
5. **Alternative flows** -- deviations (format `Na` where N is the step)
6. **Related endpoint** -- corresponding operationId

### Best practices
- One UC = one actor intent
- Alternative flows must cover ALL endpoint errors
- Each UC must have at least 1 alternative flow

## Error Mapping

### Process
1. List all HTTP status >= 400 for each endpoint
2. For each, define an `error.code`
3. Check the global catalog to see if it already exists
4. If new, register in the catalog BEFORE using it
5. Include in the "Error Behaviors" section of .spec.md
