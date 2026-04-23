---
name: u-spec-globals-glossary
description: Global glossary of terms used in specifications. Avoids ambiguity between agents and teams.
user-invocable: false
---

# Global Glossary

## Rules
1. Every term that could cause ambiguity between agents or teams must be listed here
2. Terms are sorted alphabetically
3. Each domain may have its own local glossary in `.spec.md`, but global terms live here
4. In case of conflict between local and global glossary, the global one prevails

## Terms

| Term | Definition | Context |
|------|-----------|---------|
| Agent | Autonomous LLM instance with defined scope, inputs, and outputs | Architecture |
| Approval | Spec status validated by the Spec Reviewer, enabling consumption by other agents | Pipeline |
| Change Request (CR) | Formal request to modify an already-approved spec | Versioning |
| Cross-validation | Consistency verification across multiple spec documents | Pipeline |
| Delivery package | Set of spec files assembled by the Orchestrator for the implementation group | Pipeline |
| Domain | Bounded business context with its own entities, rules, and contracts | DDD |
| Fast-track | Simplified flow for low-impact changes to approved specs | Pipeline |
| Gate | Mandatory checkpoint in the pipeline where an agent validates before proceeding | Pipeline |
| Handoff | Formal spec transfer between groups (spec -> implementation) | Pipeline |
| Orchestrator | Coordinator agent that distributes tasks and manages sequencing | Architecture |
| Reverse Feedback | Return from the implementation group reporting technical infeasibility | Pipeline |
| Skill | Reusable knowledge set loaded by agents | Architecture |
| Spec | Specification document (business, technical, or UI) serving as source of truth | Pipeline |
