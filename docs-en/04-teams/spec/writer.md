# Spec Writer

First agent in the spec pipeline. Creates the initial API contract and specification document.

## Responsibilities

- Analyze the incoming requirement
- Create folder structure for new domains
- Write `openapi.yaml` (API contract)
- Write `{domain}.spec.md` (use cases, business rules, state machines)
- Register error codes in the global catalog
- Update `openapi.root.yaml` aggregator

## Operating modes

| Mode | Behavior |
|------|----------|
| **New domain** | Greenfield -- create all artifacts from scratch |
| **Existing domain** | Evolution -- add/modify within existing structure |
| **Change request** | Targeted modification to existing spec |
| **Reverse feedback** | Correct spec based on Developer feedback |

## Inputs

- Requirement description (from user)
- `_global/conventions.md` -- Project conventions
- `_global/error-codes.md` -- Error code catalog
- `_global/glossary.md` -- Domain glossary
- Spec templates from `_templates/`

## Mandatory rules

- Every Use Case (UC-NN) must have a corresponding endpoint in `openapi.yaml`
- Every `error.code` must be registered in the global error catalog
- Schema definitions must include examples
- No ambiguous terms -- all domain-specific terms must be in the glossary

## Short mode reactivation

When reactivated after a Reviewer rejection, the Writer receives only:
- Agent identity and current task
- Reviewer's rejection report with specific issues
- Delta from the previous activation

This reduces context from ~15K tokens to ~2K tokens.

## Output

- `{SPECS_DIR}/domains/{domain}/openapi.yaml`
- `{SPECS_DIR}/domains/{domain}/{domain}.spec.md`
- Updated `_global/error-codes.md`
- Updated `openapi.root.yaml`
