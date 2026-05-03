# {ComponentName} -- Component Spec

> Path: `src/components/{name}/`
> Used in features: `{/route, /route}` | Status: draft | review | approved | Layer: permanent

---

## 1. Purpose and Responsibilities

{What this component renders and what problem it solves.}

**Out of scope for this component:** {what it deliberately does not handle}

---

## 2. When to Use / When Not to Use

> Guides consumers on correct placement. "Not to use" must name the alternative component — never leave it open-ended.

| Use when | Do not use when |
|----------|-----------------|
| {valid context — type of data, frequency in UI, interaction type} | {invalid context} → use `{AlternativeComponent}` instead |

---

## 3. Props Contract

> Binding contract. Prop changes without a spec CR are breaking changes. TypeScript types from the project; props sourcing API response data must reference the openapi.yaml schema type.

<!-- Include the TypeScript import block below when any prop's type originates from a project
     module (not a primitive, built-in, or shadcn/ui intrinsic). Use the exact @/ alias path.
     Omit this block if all types are primitives (string, number, boolean, Date) or framework intrinsics. -->

```ts
import type { {TypeName} } from '@/features/{domain}/types/{domain}.types'
```

| Prop | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| {prop} | {type} | yes \| no | {value \| —} | {description} |

---

## 3.1 Data Contract

> Fill when: (a) one or more props receive objects or arrays where the component uses only a subset of fields, OR (b) two or more props have fields that cross-reference each other (join rules).
> Omit entirely if all props map directly to their TypeScript types with no internal field selection, filtering, or cross-prop correlation.

**Field usage:**

| Field | Source prop | Internal use | Behavior if absent |
|-------|-------------|--------------|-------------------|
| `{field}` | `{prop}` | `{how the component uses this field}` | `{default value or fallback behavior}` |

**Cross-prop join rules** *(fill only when fields from two or more props are correlated — omit if not applicable):*

| Prop A | Field A | Prop B | Field B | Relationship |
|--------|---------|--------|---------|--------------|
| `{prop}` | `{field}` | `{prop}` | `{field}` | `{matches on \| filters by \| references}` |

---

## 4. Component States

> Internal states only (own useState/useReducer). States driven entirely by external props belong in §3.

| State | Trigger | Visual change | Interactivity |
|-------|---------|---------------|---------------|
| `idle` | initial render | {default appearance} | full |
| `{name}` | `{prop === value}` | {what changes} | {full \| partial \| none} |

> **Transition parameters:** For states triggered by a numeric threshold or derived formula (e.g., adaptive typography, layout breakpoints), document exact values below. Omit if no thresholds apply.

| Parameter | Formula / Value | Unit | Applies to state |
|-----------|----------------|------|-----------------|
| `{name}` | `{exact value or formula}` | `{px \| rem \| %  \| —}` | `{state name}` |

---

## 5. Events Emitted

> Pure display components with no callback props: **omit this section entirely.**
> Do not write "None" — absence of the section is unambiguous.
> Include this section only when the component has at least one callback prop.
> Exact TypeScript payload type for every callback prop. `() => void` if no payload. `(data: any) => void` is rejected.

| Event | Payload type | When emitted | Consumer action |
|-------|-------------|--------------|-----------------|
| `{onEvent}` | `{TypeScript type}` | {trigger condition} | {what the consumer does} |

---

## 6. Variants and Compositions

| Variant | Prop | Usage context |
|---------|------|---------------|
| `{name}` | `variant="{name}"` | {where and when to use} |

---

## 7. Do / Don't

| Do | Don't |
|----|-------|
| {correct usage} | {incorrect usage — reason} |

---

## 8. BDD Scenarios

> Minimum 3 scenarios: default render + error/disabled state + keyboard navigation. Isolation test baseline.

### Default render

```
Given the component receives valid required props
When it mounts
Then it renders in idle state with correct content
```

### Error state

```
Given {error condition}
When {trigger}
Then the component shows {error display} and disables {interaction}
```

### Keyboard navigation

```
Given the component is focused
When the user presses {Tab | Enter | Esc | Arrow keys}
Then focus moves to {next element} and {observable result}
```

---

## 9. Accessibility Contract

| Requirement | Implementation |
|-------------|---------------|
| Label | {aria-label strategy or "wraps labeled element"} |
| Keyboard | {Tab / Enter / Esc behavior} |
| Focus management | {on open: moves to {element} · on close: returns to {trigger}} |
| ARIA states | {aria-expanded \| aria-disabled \| aria-busy \| aria-selected — as applicable} |

---

## 10. Internal Dependencies

> Components from the design system or other specs consumed internally. Write "None" if absent.

| Component | Source | Usage |
|-----------|--------|-------|
| `{ComponentName}` | `design-system/components.md` \| `{/components/name.component.spec.md}` | {what it does inside this component} |

---

## Changelog

> Mandatory — never remove previous entries. A Props Contract change (§3) requires a new version entry.

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
