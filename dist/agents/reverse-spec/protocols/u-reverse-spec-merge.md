---
name: u-reverse-spec-merge
description: Smart merge protocol between reverse-engineered specs and existing specs. Compares, identifies gaps and divergences, and applies changes with human confirmation.
user-invocable: false
---

# Protocol: Smart Spec Merge

## When to use
- When `{SPECS_DIR}/` already exists and the Orchestrator detects merge mode
- When the user re-runs `/u-reverse-spec` on an already-documented project

---

## Principles

1. **Non-destructive** — never overwrite existing specs without confirmation
2. **Existing spec prevails** — if there is a conflict between an existing (human-authored) spec and a generated (reverse-engineered) spec, the existing one prevails
3. **Additive only** — the merge adds what is missing, it does not remove what exists
4. **Divergences are flagged** — not automatically resolved

---

## Process

### Step 1: Inventory existing specs

List all artifacts in `{SPECS_DIR}/`:

```markdown
## Existing Specs Inventory

| Domain | openapi.yaml | .spec.md | .back.md | Screens | Flows | Status |
|--------|-------------|----------|----------|---------|-------|--------|
| {dom}  | {yes/no}    | {yes/no} | {yes/no} | {N}     | {N}   | {status} |
```

### Step 2: Compare with analysis

For each domain found by the Analyzer:

#### 2.1 New domain (does not exist in specs/)
- Classify as **ADDITION**
- Generate specs normally (new mode)

#### 2.2 Existing domain — compare artifacts

**openapi.yaml:**
- Compare endpoints: which exist in the code but not in the spec
- Compare schemas: which fields exist in the code but not in the schema
- Register as **NEW_ENDPOINTS** or **NEW_FIELDS**

**{domain}.spec.md:**
- Compare UCs: logic in the code without a corresponding UC
- Compare business rules: validations in the code without a corresponding BR
- Register as **NEW_UCS** or **NEW_BRS**

**{domain}.back.md:**
- Compare data model: fields in the entity not in the spec
- Compare BRs: validations in the code without a corresponding BR
- Compare events: emitters without a corresponding EV
- Register as **NEW_FIELDS**, **NEW_BRS**, **NEW_EVENTS**

**screens / flows:**
- Compare screens: pages in the code without a screen.md
- Compare flows: navigations without a flow.md
- Register as **NEW_SCREENS**, **NEW_FLOWS**

### Step 3: Classify divergences

For each item that exists in BOTH (spec and code) but with different values:

| Type | Description | Action |
|------|-------------|--------|
| **TYPE_DIVERGENCE** | Field has a different type in code vs spec | Flag to human |
| **RULE_DIVERGENCE** | Validation in code differs from BR in spec | Flag to human |
| **ROUTE_DIVERGENCE** | Endpoint has a different route in code vs spec | Flag to human |
| **STATUS_DIVERGENCE** | State machine has different states | Flag to human |
| **DEPRECATED** | Spec references something that no longer exists in code | Flag to human |

### Step 4: Generate merge report

Present to the human:

```markdown
## Merge Report — Reverse Engineering

### Summary

| Type | Count |
|------|-------|
| New domains | {N} |
| New endpoints | {N} |
| New fields | {N} |
| New UCs | {N} |
| New BRs | {N} |
| New screens | {N} |
| Divergences | {N} |
| Deprecated items | {N} |

### Proposed Additions

#### Domain: {name}

**New endpoints:**
| Verb | Route | operationId | Description |
|------|-------|-------------|-------------|

**New entity fields:**
| Entity | Field | Type | Description |
|--------|-------|------|-------------|

**New UCs:**
| ID | Name | Endpoint |
|----|------|----------|

**New BRs:**
| ID | Description | Related UC |
|----|-------------|------------|

### Divergences Found

| # | Type | Current Spec | Current Code | Recommendation |
|---|------|-------------|-------------|----------------|
| 1 | {type} | {value in spec} | {value in code} | {update spec / keep spec / investigate} |

### Possibly Deprecated Items

| # | Artifact | Reference | Reason |
|---|----------|-----------|--------|
| 1 | {file} | {UC/BR/endpoint} | Not found in code |

---

Which actions to apply?

1. Apply ALL additions (excluding divergences)
2. Apply selected additions — [list numbers]
3. Generate report only without applying
4. Cancel
```

### Step 5: Apply confirmed changes

For each confirmed change:

#### Adding endpoints to existing openapi.yaml
- Insert new path in the correct location (alphabetical order)
- Add new schemas in components.schemas
- Increment the openapi minor version

#### Adding UCs to existing .spec.md
- Add after the last existing UC (maintain sequential numbering)
- Add corresponding alternative flows
- Update the errors section if needed
- Add a Changelog entry

#### Adding BRs to existing .back.md
- Add after the last existing BR
- Reference the corresponding UC
- Add a Changelog entry

#### New screens/flows
- Create new screen.md / flow.md files
- Do not modify existing screens/flows

### Step 6: Mark as review and create marker

All modified artifacts must have:
- Status updated to `review` (if it was `approved`, flag that it was changed)
- Changelog note: `Type: merge (reverse-eng) | Description: Added items found in code analysis`

Create marker `{SPECS_DIR}/_meta/merge-pending-review.md` so the next `/u-spec` detects that specs need formal review:

```markdown
# Merge Pending Review
> Generated by: /u-reverse-spec (merge mode) | Date: {YYYY-MM-DD}

## Modified Domains
| Domain | Items added | Flagged divergences |
|--------|-------------|---------------------|
| {domain} | {N} endpoints, {N} UCs, {N} BRs | {N} divergences |

## Required Action
Run `/u-spec [SPECS_DIR]` for formal review. The Spec Orchestrator will enter merge review mode.
```

> This marker is removed after formal review approves all domains.

---

## Safety Rules

1. **NEVER remove** content from existing specs
2. **NEVER change status** from `approved` to `draft` without confirmation
3. **NEVER resolve divergences** automatically — always flag to the human
4. **Maintain backup** — when modifying an existing file, record the previous version in the Changelog
5. **Non-conflicting prefixes** — when adding UC-NN or BR-NN, use the next available number (do not reuse removed IDs)
