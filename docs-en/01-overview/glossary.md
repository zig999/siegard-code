# Glossary

Alphabetical reference of technical terms used across the system.

| Term | Definition |
|------|-----------|
| **Back Spec Agent** | Agent that produces the backend technical specification (`.back.md`) per domain after the spec is approved |
| **BR-NN** | Business Rule identifier (e.g., BR-01, BR-02). Defined in `.back.md` and traced to Use Cases |
| **Cleanup** | Protocol that archives temporary artifacts to `_temp/` after consumption (never deletes) |
| **Context mounting** | Protocol that selectively loads only the artifacts each agent needs, minimizing token usage |
| **{SESSIONS_DIR}/{SESSION}/** | Working directory for the current session |
| **Epic** | Group of related User Stories that together deliver a coherent feature increment |
| **Epic integration** | Protocol for cross-Story validation when all Stories in an Epic are complete |
| **EV-NN** | Domain Event identifier (e.g., EV-01). Defined in `.back.md` for async communication |
| **E2E Validation** | Cross-domain integration check in fullstack sessions, verifying that FE correctly consumes BE endpoints |
| **Escalation** | Automatic handoff to human when an agent exceeds its retry limit (e.g., 3 rejections) |
| **Fast-track** | Simplified spec pipeline for minor/patch changes that skips Back/Front agents when not impacted |
| **Feedback reverso** | Reverse feedback -- when a Developer discovers a problem in the spec during implementation |
| **FL-NN** | Navigation Flow identifier (e.g., FL-01). Defined in `.flow.md` for screen transitions |
| **Front Spec Agent** | Agent that produces frontend specs (screens, flows). Runs after ALL Back Specs are valid |
| **Fullstack Meta-Orchestrator** | Coordinator for `domain: fullstack` projects. Runs BE phase, generates BE→FE handoff, then runs FE phase |
| **Handoff** | Formal artifact transfer protocol between Spec and Dev teams |
| **handoff-be-to-fe.md** | Artifact generated after Phase 1 (BE) in fullstack sessions, listing implemented endpoints and deviations |
| **Improve mode** | Pipeline for incremental improvements captured via `/u-improve` |
| **Quality gate** | Checkpoint where an agent must approve before the pipeline continues |
| **Reverse feedback** | See *Feedback reverso* |
| **Rework** | Correction cycle when QA rejects a Story. Max 3 rounds before escalation |
| **Scope (Story)** | Field (`backend`, `frontend`, or `both`) on each Story in fullstack backlogs, determining which phase processes it |
| **SESSION** | Name of the current working session. Last argument in commands |
| **Short mode** | Reduced context reactivation (~2K tokens) for 2nd+ activation of the same agent in a session |
| **SPECS_DIR** | Root directory for all specifications |
| **Spec Reviewer** | Agent that approves or rejects specs with detailed feedback. Max 3 rejection cycles |
| **Spec Validator** | Agent that performs cross-reference validation across all spec artifacts |
| **ST-NN** | State Machine state identifier (e.g., ST-01). Defined in `.back.md` |
| **Story** | User Story -- atomic unit of work in the Dev pipeline. Follows INVEST criteria |
| **Triage** | Incremental error correction process that selects 5-10 errors per session to avoid token overflow |
| **UC-NN** | Use Case identifier (e.g., UC-01). Central traceability anchor in `.spec.md` |
| **UI-NN** | UI State identifier (e.g., UI-01). Defined in `.screen.md` for component states |
