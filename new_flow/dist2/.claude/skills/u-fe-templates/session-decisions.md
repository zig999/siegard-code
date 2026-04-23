---
name: session-decisions
description: Cross-session persistent log for escalation resolutions, architectural decisions, and implementation patterns made by orchestrator and developer agents. Prevents repeated mistakes across sessions.
user-invocable: false
---

# Session Decisions Log

> Path: `$SESSION_DIR/session-decisions.md`
> Layer: semi-permanent — versioned in repo, consumed across sessions. Never ephemeral.
> Format: append-only. Orchestrator reads last 20 entries on session start. Never truncate — rotate to `_archive/session-decisions-archive-YYYY.md` when exceeding 300 entries.

---

## Log

| ID | Session | Date | Type | Task/Domain | Context | Resolution | Status |
|----|---------|------|------|-------------|---------|------------|--------|

---

## Field definitions

| Field | Values | Description |
|-------|--------|-------------|
| `ID` | `DEC-NN` | Sequential decision identifier, project-scoped (DEC-01, DEC-02, ...) |
| `Session` | `<workflow_id>` | Session identifier (workflow_id from orchestrator) |
| `Date` | `YYYY-MM-DD` | Date of entry |
| `Type` | `escalation` \| `arch-decision` \| `spec-gap` \| `triage-resolution` \| `qa-root-cause` | Classification |
| `Task/Domain` | `TC-XX` \| `{domain}` \| `global` | Affected scope |
| `Context` | 1-sentence | What condition triggered this entry |
| `Resolution` | 1-sentence | What was decided or learned |
| `Status` | `active` \| `superseded` \| `reverted` | Current validity |

---

## Usage rules

**Orchestrator writes on:**
- Agent escalation to human (type: `escalation`)
- Architectural decision with project-wide impact (type: `arch-decision`)
- Spec gap confirmed during implementation (type: `spec-gap`)
- Triage resolution that closes a validation error (type: `triage-resolution`)
- QA root-cause finding that reveals a systemic pattern (type: `qa-root-cause`)

**Orchestrator reads on:**
- Session start — read last 20 entries; log to session header which active entries apply

**Developer writes on:**
- None — read-only for developer agents

**Supersede rule:** when a previous decision no longer applies, add a new row with `Status: superseded` referencing the original date in Context.
