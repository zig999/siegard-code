# Documentation -- Dev Team Agents

Autonomous agent system for Claude Code that coordinates the complete feature development cycle -- from technical specification to delivery with QA.

> This repository is not a product. It is the agent infrastructure installed into target projects.

## High-level architecture

```mermaid
graph TB
    subgraph INPUT["Input"]
        REQ[Requirement / Existing code]
    end
    subgraph RSPEC["Reverse Spec"]
        RSORC[Orchestrator]
        RSANA[Analyzer]
        RSWRT[Writer]
        RSORC --> RSANA --> RSWRT
    end
    subgraph SPEC["Spec Team"]
        SPORC[Orchestrator]
        SPWRT[Spec Writer]
        SPREV[Spec Reviewer]
        SPBCK[Back Spec Agent]
        SPFRT[Front Spec Agent]
        SPVAL[Spec Validator]
        SPORC --> SPWRT --> SPREV
        SPREV -->|APPROVED| SPBCK & SPFRT
        SPBCK & SPFRT --> SPVAL
        SPREV -->|REJECTED| SPWRT
        SPVAL -->|INVALID| SPBCK & SPFRT
    end
    subgraph DEV["Dev Team"]
        DVORC[Orchestrator-Dev]
        PLAN[Planner]
        UIAG[UI Agent]
        DEVAG[Developer]
        QAAG[QA & Docs]
        DVORC --> PLAN --> UIAG --> DEVAG --> QAAG
        QAAG -->|REJECTED| DEVAG
    end
    REQ --> RSORC & SPORC
    RSWRT -->|{SPECS_DIR} draft| SPORC
    SPVAL -->|VALID + {SPECS_DIR}| DVORC
    QAAG -->|APPROVED| END[Delivery]
```

## Quick flows

```
Spec-first:           /u-spec -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
Quick improvement:    /u-improve {SPECS_DIR} {SESSION} -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
Bug fix:              /u-bug-report {SPECS_DIR} {SESSION} -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
Reverse + triage:     /u-reverse-spec -> /u-spec-triage {SPECS_DIR} {SESSION} -> /u-dev {SPECS_DIR} {SESSIONS_DIR} {SESSION}
```

## Getting started

- First time? Start with [Installation](02-installation/README.md)
- Want to run something? See [Commands](03-commands/README.md)
- Want to understand the architecture? Read the [Overview](01-overview/README.md)

## Index

1. [Overview](01-overview/README.md) -- Architecture, core concepts, and glossary
2. [Installation](02-installation/README.md) -- How to install and configure in the target project
3. [Commands](03-commands/README.md) -- The 6 slash commands available
4. [Agent Teams](04-teams/README.md) -- The 3 teams: Spec, Dev, and Reverse Spec
5. [Execution Flows](05-flows/README.md) -- Step-by-step usage scenarios
6. [Protocols](06-protocols/README.md) -- On-demand orchestrator protocols
7. [Skills](07-skills/README.md) -- Reusable skill catalog
8. [Artifacts](08-artifacts/README.md) -- Generated files, lifecycle, and cleanup
9. [Estimates](09-estimates/README.md) -- Cost, tokens, and time per mode
10. [Resilience](10-resilience/README.md) -- Failure scenarios, limits, and troubleshooting
11. [Quick Reference](11-reference/README.md) -- Cheat sheet, action guide, and variables
