# {FlowName} -- Flow Spec

> Flow ID: FLOW-NN | Objective: {what the user wants to complete} | Status: draft | review | approved | Layer: permanent
> Domains involved: {list}

---

## 1. Involved Features

> Every feature listed here must have a corresponding .feature.spec.md — the Validator flags missing specs.

| # | Route | Feature Spec | Primary Domain |
|---|-------|-------------|----------------|
| 1 | /{route} | {feature}.feature.spec.md | {domain} |

---

## 2. Happy Path

> Mermaid flowchart of the error-free path, then numbered steps. Each step is a user action or system action — never ambiguous.
> Use `flowchart TD` (top-down) for linear flows; `flowchart LR` (left-right) for wide branching.
> Permission guards use diamond `{condition?}`; screens use rectangle `[Screen]`;
> system actions use double-border rectangle `[[action]]`; end uses `([End])`.
> One diagram per named sub-flow. Do not collapse all sub-flows into a single diagram.
> Error nodes use CSS class: `E[Inline error]:::error`.
> Never use ASCII art in a code block to represent navigation flows.

```mermaid
flowchart TD
  A[{screen-1}] --> B{guard?}
  B -->|yes| C[{screen-2}]
  B -->|no| D[{fallback}]
  C --> E([End])
```

**Detailed steps:**
1. User accesses {screen-1} via {how}
2. ...

---

## 3. Alternative Flows

> Every deviation from the happy path: error conditions, timeout, user cancels, invalid data, permission denied. Each alternative must have concrete behavior — not "handle appropriately".

| # | Condition | From | To | Behavior |
|---|-----------|------|----|----------|
| 3a | {condition} | {screen} | {screen} | {what happens} |

> State transition table — one row per atomic event. Complements the alternative flows table above.
> Every guard, permission check, and API error that changes application state must appear here.
> Do not merge rows: one event + one condition = one row.
> "Current State" and "Next State" are always named screens, modals, or UI states — never vague descriptions like "current screen".
> "Event" is always a concrete trigger: click, submit, HTTP response, timeout.
> "Condition" may be empty if there is no guard (write —).
> "Action" uses controlled vocabulary: redirect | toast-success | toast-error | inline-error | close-modal | open-modal | revalidate-query | none.
> API errors must include the code: e.g. 409 BUSINESS_GROUP_HAS_USERS.

| Current State  | Event                         | Condition                          | Next State          | Action                                                          |
|----------------|-------------------------------|------------------------------------|---------------------|-----------------------------------------------------------------|
| {screen/modal} | {user action or system event} | {guard / permission / error code}  | {screen/modal/same} | {redirect \| toast \| inline-error \| close-modal \| none}     |

---

## 4. Navigation Rules (FL)

> Each rule must have an explicit condition, behavior, and fallback. Fallback = what happens if the condition cannot be evaluated (e.g., offline).

### FL-01 -- {Rule Name}
**Condition:** {when this rule applies}
**Behavior:** {what happens}
**Fallback:** {if the condition fails}

---

## 5. Deep Links and Alternative Entries

> The user may access any route directly (bookmark, shared link). Every route in the flow must have an entry here.

| Direct route | Precondition | Behavior if not met |
|-------------|--------------|---------------------|
| {/route} | {authenticated} | redirect -> /login |

---

## 6. Data Persisted Between Screens

> Only when data must survive navigation. Mechanism must be concrete — never "as needed".

| Data | From | To | Mechanism |
|------|------|----|-----------|
| {data} | {screen} | {screen} | {state \| url \| sessionStorage \| localStorage} |

---

## Changelog

> Mandatory — never remove previous entries.

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
