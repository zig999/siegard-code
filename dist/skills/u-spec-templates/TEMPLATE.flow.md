# {FlowName} -- Flow Spec

> Objective: {what the user wants to complete}
> Domains involved: {list}

## 1. Involved Screens
<!-- INSTRUCTION: List all screens in the flow with route and reference to .screen.md. Every screen listed here must have a corresponding .screen.md — if it does not exist, the Validator will flag it. -->
| # | Route | Screen Spec | Primary Domain |
|---|-------|-------------|----------------|
| 1 | /{route} | {screen}.screen.md | {domain} |
| 2 | /{route} | {screen}.screen.md | {domain} |

## 2. Happy Path
<!-- INSTRUCTION: ASCII diagram of the error-free path. Then, numbered detailed steps. Each step must be a user action or system action, never ambiguous. -->
```
{screen-1} --> {screen-2} --> {screen-3} --> [End]
```

**Detailed steps:**
1. User accesses {screen-1} via {how}
2. ...

## 3. Alternative Flows
<!-- INSTRUCTION: Every deviation from the happy path. Include: error conditions, timeout, user cancels, invalid data, permission denied. Each alternative must have concrete behavior (not "handle appropriately"). -->
| # | Condition | From | To | Behavior |
|---|-----------|------|----|----------|
| 3a | {condition} | {screen} | {screen} | {what happens} |

## 4. Navigation Rules (FL)
<!-- INSTRUCTION: Each rule with explicit condition, behavior, and fallback. Fallback is what happens if the condition cannot be evaluated (e.g., offline). -->

### FL-01 -- {Rule Name}
**Condition:** {when this rule applies}
**Behavior:** {what happens}
**Fallback:** {if the condition fails}

## 5. Deep Links and Alternative Entries
<!-- INSTRUCTION: The user may access any route directly (bookmark, shared link). Define preconditions and behavior when not met. Every route in the flow must have an entry here. -->
| Direct route | Precondition | Behavior if not met |
|-------------|--------------|---------------------|
| {/route} | {authenticated} | redirect -> /login |

## 6. Data Persisted Between Screens
<!-- INSTRUCTION: When data needs to survive navigation between screens. Define concrete mechanism: state (zustand/redux), URL params, sessionStorage, localStorage. Avoid "as needed". -->
| Data | From | To | Mechanism |
|------|------|----|-----------|
| {data} | {screen} | {screen} | {state|url|storage} |

## Changelog
<!-- INSTRUCTION: Mandatory. Never remove previous entries. -->
| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
