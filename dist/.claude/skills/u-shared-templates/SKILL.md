---
name: u-shared-templates
description: Schema + example pairs for every cross-agent envelope (handoff-manifest, delivery, qa-verdict, blocked-report, task_contract, validation-result, compliance/security/architecture findings, and others). Single source of truth for inter-agent contracts; consumed by all orchestrators, workers, and u-handoff-validator. Resource bundle — no scripts. Not user-invocable.
user-invocable: false
---

# u-shared-templates

Resource bundle: inter-agent envelope contracts. Every envelope ships as a pair — `<envelope>.schema.yaml` (validation schema) plus `<envelope>.yaml` (canonical example). Files are read by path (`.claude/skills/u-shared-templates/<file>`); the directory listing is authoritative.

## Envelope index

| Envelope | Producer | Consumer |
|---|---|---|
| `handoff-manifest` | orchestrator-sdd | u-handoff-validator, dev orchestrators |
| `handoff-receipt` | dev orchestrators | orchestrator-sdd |
| `handoff-validation-envelope` | u-handoff-validator | dev orchestrators |
| `improve-handoff-envelope` | /u-improve | u-spec-triage, orchestrator-sdd |
| `be-to-fe-handoff` | u-be-developer | u-fe-developer |
| `backlog` | planners | orchestrator-dev |
| `task_contract` | planners | developers |
| `delivery` | developers | QA workers |
| `qa-verdict` | QA workers | orchestrator-review |
| `blocked-report` | any worker | orchestrator |
| `validation-result` | u-spec-validator | orchestrator-sdd |
| `compliance-finding` | u-spec-compliance | orchestrator-sdd |
| `security-finding` | u-security-reviewer | orchestrator-review |
| `architecture-finding` | u-architecture-reviewer | orchestrator-review |
| `cr` (`cr-template.yaml` + `cr.schema.yaml`) | any agent flagging a spec change | orchestrator-sdd |
| `component-spec-gate-report` | component-spec-gate | orchestrator-dev |
| `design-system-gate-report` | design-system gate | orchestrator-dev |
| `fe-validate-report` | /u-fe-validate | user, orchestrator-dev |
| `spec-changelog-notify` | orchestrator-sdd | downstream orchestrators |
| `ui-agent-output` | u-fe-ui | u-fe-developer |

Non-pair files: `delivery-gate.md` (gate checklist consumed by orchestrator-dev).

## Constraints

- Schemas are the contract (AI FIRST — contracts over interpretation): producers MUST emit envelopes that validate against the `.schema.yaml`; consumers MUST validate before consumption
- Schema changes are breaking changes — update producer, consumer, and example in the same commit
