---
name: u-ui-brief
description: Refine a raw UI request into a detailed, standardized, unambiguous brief ready to be handed to /u-spec (new demand) or /u-improve (change to an existing spec). This skill produces the structured input to the pipeline — it does not produce the specification itself and does not invoke leaf agents. Trigger when an author needs to prepare a UI request (component, screen, or flow) before running the spec pipeline.
user-invocable: true
argument-hint: "[target]"
---

# SKILL: UI Brief

## Purpose

Convert a raw UI request into a structured brief that the `/dist` spec agents can consume without making implicit decisions. The brief captures **intent**; the spec pipeline resolves intent into tokens, values, identifiers, and contracts.

This skill does not produce specifications. It produces the input a spec agent needs to produce a specification.

---

## Scope boundary — intent vs. resolution

This skill describes **intent**. Literal values (hex, px, ms), tokens, fonts, HTTP verbs, payloads, TypeScript types, and component library bindings are resolved by downstream layers, orchestrated by `/u-spec` or `/u-improve`.

| Layer | Entry point | Responsibility | Produces |
|---|---|---|---|
| `u-ui-brief` (this skill) | — | Intent: what the screen does, which states exist, how the user is served | Structured brief |
| Spec pipeline | `/u-spec` (new demand) | Domain contract, UC, BR, `openapi.yaml` operationIds, error catalog, front spec, design-system | `{domain}.spec.md`, `{domain}.back.md`, `feature.spec.md`, `component.spec.md` |
| Improve flow | `/u-improve` (modify existing spec) | Classifies impact, writes `improve_scope` block, delegates to `/u-spec` fast-track and/or `/u-dev` | Updated specs and/or implementation |

The brief is **never handed directly** to leaf agents (e.g., `u-spec-writer`, `u-spec-front`, `u-spec-back`, `u-fe-ui`, `u-ui-design`). Those are invoked internally by the orchestrators behind `/u-spec` (`u-spec-orchestrator`) and `/u-improve`, which manage session logs, mode detection, approval gates, validation, and handoff to `/u-dev`.

**Authoring rule:** if a value can be resolved by a downstream layer, describe it by intent — never by literal. Say `primary-action` — never `#2563EB`. Say `short-feedback` — never `150ms`. The downstream pipeline resolves per R1–R25 and the project design system.

---

## Core principles

- **Describe behavior, not subjective appearance.** States, transitions, conditions — never "looks good".
- **Zero ambiguity.** If a downstream agent must decide something the author could have declared, the brief failed.
- **Separate the five layers.** Layout, state, behavior, feedback, data — never mixed in one description.
- **Semantic over literal.** Describe intent; let tokens and values resolve downstream.
- **General to specific.** Screen context → components → states → integration contracts.
- **Structure over narrative.** Tables and enumerations over prose.

---

## Required structure

### 1. Overview

One or two sentences describing the functional purpose. Answer: *what does this UI do for the user?*

### 2. Access context

| Field | Value |
|---|---|
| Entry point | how the user reaches this UI |
| Precondition | `public` \| `authenticated` \| `role:{name}` \| `state:{name}` |
| Prior state required | — or named prior screen/flow |
| Route intent | semantic route description (not a final path) |

### 3. Layout and composition

Fill each row. Every answer is semantic; downstream agents resolve to tokens.

| Aspect | Declare |
|---|---|
| Visual hierarchy | single dominant element + role of each secondary element + reason |
| Groupings | which elements form units; which are standalone |
| Within-group spacing | `tight` \| `comfortable` \| `generous` |
| Between-group spacing | `section-gap-small` \| `section-gap-medium` \| `section-gap-large` |
| Density | `compact` \| `comfortable` \| `generous` |
| Alignment axis | `left` \| `center` \| `right` \| `justified-axis` per region |
| Responsive intent | what restructures on mobile vs. desktop (layout shape, not px) |

Do not prescribe `max-width` or padding in px. Describe the column width as `narrow`, `standard`, or `full`.

### 4. Components

One block per component.

#### 4.1 Identification

| Field | Value |
|---|---|
| Name | semantic name |
| Role | functional purpose in this screen |
| Scope | `global` (reusable) \| `feature` (local) |
| Classification | `new` \| `existing` \| `variant-of:{name}` |
| Component spec expected | `yes` (appears in 2+ features or has internal logic) \| `no` |

#### 4.2 Default appearance (intent)

Tabular only. No literal values.

| Attribute | Semantic intent |
|---|---|
| Surface | `inline` \| `input` \| `card` \| `elevated-card` \| `full-bleed` |
| Border | `default` \| `emphasized` \| `none` |
| Text role | `display` \| `heading` \| `subheading` \| `body` \| `label` \| `caption` \| `code` |
| Weight intent | `normal` \| `emphasized` \| `metric-bold` |
| Icon | `none` \| `leading:{purpose}` \| `trailing:{purpose}` |
| Placeholder | exact user-facing text, if applicable |
| Radius intent | `square` \| `subtle` \| `standard` \| `prominent` \| `pill` |
| Elevation intent | `flat` \| `raised` \| `floating` \| `modal-level` \| `overlay-level` |

#### 4.3 States

One row per state. Declare only the semantic delta from default.

| State | Trigger | Semantic delta | Interactivity |
|---|---|---|---|
| default | initial render | — | full |
| hover | pointer over | emphasized border | full |
| focus | keyboard or pointer focus | focus ring present (R15 mandatory) | full |
| active | press / click instant | pressed affordance | full |
| filled | has value | — | full |
| error | validation fails | error border + inline helper text (R16, R20) | full |
| success | validation succeeds | success affordance | full |
| disabled | prop or context | reduced emphasis; no interaction | none |
| loading | async in progress | inline indicator (R19) | partial |

**Mandatory:** every interactive element must declare all five states `default / hover / focus / active / disabled` — R15. Declaring them as identical to default is valid; omitting them is not.

#### 4.4 Interactions

Format: `[trigger] → [immediate action] → [resulting state]`.

Example (semantic only):

- user focuses field → field enters `focus`
- `blur` with invalid value → validation runs → state `error` with message `{exact user-facing text}`
- user edits field in `error` → `error` persists during typing → revalidation on next `blur`

#### 4.5 Implementation contract (intent)

| Field | Value |
|---|---|
| Identifier | kebab-case id |
| Base type | `input-text` \| `button` \| `select` \| `card` \| `modal` \| ... |
| Props intended | semantic prop names + short purpose — no TypeScript types |
| Events intended | callback purposes — not payload types |
| External dependencies | named intent (e.g., `email validator`, `list of categories`) — not libraries |

Downstream `component.spec.md` resolves these to TypeScript types and `@/` import paths.

---

### 5. Data integration

Declare intent. Do not declare HTTP method, path, status codes, or payload JSON.

| Field | Value |
|---|---|
| Domain intended | `auth`, `catalog`, `billing`, ... |
| Operation | `create` \| `read` \| `update` \| `delete` \| `list` \| `search` |
| Fields in (semantic) | user-facing names of inputs |
| Fields out (semantic) | names the UI needs from the response |
| On success | `redirect:{target}` \| `inline-update` \| `toast:{tone}` \| `modal:{name}` |
| On error (per class) | one row per error class the UI distinguishes |
| Endpoint status | `existing` \| `endpoint_missing` \| `unknown` |

If `endpoint_missing`, the spec agent records it in `tc-XX-backend-pending-items.md` — do not fabricate an operationId here.

---

### 6. User feedback

Every user-visible signal gets a row. Three dimensions are mandatory.

| Dimension | Declare |
|---|---|
| What | kind (`toast` \| `inline` \| `banner` \| `modal` \| `redirect`) + tone (`success` \| `error` \| `warning` \| `info`) |
| Where | position intent (`top-right floating`, `below field`, `above form`, `full-screen blocking`) — not px |
| When | trigger + duration intent (`instant`, `auto-dismiss-short`, `auto-dismiss-long`, `user-dismissed`, `persistent`) |

Error message content: if an exact user-facing text is decided, quote it verbatim. Otherwise write `text-source: §6 of feature.spec.md` — the spec agent will carry the canonical text.

---

### 7. Flows (when multi-screen)

| Field | Value |
|---|---|
| Happy path steps | numbered; one sentence each; user action or system action |
| Branches | `{step}.{letter}: {condition} → {outcome}` |
| Transition intent | `instant` \| `short-crossfade` \| `slide-forward` \| `slide-back` |
| Persistence between steps | `in-memory` \| `url-param` \| `session` \| `local` \| `none` |
| Reload behavior | `restart-from-step-1` \| `resume-from-last-step` \| `block-until-complete` |

The spec agent resolves transition intent to the R23 duration scale.

---

### 8. Mandatory behavior decisions

Every row must be answered. Unanswered rows set `ready_for_spec_pipeline: false`.

| Decision | Options |
|---|---|
| Debounce on validation / search | `none` \| `short` \| `medium` |
| Retry on network failure | `none` \| `auto-once` \| `auto-three` \| `user-prompted` |
| Optimistic update | `yes` \| `no` |
| Cache on read | `none` \| `inherit` \| `long-lived` \| `on-focus-revalidate` |
| Duplicate clicks during async | `block-until-response` \| `queue` \| `ignore` |
| Network error vs API error | `same-feedback` \| `differentiated` |

---

### 9. Edge cases

Answer each. `not-applicable` is valid; silence is not.

- Empty result / zero records
- API error with generic body
- Slow response (perceived long)
- Malformed or unexpected API shape
- User navigates away during async
- Rapid repeated action or double-click
- Unauthorized session mid-flow
- Offline or no network

---

### 10. Fidelity level

| Level | Meaning |
|---|---|
| `low` | Structure and behavior correct; visual polish deferred |
| `medium` | Full state coverage + design-system tokens applied |
| `high` | Pixel-perfect; all micro-interactions; design system fully calibrated |

---

## Controlled vocabulary — intent terms

Use these canonical intent terms. The spec pipeline resolves each to concrete tokens or values per R1–R25 and the project design system.

| Category | Intent terms | Resolved against |
|---|---|---|
| Color role | `primary-action`, `danger-action`, `data-highlight`, `neutral-body`, `neutral-muted`, `border-default`, `border-focus`, `border-error`, `surface`, `elevated-surface` | `tokens.md` |
| Spacing | `tight`, `comfortable`, `generous`, `section-gap-small`, `section-gap-medium`, `section-gap-large` | R1 scale (4/8/12/16/24/32/48/64) |
| Typography role | `display`, `heading`, `subheading`, `body`, `body-sm`, `label`, `caption`, `code` | R4 scale (12/14/16/20/24/30) |
| Motion | `instant`, `short-feedback`, `medium-transition`, `long-enter` | R23 scale (100/200/300/500ms) |
| Radius | `square`, `subtle`, `standard`, `prominent`, `pill` | R13 |
| Elevation | `flat`, `raised`, `floating`, `modal-level`, `overlay-level` | `tokens.md` |
| Density | `compact`, `comfortable`, `generous` | R3 / R17 |
| Feedback tone | `success`, `error`, `warning`, `info` | R20 |

---

## Anti-patterns — forbidden in a brief

These violate the intent/resolution boundary and must not appear in a brief produced by this skill.

| Anti-pattern | Reason |
|---|---|
| Hex codes (e.g., `#2563EB`) | Color is resolved by `tokens.md` — R9 |
| Pixel dimensions for spacing, size, or max-width | Resolved by R1 / R3 / R18 |
| Explicit ms durations | Resolved by R23 |
| Explicit `font-size` in px | Resolved by R4 |
| HTTP method + path inline | Owned by `openapi.yaml` per `feature.spec.md §1` |
| Payload JSON or response body | Contract lives in the schema |
| Component-library binding (e.g., `<Button variant="primary">`) | Resolved by the implementation pipeline (`/u-dev`), not by the brief |
| Subjective adjectives (`nice`, `clean`, `modern`, `appropriate`, `fast`, `smooth`) | No deterministic resolution |
| Invented UI-NN / FL-NN / TC-XX identifiers | Spec pipeline mints these — brief uses semantic labels only |

---

## Handoff envelope (mandatory output)

Every brief produced by this skill ends with this YAML block. The Markdown body is human-readable; this block is the structured handoff consumed by downstream agents.

```yaml
ui-brief:
  produced_by: u-ui-brief
  timestamp: <ISO-8601>
  language: en
  layer: ephemeral

  request_summary: <one sentence>

  handoff:
    target_command: /u-spec | /u-improve   # /u-spec for new demand; /u-improve when modifying an existing spec
    reason: <short justification — e.g., "new feature, no prior spec" | "adjusts existing ui-epic-04 states">
    # Downstream routing is owned by the target command's orchestrator.
    # Do NOT invoke leaf agents directly (u-spec-writer, u-spec-front, u-spec-back, u-fe-ui, u-ui-design).

  screens_intended:
    - name: <SemanticScreenName>
      route_intent: <semantic path description>
      access_precondition: public | authenticated | role:<name> | state:<name>
      feature_name_intent: <kebab-case>
      persona_intent: <role name from CLAUDE.md if known>

  states_intended:
    - screen: <SemanticScreenName>
      labels: [idle, loading, success, error, empty, ...]   # semantic; spec agent assigns UI-NN

  flows_intended:
    - id_intent: <semantic flow name>
      spans_screens: [<SemanticScreenName>, ...]
      step_labels: [<entry>, <validation>, <success>, <error-branch>]

  data_intent:
    - domain: <domain-name>
      operation: create | read | update | delete | list | search
      fields_in: [<semantic names>]
      fields_out: [<semantic names>]
      endpoint_status: existing | endpoint_missing | unknown

  components_intended:
    - id: <kebab-case>
      base_type: <input-text | button | select | card | modal | ...>
      scope: global | feature
      classification: new | existing | variant-of:<name>
      has_component_spec_expected: true | false | unknown

  behavior_decisions:
    debounce: none | short | medium
    retry: none | auto-once | auto-three | user-prompted
    optimistic_update: true | false
    cache: none | inherit | long-lived | on-focus-revalidate
    duplicate_clicks: block-until-response | queue | ignore
    error_differentiation: same-feedback | differentiated

  edge_cases:
    empty_result: <answer | not-applicable>
    api_error_generic: <answer>
    slow_response: <answer>
    malformed_response: <answer>
    navigate_away_during_async: <answer>
    rapid_repeated_action: <answer>
    unauthorized_mid_flow: <answer>
    offline: <answer>

  fidelity: low | medium | high

  design_system_status: present | missing | unknown

  open_questions:
    - id: OQ-01
      topic: <short>
      blocking: true | false

  ready_for_spec_pipeline: true | false
  blocking_reasons: []   # populated when ready_for_spec_pipeline=false
```

---

## Final checklist

- [ ] Overview and access context declared
- [ ] Layout declares hierarchy, groupings, spacing intent, density, responsive intent — no px, no hex
- [ ] Every component has default appearance (intent) + all five R15 states (`default/hover/focus/active/disabled`) + `filled/error/success/loading` as applicable
- [ ] State changes declared as semantic delta from default only
- [ ] Implementation contract at intent level — no TypeScript types, no library bindings
- [ ] Data integration by domain + operation + semantic fields — no HTTP/JSON
- [ ] Every user-feedback item has `what / where / when`
- [ ] All mandatory behavior decisions answered
- [ ] All edge cases answered (including `not-applicable`)
- [ ] Fidelity level declared
- [ ] Vocabulary is semantic throughout — no hex / px / ms literals, no invented UI-NN / FL-NN / TC-XX
- [ ] Handoff YAML block present and populated
- [ ] `ready_for_spec_pipeline: true` or `blocking_reasons` explains why not
