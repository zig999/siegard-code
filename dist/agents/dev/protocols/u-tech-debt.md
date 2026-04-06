## Tech-debt Protocol

**Who creates:** the Orchestrator-Dev, when processing a `us-XX-delivery.md` that contains a "Generated tech debt" section.
**When:** immediately after QA approves the Story (before push).
**Where:** `{SESSIONS_DIR}/tech-debt.md` (created automatically on first occurrence).

Add to `{SESSIONS_DIR}/tech-debt.md`:
```markdown
## [US-XX] — [Title] — [date]
- **[Blocking | Non-blocking]** — [description]
- **Status:** Pending | Addressed in US-YY
```

- **Blocking:** prevents future Stories -> create a Refactoring P0 Story in the backlog **immediately**, before advancing to the next dependent Story. Use this inline format in backlog.md:
  ```
  ### US-[next number]: Refactoring — [debt description]
  **Epic:** [same Epic]  **Priority:** P0  **Type:** Refactoring
  **Acceptance criteria:**
  - [ ] Given [current state with debt], When [affected operation], Then [correct behavior after refactoring]
  **Dependencies:** US-XX (Story that generated the debt)
  **Status:** Backlog
  ```
- **Non-blocking:** record in tech-debt.md -> review at the end of each Epic and decide with the human whether to generate a dedicated Story or keep it as a record
