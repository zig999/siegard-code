# Catálogo de Artefatos

> Todos os artefatos criados pelo sistema: localização, formato, quem produz, quem consome.

---

## Organização dos artefatos

O sistema cria artefatos em dois grupos:

**1. Artefatos de spec** — ficam em `SPECS_DIR` (configurável, ex: `./specs/`)

**2. Artefatos de orquestração** — ficam em `.orch/` (runtime, não versionado)

---

## Artefatos de Spec (`SPECS_DIR/`)

### `openapi.yaml`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/{domain}/openapi.yaml` |
| Produzido por | `u-spec-writer` |
| Consumido por | `u-spec-reviewer`, `u-spec-validator`, `u-spec-back`, `u-spec-front`, `u-be-developer`, `u-fe-developer` |
| Formato | OpenAPI 3.0 YAML |

**Conteúdo mínimo:**
```yaml
openapi: "3.0.3"
info:
  title: "{Domain} API"
  version: "1.0.0"
paths:
  /resource:
    post:
      summary: "..."
      operationId: "createResource"
      requestBody: ...
      responses:
        "201": ...
        "400": ...
        "500": ...
components:
  schemas:
    ResourceRequest: ...
    ResourceResponse: ...
    ErrorResponse: ...
  securitySchemes:
    bearerAuth: ...
```

---

### `{domain}.spec.md`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/{domain}/{domain}.spec.md` |
| Produzido por | `u-spec-writer` |
| Consumido por | `u-spec-reviewer`, `u-spec-validator`, todos os workers |
| Template base | `u-spec-templates/TEMPLATE.spec.md` |

**Seções obrigatórias:**
```markdown
# {Domain} Specification

## 1. Domain Overview
## 2. Entities & Value Objects
## 3. Use Cases
   ### UC-NN: {Nome}
   - **Actor:** ...
   - **Preconditions:** ...
   - **Main Flow:** (numerado)
   - **Alternative Flows:** (numerado)
   - **Postconditions:** ...
## 4. Business Rules
   - BR-NN: {Regra verificável}
## 5. Error Codes
   | Code | HTTP | Message |
## 6. Domain Events
## 7. Constraints & Non-Functional Requirements
```

---

### `{domain}.back.md`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/{domain}/{domain}.back.md` |
| Produzido por | `u-spec-back` |
| Consumido por | `u-spec-validator`, `u-be-developer`, `u-be-qa-docs` |
| Template base | `u-spec-templates/TEMPLATE.back.md` |

**Seções obrigatórias:**
```markdown
# {Domain} — Backend Specification

## 1. Architecture Overview
## 2. Database Schema
## 3. Repository Layer
   ### {Entity}Repository
   - Interface: ...
   - Methods: create, findById, findBy*, update, delete
## 4. Service Layer
   ### {Domain}Service
   - Dependencies: ...
   - Methods: (one per UC)
## 5. Route Handlers / Controllers
## 6. Middleware
## 7. Authentication & Authorization
## 8. Error Handling
## 9. Testing Strategy
```

---

### `{domain}.feature.spec.md`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/{domain}/{domain}.feature.spec.md` |
| Produzido por | `u-spec-front` |
| Consumido por | `u-spec-validator-front`, `u-fe-developer`, `u-fe-qa-docs` |
| Template base | `u-spec-templates/TEMPLATE.feature.spec.md` |

**Conteúdo:** Screens, estados de UI, interações, chamadas de API, mensagens de erro para o usuário.

---

### `{domain}.component.spec.md`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/{domain}/{domain}.component.spec.md` |
| Produzido por | `u-spec-front` |
| Consumido por | `u-fe-developer`, `u-fe-qa-docs` |
| Template base | `u-spec-templates/TEMPLATE.component.spec.md` |

**Conteúdo:** Componentes UI reutilizáveis do domain: props, estados, variantes, acessibilidade.

---

### `flows/{flow}.flow.md`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/{domain}/flows/{flow}.flow.md` |
| Produzido por | `u-spec-front` |
| Consumido por | `u-fe-developer` |
| Template base | `u-spec-templates/TEMPLATE.flow.md` |

**Conteúdo:** Diagrama de fluxo de navegação (em Mermaid ou ASCII), telas envolvidas, condições de transição.

---

### `_validation/{domain}-validation.md`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/{domain}/_validation/{domain}-validation.md` |
| Produzido por | `u-spec-validator` |
| Consumido por | `orchestrator-sdd` (exit criterion `all_domains_validated`) |

**Formato:**
```markdown
# Validation Report — {domain}

**Status:** VALID | INVALID
**Validated at:** <ISO timestamp>

## Checks

| Check | Status | Detail |
|-------|--------|--------|
| UC→endpoint mapping | PASS | ... |
| error codes synced | PASS | ... |
| BR references valid | FAIL | BR-03 references non-existent UC-07 |

## Findings
...
```

O exit criterion `all_domains_validated` falha se qualquer arquivo neste diretório contém a string `INVALID`.

---

### `handoff-manifest.yaml`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/handoff-manifest.yaml` |
| Produzido por | `u-spec-compliance` (gerado / aprovado manualmente) |
| Consumido por | `orchestrator-dev` (Step 2), `orchestrator-review` (stack detection) |
| Schema | `u-shared-templates/handoff-manifest.schema.yaml` |

```yaml
handoff_type: spec_first | fast_track | major_evolution | hotfix
stack: be | fe | fullstack
dev_impact: full | partial | no_action
specs_dir: ./specs
changed_files:
  - path: specs/payment/openapi.yaml
    domains: [payment]
    impact: new | modified | deleted
approval:
  status: approved
  reviewer: "user@example.com"
  approved_at: "2026-04-23T10:00:00Z"
```

---

### `error-codes.md`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/error-codes.md` |
| Produzido por | Primeiro `u-spec-writer`, atualizado por `u-spec-compliance` |
| Consumido por | Todos os spec workers, `u-be-developer`, exit criterion `error_codes_synced` |

**Formato:**
```markdown
# Error Codes

| Code | HTTP | Domain | Message | Recovery |
|------|------|--------|---------|---------|
| PAYMENT_001 | 402 | payment | Insufficient funds | ... |
| AUTH_001 | 401 | auth | Invalid credentials | ... |
```

---

### `decisions.md`

| Campo | Valor |
|-------|-------|
| Localização | `{SPECS_DIR}/decisions.md` |
| Produzido por | `u-spec-back`, `u-spec-front`, qualquer worker |
| Template base | `u-spec-templates/TEMPLATE.decisions.md` |

Registro de decisões arquiteturais tomadas durante o processo de spec.

---

## Artefatos de Orquestração (`.orch/`)

> Estes artefatos são de runtime — **não devem ser versionados** (adicione `.orch/` ao `.gitignore`).

### `.orch/log.jsonl` — O log principal

| Campo | Valor |
|-------|-------|
| Localização | `.orch/log.jsonl` |
| Produzido por | `append.py` (via todos os orchestrators e workers) |
| Consumido por | `reduce.py`, `read.py`, `verify.py`, hooks |
| Formato | JSONL (um evento JSON por linha) |

É a fonte única de verdade. Nunca deve ser editado manualmente.

---

### `.orch/log.jsonl.lock` — Lock file

Usado pelo `fcntl.flock()` para serializar writes. Nunca deletar manualmente enquanto o sistema está rodando.

---

### `.orch/blobs/evt_{id}.json` — Payloads externos

Quando um payload de evento excede 3500 bytes (limite do PIPE_BUF), é externalizado:

```
.orch/blobs/
└── evt_01HK7XZY8K9ABCDE01234.json    # Payload completo
```

O evento no log contém uma referência:
```json
{
  "data": {
    "_blob_ref": "blobs/evt_01HK7XZY8K9ABCDE01234.json",
    "_size": 15000,
    "_blob_hash": "sha256:abc123..."
  }
}
```

---

### `.orch/state/` — Snapshots (futuro)

Reservado para snapshots periódicos de estado (Task 1.8, atualmente deferida). Não usado na versão atual — `reduce_all()` é chamado em cada invocação.

---

### `.orch/workers/{worker_id}.json` — Worker registry

| Campo | Valor |
|-------|-------|
| Localização | `.orch/workers/{worker_id}.json` |
| Produzido por | `register_worker()` em `orch_core.py` (chamado pelo orchestrator ao claim) |
| Consumido por | `on_subagent_stop.py` hook |

```json
{
  "worker_id": "worker-sdd-01",
  "task_id": "sdd_payment_spec-writer",
  "attempt": 1,
  "phase": "sdd",
  "worker_type": "u-spec-writer",
  "registered_at": "2026-04-23T10:00:00Z"
}
```

Usado pelo hook para detectar workers que morreram silenciosamente.

---

### `.orch/dlq/` — Dead Letter Queue

Tasks que falharam permanentemente. Usado por `dlq_triage.py` para categorização.

```
.orch/dlq/
├── dev_tc_003_attempt_3.json
└── sdd_payment_spec-writer_attempt_3.json
```

---

### `.orch/audit/` — Audit trail

Logs de auditoria de operações sensíveis (recovery, circuit breaker reset).

---

### `.orch/metrics/current.json` — Métricas de sessão

| Campo | Valor |
|-------|-------|
| Localização | `.orch/metrics/current.json` |
| Produzido por | `on_stop.py` hook (ao encerrar sessão) |

```json
{
  "workflow_id": "<uuid>",
  "snapshot_at": "2026-04-23T15:30:00Z",
  "run_status": "active",
  "current_phase": "dev",
  "tasks": {
    "total": 12,
    "completed": 8,
    "running": 2,
    "pending": 2,
    "failed": 0,
    "dlq": 0
  },
  "phases": {
    "sdd": {"status": "completed", "duration_seconds": 1240},
    "dev": {"status": "active", "entered_at": "2026-04-23T14:00:00Z"}
  },
  "completion_pct": 66.7
}
```

---

### `.orch/workflow.json` — Override de fases (opcional)

Se presente antes do primeiro run, sobrescreve as fases padrão:

```json
{
  "phases": [
    {"name": "sdd",  "order": 1, "required": true},
    {"name": "dev",  "order": 2, "required": true},
    {"name": "test", "order": 3, "required": true}
  ]
}
```

Sem este arquivo, o workflow padrão é `sdd → dev → review → test`.

---

### `.orch/improve-scope.json` — Scope de melhoria (improve mode)

| Campo | Valor |
|-------|-------|
| Localização | `.orch/improve-scope.json` |
| Produzido por | `u-improve` skill (via `/u-improve` command) |
| Consumido por | `orchestrator-sdd` (detecta fast-track mode) |

```json
{
  "workflow_id": "<uuid>",
  "improvement_task": "Add rate limiting to payment endpoints",
  "classification": "enhancement",
  "affected_specs": [
    "specs/payment/openapi.yaml",
    "specs/payment/payment.spec.md"
  ],
  "mode_hint": "patch",
  "spec_changes_needed": true,
  "execution_policy": "fast_track",
  "created_at": "2026-04-23T10:00:00Z"
}
```

---

### `.orch/sessions/{workflow_id}/` — Session artifacts

Artefatos de sessão específicos de um workflow.

---

## Artefatos de Entregas Dev (`.orch/deliveries/`)

### `delivery.md`

| Campo | Valor |
|-------|-------|
| Localização | `.orch/deliveries/{task_id}/delivery.md` |
| Produzido por | `u-be-developer` / `u-fe-developer` |
| Consumido por | `orchestrator-dev` (exit criterion `all_deliveries_qa_ready`), `u-be-qa-docs` / `u-fe-qa-docs` |
| Template base | `u-shared-templates/delivery.schema.yaml` |

```markdown
# Delivery — {task_id}

**Task:** TC-NN — {Título do task contract}
**Phase:** dev
**Attempt:** 1

## Implemented

- [ ] Feature A (src/payment/PaymentService.ts)
- [ ] Tests (tests/payment/PaymentService.test.ts)
- [ ] Documentation updated

## Artifacts

| File | Type | Status |
|------|------|--------|
| src/payment/PaymentService.ts | implementation | created |
| tests/payment/PaymentService.test.ts | test | created |

## QA Readiness

**qa_ready:** true | false
**reason:** (se false, explicar o que falta)

## Prohibition Violations

(vazio se nenhuma; lista se houver)
```

---

## Artefatos de QA (`.orch/qa/`)

### `qa.md`

| Campo | Valor |
|-------|-------|
| Localização | `.orch/qa/{task_id}/qa.md` |
| Produzido por | `u-be-qa-docs` / `u-fe-qa-docs` |
| Consumido por | `orchestrator-review` (exit criteria, divergence scan, human gate) |

```markdown
# QA Report — {task_id}

**verdict:** approved | approved_with_reservations | rejected
**reviewed_at:** <ISO timestamp>
**documentation_verified:** true | false

## Summary

...

## Findings

| ID | Severity | Type | Description |
|----|----------|------|-------------|
| F-01 | warning | test_coverage | Missing edge case for empty cart |

## SPEC-DIVERGENCE (se houver)

**SPEC-DIVERGENCE:** POST /payments retorna 200 mas spec exige 201.
Referência: specs/payment/openapi.yaml §responses
```

O campo `SPEC-DIVERGENCE:` é detectado pelo `orchestrator-review` para acionar escalation `E09`.

---

## Artefatos de Templates Compartilhados

### `u-shared-templates/`

Templates e schemas YAML usados em todo o sistema:

| Arquivo | Propósito |
|---------|---------|
| `handoff-manifest.schema.yaml` | Schema do manifesto SDD→Dev |
| `handoff-manifest.yaml` | Template preenchível do manifesto |
| `delivery.schema.yaml` | Schema do delivery.md |
| `backlog.schema.yaml` | Schema do backlog.json gerado pelo planner |
| `task_contract.schema.yaml` | Schema de um task contract (TC-NN) |
| `task_contract.yaml` | Template de task contract |
| `qa-verdict.schema.yaml` | Schema do qa.md |
| `blocked-report.schema.yaml` | Schema de relatório de bloqueio |
| `architecture-finding.schema.yaml` | Schema de finding de arquitetura |
| `security-finding.schema.yaml` | Schema de finding de segurança |
| `compliance-finding.schema.yaml` | Schema de finding de compliance |
| `cr.schema.yaml` | Schema de Change Request (spec-versioning) |
| `handoff-receipt.schema.yaml` | Schema de recibo de handoff |
| `improve-handoff-envelope.schema.yaml` | Schema do envelope de improve |
| `fe-validate-report.schema.yaml` | Schema do relatório de validação frontend |
| `ui-agent-output.schema.yaml` | Schema de output do UI agent |
| `be-to-fe-handoff.schema.yaml` | Schema de handoff BE→FE (fullstack) |

### `u-spec-templates/`

Templates Markdown para specs:

| Arquivo | Propósito |
|---------|---------|
| `TEMPLATE.spec.md` | Domain spec principal |
| `TEMPLATE.back.md` | Backend spec |
| `TEMPLATE.feature.spec.md` | Feature spec (frontend) |
| `TEMPLATE.component.spec.md` | Component spec (UI) |
| `TEMPLATE.flow.md` | Navigation flow |
| `TEMPLATE.front.md` | Regras globais frontend |
| `TEMPLATE.decisions.md` | Log de decisões |
| `TEMPLATE.design-system/_index.md` | Design system index |
| `TEMPLATE.design-system/tokens.md` | Design tokens |
| `TEMPLATE.design-system/components.md` | Component library |
| `TEMPLATE.design-system/composition.md` | Composition rules |
| `TEMPLATE.design-system/implementation.md` | Implementation guide |

---

## Mapa de produção e consumo

```
Fase SDD:
  u-spec-writer         → openapi.yaml, {domain}.spec.md
  u-spec-reviewer       → (aprovação, sem artefato novo)
  u-spec-back           → {domain}.back.md
  u-spec-validator      → _validation/{domain}-validation.md
  u-spec-front          → {domain}.feature.spec.md, {domain}.component.spec.md, flows/*.flow.md
  u-spec-compliance     → error-codes.md (sync), handoff-manifest.yaml (validado)

Fase Dev:
  u-be-planner          → .orch/deliveries/{task_id}/backlog.json
  u-fe-planner          → .orch/deliveries/{task_id}/backlog.json
  u-be-developer        → .orch/deliveries/{task_id}/delivery.md + código fonte
  u-fe-developer        → .orch/deliveries/{task_id}/delivery.md + código fonte

Fase Review:
  u-be-qa-docs          → .orch/qa/{task_id}/qa.md
  u-fe-qa-docs          → .orch/qa/{task_id}/qa.md

Fase Test:
  u-test-runner         → .orch/tests/{task_id}/test-report.md

Runtime:
  orch_core.py          → .orch/log.jsonl (via append.py)
  on_subagent_stop.py   → sintetiza task_failed no log
  on_stop.py            → .orch/metrics/current.json
  u-improve skill       → .orch/improve-scope.json
```
