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
  domains/
    {domain}/
      openapi.yaml          # API contract
      {domain}.spec.md      # Use cases and business rules
      back/
        {domain}.back.md    # Backend technical spec
  front/
    front.md                # Global frontend spec
    design-system/          # Design system reference (5 files)
    screens/
      {screen}.screen.md    # Per-screen UI spec
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
| `front.md` | What is the global frontend architecture? |
| `{screen}.screen.md` | What does this screen look like? What states does it have? |
| `{flow}.flow.md` | How does navigation work between screens? |

## Identifier prefixes

| Prefix | Meaning | Defined in |
|--------|---------|-----------|
| UC-NN | Use Case | `.spec.md` |
| BR-NN | Business Rule | `.back.md` |
| ST-NN | State Machine state | `.back.md` |
| EV-NN | Domain Event | `.back.md` |
| UI-NN | UI State | `.screen.md` |
| FL-NN | Navigation Flow | `.flow.md` |
