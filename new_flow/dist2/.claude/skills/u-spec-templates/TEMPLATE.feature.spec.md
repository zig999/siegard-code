# {FeatureName} -- Feature Spec

> Route: `{/path}` | Related flows: `{flow.md}`
> Consumed domains: `{list}` | Status: draft | review | approved | Layer: permanent

---

## 1. Consumed Endpoints

> For HTTP method, path, request/response schemas, and auth requirements: look up `{SPECS_DIR}/domains/{domain}/openapi.yaml` by operationId. Do not copy contract details here — this table is a cross-domain selection map only.

| Domain | operationId | Purpose |
|--------|-------------|---------|
| {domain} | {operationId} | {why this feature uses this endpoint} |

---

## 2. Feature States (UI)

### UI-01 -- idle
**Entry condition:** initial load, no prior interaction
**What to display:** {description}

### UI-02 -- loading
**Entry condition:** any data request in flight
**What to display:** skeleton / spinner

### UI-03 -- success
**Entry condition:** all critical requests resolved with data
**What to display:** {data description}

### UI-04 -- error
**Entry condition:** any critical request failed
**What to display:** error message + retry action

<!-- Include UI-05 ONLY if this feature displays a collection query that can return zero records
     (list, table, search result, feed). For forms, auth flows, and single-resource views:
     DELETE this state entirely. Do not write "not applicable" — absence communicates the same. -->

### UI-05 -- empty
**Entry condition:** request succeeded, zero records returned
**What to display:** empty state illustration + CTA

---

## 3. State Transition Table

| From | Trigger | To | Side Effect |
|------|---------|----|-------------|
| idle | page mount | loading | — |
| loading | data resolved | success | — |
| loading | request failed | error | — |
| loading | empty response | empty | — | ← remove this row if UI-05 was omitted |
| error | retry action | loading | reset error state |
| {state} | {trigger} | {state} | {cache invalidation \| redirect \| analytics event \| local state reset \| "—"} |

---

## 4. Requests, Order and Cache

| # | operationId | Domain | Execution | Priority | Cache TTL | Revalidation | Params / Headers |
|---|-------------|--------|-----------|----------|-----------|--------------|-----------------|
| 1 | {operationId} | {domain} | {parallel \| sequential \| lazy} | {critical \| normal} | {30s \| inherit} | {on-focus \| manual \| none \| inherit} | {`param=value`, `Header: value` \| —} |

> `inherit` = use global defaults from `front.md §3`. Specify only when overriding the global default.
> `Params / Headers`: record only parameters and headers this feature effectively uses. `openapi.yaml` declares what is possible; this column declares what is used. Always include `Prefer: return=representation` when a mutation requires the returned object.

### Response transforms (optional — omit if API responses are consumed as-is)

| operationId | Input | Output | Rule |
|-------------|-------|--------|------|
| `{operationId}` | `{response.field.path}` | `{ui.field}` | {rename \| cast: Date \| cast: string \| cast: number \| concat \| derive: {expr} \| filter: {cond} \| omit \| flatten} |

### Composed models (optional — omit if each UI model comes from a single endpoint)

**{ModelName}** — consumed by {component or store slice}
| Field | operationId | Source path | Transform |
|-------|-------------|------------|-----------|
| `{field}` | `{operationId}` | `{response.path}` | {none \| rule} |

---

## 5. Input Validations

> Technical constraints (required, minLength, maxLength, pattern, enum) are defined in the `requestBody` schema of the corresponding operationId in `openapi.yaml`. §5 specifies only frontend UX behavior.

| Field | User message | When to validate |
|-------|--------------|------------------|
| {field} | {user-facing message} | {blur \| submit \| change} |

---

## 6. API Error → UI Mapping

| error.code | Display | User message | Action |
|------------|---------|--------------|--------|
| `AUTH_UNAUTHORIZED` | redirect | — | → /login |
| `{CODE}` | {inline \| toast \| modal} | {message} | {retry \| redirect \| dismiss} |

---

## 7. Shared Components Used

> Components from `src/components/` (global) only. Feature-local components belong in §10.
> Feature-specific props = read-only usage customization for this context — NOT component modification. Modifications belong in §10 with Action "update".

| Component | Spec file | Feature-specific props | Notes |
|-----------|-----------|----------------------|-------|
| `{ComponentName}` | `{/components/name.component.spec.md}` \| none | `propName="value"` \| none | {or "—"} |

### Component adapters

> **Required declaration for every component listed in the §7 table.** Absence of declaration is a Validator blocking error.
> - ALL props map directly (same name, same type, no transform): use the `direct-map` declaration.
> - ANY prop requires rename, cast, or derivation: use the adapter block.
> Binding rule: adapter props must reference §2 of the component's `component.spec.md`. An adapter prop not in §2 is a spec error.

**{ComponentName}: direct-map** ← when ALL props arrive with identical name and type from the API response

OR when transformation is required:

**{ComponentName}**
| Component prop | API source | Transform |
|---------------|-----------|-----------|
| `{prop}` | `{operationId}.{response.path}` | {rename \| cast: string \| cast: number \| cast: Date \| derive: {expr} \| concat} |

---

## 8. Feature Accessibility

- [ ] All inputs have associated labels
- [ ] Keyboard navigation covers all interactive elements (Tab, Enter, Esc)
- [ ] ARIA roles on dynamic regions (`aria-live`, `aria-busy`, `role="dialog"`)
- [ ] WCAG AA contrast on all text
- [ ] Focus returns to trigger on modal/drawer close

---

## 9. BDD Scenarios

> Feature invariants: hold true across all Task Contracts in this feature. Cover end-to-end observable outcomes from the user's perspective. Minimum: 1 happy path + 1 critical error. Not Task Contract acceptance criteria — regression anchors.

### Happy path

```
Given {precondition — system state, not user intent}
When {user action}
Then {observable result — specific, verifiable}
  And {optional additional observable state}
```

### Critical error scenario

```
Given {precondition}
When {failure condition — API error, network issue, invalid state}
Then {error state displayed with correct message}
  And {recovery action available — retry, redirect, or dismiss}
```

---

## 10. Components to Create / Update

> **Auto-Spec criterion:** any component with `Action: create` that also appears in §7 of another feature.spec.md (i.e., used in 2+ features) **must have** a `component.spec.md`. The Planner will auto-generate a Spec Task Contract for it in Step 4B if the spec is absent.

| Component | Action | Needed by | Rationale |
|-----------|--------|-----------|-----------|
| `{ComponentName}` | create \| update | `{/route}` | {used in 2+ features \| complex internal logic \| shared contract} |

---

## 11. Out of Scope

> Declare explicitly what will NOT be implemented in this spec. Prevents scope creep and clarifies QA boundaries.

- {excluded functionality or behavior — one item per line}

---

## Changelog

> Mandatory — never remove previous entries.

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
