# Rework Protocol

Correction cycle triggered when QA rejects a Story.

## Flow

```
QA rejects -> Developer reactivated (short mode) -> Developer fixes -> QA retests
```

## How it works

1. QA generates rejection report in `us-XX-qa.md` with specific issues
2. Developer is reactivated in **short mode** (only receives delta + QA feedback)
3. Developer fixes the identified issues
4. QA retests the Story

## Limits

- Max **3 rework rounds** per Story
- If QA still rejects after 3 rounds, the Story is **blocked** and escalated to human
- Escalation includes all 3 QA reports for human review

## Short mode in rework

The Developer receives only:
- Agent identity
- Current Story reference
- QA rejection report with specific issues
- Instructions for what to fix

This keeps each rework cycle efficient (~2K tokens vs ~15K for full activation).
