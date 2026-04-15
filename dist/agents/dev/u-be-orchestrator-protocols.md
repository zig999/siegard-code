---
name: u-be-orchestrator-protocols
description: Index of protocol files. Each protocol is a separate file loaded on demand by orchestrator-core.
user-invocable: false
---

# Orchestrator-Dev — Protocols (Backend)

> **Do not load this entire file.** Each protocol is a separate file. Load only the protocol needed for the current decision.

## Protocol Index

| Protocol | File | When to load |
|----------|------|--------------|
| Context — Planner | `.claude/agents/dev/protocols/u-be-context-mounting-planner.md` | When activating the Planner |
| Context — Spec Consumption | `.claude/agents/spec/protocols/u-spec-to-dev-handoff.md` | When Spec-first mode is detected — defines how to consume approved specs |
| Context — Developer | `.claude/agents/dev/protocols/u-be-context-mounting-developer.md` | When activating the Developer |
| Context — QA & Docs | `.claude/agents/dev/protocols/u-be-context-mounting-qa.md` | When activating QA & Docs |
| Short mode | `.claude/agents/dev/protocols/u-context-mounting-short-mode.md` | When activating any sub-agent for the 2nd+ time in the session |
| Epic Integration | `.claude/agents/dev/protocols/u-be-epic-integration.md` | When all Task Contracts in an Epic reach `Done` |
| Security Review | `.claude/agents/dev/u-security-reviewer.md` | After QA full-mode approves a Task Contract (before push/merge) |
| Architecture Review | `.claude/agents/dev/u-architecture-reviewer.md` | After Epic integration QA approves |
| Rework (feedback loop) | `.claude/agents/dev/protocols/u-rework.md` | When QA rejects a Task Contract |
| Tech-debt | `.claude/agents/dev/protocols/u-tech-debt.md` | When `tc-XX-delivery.md` contains "Generated tech debt" |
| Push and merge | `.claude/agents/dev/protocols/u-push-merge.md` | After QA approves a Task Contract |
| Cleanup `_temp/` | `.claude/agents/dev/protocols/u-cleanup.md` | After Planner, Task Contract, or Epic completion |
| Improve Mode | `.claude/agents/dev/protocols/u-improve-mode.md` | When Improve mode is detected (improve_scope block in log) |
| Bug Mode | `.claude/agents/dev/protocols/u-bug-mode.md` | When Bug mode is detected (bug##.md present) |

## Blocked response schema

When any sub-agent cannot proceed, it **must** use the canonical template — never invent missing data, never return partial results:

```
Template: .claude/skills/u-shared-templates/blocked-report.yaml
```

The orchestrator treats `status: blocked` as a hard stop: do not advance to the next stage, do not infer missing inputs, escalate to human if `resolution.escalate_to: human`.
