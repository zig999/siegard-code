# Troubleshooting

Quick diagnostics for common problems.

## "Orchestrator doesn't detect {SPECS_DIR}"

**Check:** Verify that `.spec.md` files have `status: approved` in their headers. The orchestrator only recognizes specs with approved status.

## "Dev enters Error mode"

**Cause:** No input artifacts found (no approved specs, no `improve##.md`, no `bug##.md`).

**Fix:** Provide at least one input: run `/u-spec` for specs, `/u-improve` for improvements, or `/u-bug-report` for bugs.

## "Too many tokens consumed"

**Strategies:**
- Use short mode for agent reactivations
- Divide sessions (1 domain at a time, 1 Epic at a time)
- Use `/u-spec-triage` instead of fixing all validation errors at once
- For large backlogs (15+ Stories), the orchestrator auto-compresses logs

## "Story blocked without apparent reason"

**Check:** Review `backlog.md` for dependency declarations. A Story may be waiting for another Story to complete first.

## "Spec rejected repeatedly"

**Cause:** Requirements are too vague or ambiguous.

**Fix:** Make requirements more precise. Include specific use cases, expected behaviors, and edge cases.

## "Reverse spec incomplete"

**Cause:** Codebase too large for a single analysis pass.

**Fix:** Use Executive Summary mode, or limit scope to one module at a time.

## "Agent ignores instructions"

**Cause:** Token overflow -- the agent's context is saturated and it starts dropping instructions.

**Fix:** Reduce session scope. Process fewer domains or Stories per session.
