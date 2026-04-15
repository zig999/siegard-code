# Protocols

On-demand behavioral protocols activated by orchestrators (not by agents directly). Each protocol defines a specific behavior pattern that can be triggered during pipeline execution.

## Protocol catalog

| Protocol | Activated by | Purpose |
|----------|-------------|---------|
| [Mode detection](mode-detection.md) | All orchestrators | Determine operating mode from artifacts |
| [Context mounting](context-mounting.md) | All orchestrators | Selective context loading per agent |
| [Short mode](short-mode.md) | All orchestrators | Reduced context for agent reactivation |
| [Handoff](handoff.md) | Spec orchestrator | Formal artifact transfer from Spec to Dev |
| [Session resume](session-resume.md) | All orchestrators | Resume interrupted session |
| [Rework](rework.md) | Dev orchestrator | Correction cycle after QA rejection |
| [Push/merge](push-merge.md) | Dev orchestrator | Git operations after QA approval |
| [Cleanup](cleanup.md) | Dev orchestrator | Archive temporary artifacts |
| [Epic integration](epic-integration.md) | Dev orchestrator | Cross-Task Contract validation when Epic complete |
| [Tech debt](tech-debt.md) | Dev orchestrator | Register technical debt |
| [Bug mode](bug-mode.md) | Dev orchestrator | Specialized bug fix pipeline |
| [Improve mode](improve-mode.md) | Dev orchestrator | Incremental improvement pipeline |
| [Fullstack coordination](fullstack-coordination.md) | Fullstack meta-orchestrator | BE→FE handoff and E2E integration validation |
| [Spec fast-track](spec-fast-track.md) | Spec orchestrator | Simplified spec pipeline for minor changes |
| [Spec versioning](spec-versioning.md) | Spec orchestrator | Semantic versioning for specs |
| [Reverse spec merge](reverse-spec-merge.md) | Reverse Spec orchestrator | Merge strategy for existing specs |

## How protocols work

Protocols are NOT agents. They are behavioral rules that an orchestrator loads and follows when specific conditions are met. The orchestrator decides when to activate a protocol based on the current pipeline state.
