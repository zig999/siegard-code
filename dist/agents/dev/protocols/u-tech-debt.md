## Tech-debt Protocol

**Who creates:** the Orchestrator-Dev, when processing a `tc-XX-delivery.md` that contains a "Generated tech debt" section.
**When:** immediately after QA approves the Task Contract (before push).
**Where:** `{SESSIONS_DIR}/tech-debt.md` (created automatically on first occurrence).

Add to `{SESSIONS_DIR}/tech-debt.md`:
```markdown
## [TC-XX] — [Title] — [date]
- **[Blocking | Non-blocking]** — [description]
- **Status:** Pending | Addressed in US-YY
```

- **Blocking:** prevents future Task Contracts -> create a Refactoring P0 Task Contract in the backlog **immediately**, before advancing to the next dependent Task Contract. Use this inline format in backlog.md:
  ```
  ### TC-[next number]: Refactoring — [debt description]
  **Epic:** [same Epic]  **Priority:** P0  **Type:** Refactoring
  **Acceptance criteria:**
  - [ ] Given [current state with debt], When [affected operation], Then [correct behavior after refactoring]
  **Dependencies:** TC-XX (Task Contract that generated the debt)
  **Status:** Backlog
  ```
- **Non-blocking:** record in tech-debt.md -> review at the end of each Epic and decide with the human whether to generate a dedicated Task Contract or keep it as a record
