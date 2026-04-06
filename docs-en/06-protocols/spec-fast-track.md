# Spec Fast-Track Protocol

Simplified spec pipeline for minor and patch changes.

## When triggered

| Change type | Classification | Example |
|-------------|---------------|---------|
| New endpoint | Minor | Adding a new API route |
| Optional field | Minor | Adding an optional query parameter |
| Typo/clarification | Patch | Fixing a description in the spec |

## Pipeline

```
Writer -> Reviewer (delta-focused) -> Validator (incremental)
```

## What is skipped

- **Back Spec Agent** -- Skipped if the change does not impact `.back.md` artifacts
- **Front Spec Agent** -- Skipped if the change does not impact screen/flow artifacts
- **Full review** -- Reviewer focuses only on changed areas, not the entire spec

## When NOT to use fast-track

- Breaking changes (removing endpoints, changing required field types)
- Changes that affect multiple domains
- Changes that require new screens or flows

These require the full spec pipeline.
