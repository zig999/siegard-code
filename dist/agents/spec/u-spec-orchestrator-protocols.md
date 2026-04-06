---
name: u-spec-orchestrator-protocols
description: Index of all protocols for the spec agent group. Loaded by the Orchestrator to locate specific protocols on demand.
user-invocable: false
---

# Spec Group Protocols

## Index

| Protocol | File | When to load |
|----------|------|--------------|
| Context Mounting | `protocols/u-spec-context-mounting.md` | Before activating any sub-agent — defines which files to pass |
| Fast-Track | `protocols/u-spec-fast-track.md` | When the demand is classified as minor/patch |
| Feedback Loop | `protocols/u-spec-feedback-loop.md` | When the implementation group reports a problem |
| Versioning | `protocols/u-spec-versioning.md` | When a version increment or Change Request needs to be opened |
| Cleanup | `protocols/u-spec-cleanup.md` | After handoff to the implementation group |
| Validation Triage | `protocols/u-spec-validation-triage.md` | When the human wants to resolve validation errors incrementally via `/u-spec-triage` |
| Handoff to Dev | `protocols/u-spec-to-dev-handoff.md` | When assembling and delivering the spec package to the implementation group |

## Usage rules

1. **Load on demand** — do not load all protocols at the start of the session
2. **One protocol at a time** — load only the one relevant to the current decision
3. **Do not duplicate content** — the protocol is the source of truth; the orchestrator references, does not copy
