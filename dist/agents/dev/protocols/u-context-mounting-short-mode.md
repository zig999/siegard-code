## Short Mode (token reduction for subsequent activations)

**Who decides:** the Orchestrator-Dev, automatically. When mounting a sub-agent's context, check the log for a prior activation of the **same agent** in the current session. If found, use short mode.

### When to apply

Short mode applies in ALL situations below:
- **2nd+ Task Contract in the same Epic** for the same agent
- **1st Task Contract in a new Epic** when the agent was already activated in a previous Epic during the same session
- **Post-QA correction (rework):** the agent has already processed the Task Contract once — always use short mode

> **Skills:** embedded in the agent's system prompt — present in **all** activations at no additional token cost. There is no skill economy between activations.

### What still applies in short mode

For the 2nd+ activation of the same agent in the session, when building the activation prompt:
- Extract only the relevant Task Contract block (not the entire `backlog.md`)
- Omit spec sections already extracted in previous activations of the same Task Contract (rework)
- For post-QA rework: include only the QA report and the delivery — do not re-pass previous context

### What NO LONGER applies

- ~~Replace skill content with compact reminder~~ — skills are in the system prompt
- ~~"Skills already loaded" reminder~~ — no longer needed
