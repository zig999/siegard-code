# Spec Team

The Spec Team is responsible for creating, reviewing, and validating technical specifications that serve as the single source of truth for development.

## Agents

| Agent | Role | Input | Output |
|-------|------|-------|--------|
| **[Orchestrator](orchestrator.md)** | Coordinates pipeline, manages gates | Requirement + mode | `log-orchestrator-spec.md` |
| **[Writer](writer.md)** | Creates initial specs | Requirement + globals | `openapi.yaml` + `.spec.md` |
| **[Reviewer](reviewer.md)** | Quality gate for specs | `.spec.md` + `openapi.yaml` | Approval/rejection report |
| **[Back Spec](back-spec.md)** | Backend technical spec | Approved `.spec.md` | `.back.md` per domain |
| **[Front Spec](front-spec.md)** | Frontend technical spec | All approved `.back.md` | `front.md`, feature specs, component specs, flows |
| **[Validator](validator.md)** | Cross-reference validation | All artifacts | Validation report |

## Pipeline

```
Writer -> Reviewer -> Back Spec Agent(s) -> Validator -> Front Spec Agent -> Validator
```

### Critical ordering rule

The **Front Spec Agent runs after ALL Back Spec Agents complete**. This is because frontend features often compose data from multiple backend domains. The Front Spec Agent needs all domain contracts available to produce accurate feature and flow specifications.

## Operating modes

| Mode | Trigger | Pipeline |
|------|---------|----------|
| **New domain** | No `{SPECS_DIR}` or new domain requested | Full pipeline |
| **Fast-track** | Minor/patch change | Writer -> Reviewer -> Validator (skip Back/Front if unaffected) |
| **Reverse-eng review** | `origin-reverse-spec.md` exists | Review + approve draft specs |
| **Merge review** | `merge-pending-review.md` exists | Review merge divergences |
| **Resume** | Incomplete `log-orchestrator-spec.md` | Resume from last stage |
| **Reverse feedback** | `feedback-NN.md` from Developer | Writer corrects -> Reviewer -> Validator |

## Quality gates

- **Reviewer**: Max 3 rejection cycles before escalation to human
- **Validator**: Max 2 invalidation cycles before escalation
- **Domain WIP limit**: Max 3 domains being processed simultaneously
