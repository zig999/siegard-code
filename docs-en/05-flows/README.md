# Execution Flows

Complete step-by-step workflows showing how commands chain together for different scenarios.

## Available flows

| Flow | Scenario | Commands |
|------|----------|----------|
| [Spec-first](spec-first.md) | New feature with full specification | `/u-spec` -> `/u-dev` |
| [Incremental improvement](incremental-improvement.md) | Small improvement without full redesign | `/u-improve` -> `/u-dev` |
| [Bug fix](bug-fix.md) | Bug documentation and correction | `/u-bug-report` -> `/u-dev` |
| [Reverse spec + triage](reverse-spec-triage.md) | Document existing project and evolve | `/u-reverse-spec` -> `/u-spec` -> `/u-spec-triage` -> `/u-dev` |
| [Reverse feedback](reverse-feedback.md) | Developer finds spec problem during implementation | `/u-spec` (feedback mode) |

## Flow selection guide

```
Need a new feature?
  -> Have specs? -> /u-dev
  -> No specs?  -> /u-spec -> /u-dev

Need a small change?
  -> /u-improve -> /u-dev
  -> Affects API? -> /u-improve -> /u-spec -> /u-dev

Found a bug?
  -> /u-bug-report -> /u-dev
  -> Reveals spec gap? -> /u-bug-report -> /u-spec -> /u-dev

Existing project without docs?
  -> /u-reverse-spec -> /u-spec -> /u-dev
```
