# Spec Artifacts

Structure and purpose of all specification files.

## Directory structure

```
{SPECS_DIR}/
  _global/
    conventions.md          # Project conventions
    error-codes.md          # Error code catalog
    glossary.md             # Domain glossary
  _templates/               # Spec templates
  _meta/
    origin-reverse-spec.md  # Reverse spec origin marker
  _validation/
    {domain}-validation.md  # Persisted validation reports
  decisions.md              # Architecture decision log (DEC-NN format)
  domains/
    {domain}/
      openapi.yaml          # API contract
      {domain}.spec.md      # Use cases and business rules
      back/
        {domain}.back.md    # Backend technical spec
  front/
    front.md                # Global frontend spec
    design-system/          # Design system reference (5 files)
    features/
      {feature}.feature.spec.md   # Per-feature/route UI spec
    components/
      {name}.component.spec.md    # Shared component contract (conditional)
    _flows/
      {flow}.flow.md        # Navigation flow spec
  openapi.root.yaml         # Root OpenAPI aggregator
```

## What each artifact answers

| Artifact | Answers |
|----------|---------|
| `openapi.yaml` | What endpoints exist? What are the request/response schemas? |
| `{domain}.spec.md` | What are the use cases (UC-NN)? Business rules? State machines? |
| `{domain}.back.md` | How should the backend implement this? Data model? Events? |
| `front.md` | What is the global frontend architecture? Permitted libraries? |
| `{feature}.feature.spec.md` | What does this route (URL) look like? States? BDD invariants? Which components does it need? |
| `{name}.component.spec.md` | What is the Props Contract for this shared component? What states and events does it have? |
| `{flow}.flow.md` | How does navigation work between features? |
| `decisions.md` | What non-obvious architectural decisions were made and why? |

## Identifier prefixes

| Prefix | Meaning | Defined in |
|--------|---------|-----------|
| UC-NN | Use Case | `.spec.md` |
| BR-NN | Business Rule | `.back.md` |
| ST-NN | State Machine state | `.back.md` |
| EV-NN | Domain Event | `.back.md` |
| FEAT-NN | Feature (frontend route spec) | `.feature.spec.md` header |
| UI-NN | UI State (within a feature) | `.feature.spec.md §2` |
| FL-NN | Navigation Flow | `.flow.md` |
| DEC-NN | Architecture Decision | `decisions.md` |
| CR-NN | Change Request | change-request process |

## Feature spec granularity rule

**1 feature = 1 URL/route.**

- Modals without URL change → states of the same feature (§2), not a separate spec
- Multi-step wizards that change URL → multiple features linked by a `flow.md`
- A feature can and should consume endpoints from multiple domains

## Component spec creation criterion

Create `{name}.component.spec.md` only when:
- The component is used in **2+ features**, OR
- The component has complex internal logic (own state + side effects + non-trivial transformations)

Simple single-use components → document directly inside the `feature.spec.md` that uses them.

## decisions.md entry format

```markdown
## DEC-NN — {short title}
**Date:** YYYY-MM-DD
**Status:** Active | Superseded by DEC-XX | Reverted
**Context:** {1-2 sentences}
**Decision:** {1-3 sentences}
**Alternatives considered:** {bullet list}
**Rationale:** {1-2 sentences}
**Impact on specs:** {files affected}
```

Superseded decisions are never edited — a new DEC-NN is created and the old entry is marked "Superseded by DEC-XX".
