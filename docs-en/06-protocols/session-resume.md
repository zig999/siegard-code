# Session Resume Protocol

Resume an interrupted session from the exact stopping point.

## When triggered

The orchestrator detects an existing `log-orchestrator-*.md` file with incomplete stages.

## How it works

1. Read the orchestrator log file
2. Reconstruct pipeline state from the log and disk artifacts
3. Identify the last completed step
4. Emit a resume plan (what was done, what remains)
5. Wait for human confirmation
6. Continue from the next incomplete step

## What is preserved

- All files generated to disk (specs, code, delivery files)
- Story status in backlog.md
- Intermediate artifacts (QA reports, delivery files)
- Orchestrator log with all recorded events

## What is lost

- In-memory context (conversation state)
- Agent-specific context from prior activations
- Any unfinished operations that were not persisted

## Rules

- **Never re-execute completed steps** -- Trust the log and disk artifacts
- **Always emit resume plan before proceeding** -- Human must confirm
- **Verify incomplete files** -- Check if any file was left in a partial state
- **Reload necessary context** -- Since in-memory state is lost, remount context for the next agent
