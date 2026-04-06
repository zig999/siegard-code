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
| Epic Integration | `.claude/agents/dev/protocols/u-be-epic-integration.md` | When all Stories in an Epic reach `Done` |
| Rework (feedback loop) | `.claude/agents/dev/protocols/u-rework.md` | When QA rejects a Story |
| Tech-debt | `.claude/agents/dev/protocols/u-tech-debt.md` | When `us-XX-delivery.md` contains "Generated tech debt" |
| Push and merge | `.claude/agents/dev/protocols/u-push-merge.md` | After QA approves a Story |
| Cleanup `_temp/` | `.claude/agents/dev/protocols/u-cleanup.md` | After Planner, Story, or Epic completion |
| Improve Mode | `.claude/agents/dev/protocols/u-improve-mode.md` | When Improve mode is detected (improve##.md present) |
| Bug Mode | `.claude/agents/dev/protocols/u-bug-mode.md` | When Bug mode is detected (bug##.md present) |
