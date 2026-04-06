# {ScreenName} -- Screen Spec

> Route: {/path} | Related flows: {flow.md}
> Consumed domains: {list}

## 1. Consumed Domains
<!-- INSTRUCTION: List ALL endpoints this screen consumes. A screen can consume multiple domains. Include the purpose of each call. -->
| Domain | operationId | Endpoint | Purpose |
|--------|-------------|----------|---------|
| {domain} | {listTasks} | GET /tasks | {what for} |

## 2. Screen States (UI)
<!-- INSTRUCTION: Mandatory minimum: idle, loading, success, error, empty. Add specific states as needed (e.g., partial-loading, editing, confirming). Each state must have a description and what to display. -->

### UI-01 -- idle
**Description:** Initial state before any interaction
**What to display:** {description}

### UI-02 -- loading
**Description:** Awaiting API response
**What to display:** skeleton / spinner

### UI-03 -- success
**Description:** Data loaded successfully
**What to display:** {data description}

### UI-04 -- error
**Description:** Request failed
**What to display:** error message + retry button

### UI-05 -- empty
**Description:** Successful request but no data
**What to display:** illustration + CTA

## 3. Behavior per State
<!-- INSTRUCTION: Every row must have a defined next transition. States without an exit are terminal and must be marked as such. -->
| State | What to display | Available action | Next transition |
|-------|----------------|-----------------|-----------------|
| loading | skeleton | -- | success | error | empty |
| empty | illustration + CTA | {action} | loading |
| error | toast + retry | retry | loading |

## 4. Requests, Order, and Cache
<!-- INSTRUCTION: Define execution order, priority, and cache strategy for each call. Critical requests (main data) should be parallel. Secondary requests can be lazy. Cache TTL and revalidation must be specific — avoid "per global default" unless truly identical to the default in front.md. -->
| # | operationId | Domain | Execution | Priority | Cache TTL | Revalidation |
|---|-------------|--------|-----------|----------|-----------|--------------|
| 1 | {listOrders} | {orders} | {parallel} | {critical} | {30s} | {on-focus} |
| 2 | {getUserProfile} | {users} | {parallel} | {critical} | {5min} | {manual} |
| 3 | {getRecommendations} | {catalog} | {lazy} | {normal} | {2min} | {on-focus} |

## 5. Input Validations
<!-- INSTRUCTION: For each form field, define rule, message, and WHEN to validate (blur, submit, change). Rules must be specific: regex, min/max, format. -->
| Field | Rule | User message | When to validate |
|-------|------|-------------|------------------|
| {field} | {rule} | {message} | {blur|submit|change} |

## 6. API Error -> UI Mapping
<!-- INSTRUCTION: Every error.code from consumed endpoints must have a mapping here. Define where to display (inline on field, toast, modal) and user action (retry, redirect, dismiss). -->
| error.code | Where to display | User message | Action |
|------------|-----------------|-------------|--------|
| `AUTH_UNAUTHORIZED` | redirect | -> /login | -- |
| `{CODE}` | {inline|toast|modal} | {message} | {retry|redirect|dismiss} |

## 7. Screen Accessibility
<!-- INSTRUCTION: Mandatory minimum checklist. Add specific requirements based on screen complexity. -->
- [ ] Labels on all inputs
- [ ] Functional keyboard navigation
- [ ] ARIA roles on dynamic components
- [ ] WCAG AA contrast

## 8. Visual Design
<!-- INSTRUCTION: Reference tokens from design-system/tokens.md. Never define values here — no color names, no hex, no arbitrary px. If a needed token does not exist in design-system/, register with a warning for the Front Spec Agent to add it there first. -->
> Tokens defined in `{SPECS_DIR}/front/design-system/tokens.md`.

| Element | Semantic Token | Covered States |
|---------|---------------|----------------|
| [screen element] | `--token-name` | default / hover / focus / error / disabled |

## Changelog
<!-- INSTRUCTION: Mandatory. Never remove previous entries. -->
| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
