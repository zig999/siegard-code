# Short Mode Protocol

Reduced context reactivation for agents that are activated more than once in the same session.

## Purpose

When an agent is reactivated (e.g., Developer after QA rejection, Writer after Reviewer rejection), loading the full context again wastes tokens. Short mode provides only the delta needed.

## When triggered

- 2nd or subsequent activation of the same agent in the same session
- Primarily used during rework cycles

## Context reduction

| | Full activation | Short mode |
|-|----------------|------------|
| **Tokens** | ~15K | ~2K |
| **Contains** | Full agent identity + all specs + all context | Agent identity + current task + delta only |

## Short mode context includes

1. Agent identity (role and rules)
2. Current task description
3. Feedback from the rejecting agent (QA report, Reviewer report, etc.)
4. Only the differences from the first activation
5. Specific instructions for what to fix

## Short mode context excludes

- Full spec documents (already loaded in first activation)
- Templates and conventions (already known)
- Glossary and error catalog (already known)
- Anything unchanged since first activation
