# Gerenciamento de Specs

> Como as especificações técnicas fluem pelo sistema: criação, revisão, validação, aprovação e uso downstream.

---

## O que é uma spec neste sistema

Uma **spec** é um conjunto de artefatos de texto estruturado que descreve completamente um domain do sistema antes que qualquer código seja escrito. A spec é o contrato entre a fase SDD e a fase Dev.

**Princípio:** Nenhum código é escrito sem uma spec aprovada. Qualquer divergência entre código e spec é tratada como bug.

**Spec-first flow:**
```
Requisito → Spec (SDD) → Backlog → Implementação (Dev) → QA (Review) → Testes (Test)
```

---

## Estrutura de um domain de spec

Para cada domain (ex: `payment`, `auth`, `user`), o sistema cria:

```
{SPECS_DIR}/{domain}/
├── openapi.yaml                    # Endpoints, schemas, security (OpenAPI 3.0)
├── {domain}.spec.md                # Spec principal: use cases, BRs, flows
├── {domain}.back.md                # Spec backend: repositories, services, middleware
├── {domain}.feature.spec.md        # Spec frontend: features, screens, comportamentos
├── {domain}.component.spec.md      # Componentes UI reutilizáveis do domain
├── flows/
│   └── {flow}.flow.md              # Fluxos de navegação e interação
└── _validation/
    └── {domain}-validation.md      # Resultado da validação cross-domain
```

**Arquivos globais (não por domain):**

```
{SPECS_DIR}/
├── error-codes.md                  # Catálogo global de error codes
├── decisions.md                    # Log de decisões arquiteturais
├── handoff-manifest.yaml           # Manifesto de handoff SDD→Dev (aprovação obrigatória)
└── design-system/                  # Tokens, componentes, composição (opcional)
    ├── _index.md
    ├── tokens.md
    ├── components.md
    ├── composition.md
    └── implementation.md
```

---

## Pipeline SDD — Como specs são criadas

O `orchestrator-sdd` coordena o pipeline para cada domain. A ordem é estrita e garantida por dependências de tasks.

### Standard mode (novo workflow)

```
Para cada domain identificado no SPECS_DIR:

  1. spec-writer
     Escreve openapi.yaml + {domain}.spec.md
     Artefatos: openapi.yaml, {domain}.spec.md

  2. spec-reviewer
     Revisa qualidade, completude, ambiguidade
     → APPROVED: próximo step
     → REJECTED(retryable): volta ao spec-writer (max 3 tentativas)
     → REJECTED(non-retryable): escalation E11

  3. spec-back
     Escreve {domain}.back.md (backend spec)
     Artefato: {domain}.back.md

  4. spec-validator (backend)
     Cross-valida spec principal + back spec
     → VALID: próximo step
     → INVALID(retryable): volta ao spec-back (max 2 tentativas)
     → INVALID(non-retryable): escalation E05

  (Passos 1-4 são o "back leg", criados POR DOMAIN.)

A decisão front/back/both é `triage.stack` (`fe | be | fullstack`), produzida deterministicamente
por `classify_stack.py` (co-presença de sinais UI + backend → `fullstack`; nunca suprimida por uma
keyword de backend isolada). `ui_task` é derivado (`stack ∈ {fe, fullstack}`).

Após o back leg de TODOS os domains — e somente se o front leg estiver ativo (`triage.stack` ∈
{`fe`, `fullstack`}, i.e. `ui_task == true`) — roda um
ÚNICO "front leg" por requisito (o Front Spec Agent é ativado uma vez e compõe todos os domains):

  5. spec-front (uma vez; task_id sdd_front; deps = spec-validator de todos os domains)
     Escreve front.md, feature.spec.md, component.spec.md, flows/
     Artefatos: todos os arquivos frontend

  6. spec-validator (front pass) (uma vez; task_id sdd_front_spec-validator; deps = sdd_front)
     Cross-valida specs principais + front spec
     → VALID: front leg completo
     → INVALID: volta ao spec-front

Se `triage.stack == be` (`ui_task == false`, back-only): o front leg é pulado (task_skipped) e nenhum artefato frontend é produzido. Se o stack estiver errado, o humano corrige no gate E99 (`force_fullstack` / `force_backend_only`).

Após o back leg (e o front leg, se houve):

  7. spec-compliance (cross-domain)
     Verifica handoff-manifest.yaml approval
     deps: sdd_front_spec-validator se houve front leg, senão todos os spec-validator de back
     Sincroniza error codes com error-codes.md
     Artefato: atualiza error-codes.md se necessário
```

### Fast-track mode (improve)

Ativado quando `.orch/improve-scope.json` existe. O `mode_hint` determina o alcance:

| mode_hint | Pipeline truncado |
|-----------|------------------|
| `patch` | Só spec-writer + spec-validator para arquivos afetados |
| `minor` | spec-writer + spec-reviewer + spec-validator |
| `full` | Pipeline completo para domains afetados |

**Diferenças do fast-track:**
- Sem gate E99 (confirmação humana já foi obtida em `/u-improve`)
- Só processa domains listados em `improve-scope.json → affected_specs`
- Task IDs têm prefixo `sdd_improve_{i:02d}_`

---

## Human Confirmation Gate (E99)

No standard mode, o orchestrator-sdd bloqueia antes do primeiro dispatch e aguarda confirmação humana:

```
Workflow Escalated
==================
Code:    E99_human_confirmation_required
Question: Ready to begin spec pipeline for domains: [payment, auth, user]?
          This will create N spec tasks across M domains.

Options:
- confirm_proceed
- abort

To resume: emit human_response and invoke orchestrator again.
```

Para responder:
```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent operator \
  --event-type human_response \
  --data '{"escalation_seq": <seq>, "action": "confirm_proceed", "operator": "user"}'
```

---

## Validação de Specs

### Checklist do spec-reviewer

O reviewer usa o skill `u-spec-review` que define critérios objetivos:

**OpenAPI:**
- Todos os endpoints têm summary, description, operationId
- Todos os schemas têm exemplos
- Responses cobrem 2xx, 4xx, 5xx para cada endpoint
- Security schemes declarados e aplicados
- Sem campos genéricos (`object` sem properties)

**spec.md:**
- Todos os UCs têm actor, precondition, postcondition, main flow, alternative flows
- BRs são verificáveis (nenhuma linguagem vaga: "may", "generally", "appropriate", "etc.")
- Referências cruzadas entre UCs e endpoints são consistentes
- Error codes listados correspondem ao `error-codes.md`

**Termos proibidos (linguagem vaga):**
`may`, `might`, `generally`, `adequate`, `etc.`, `similar to`, `soon`, `as needed`, `when appropriate`

### Cross-validation (spec-validator)

O validator usa o skill `u-spec-validation` para verificar:

| Verificação | O que checa |
|-------------|------------|
| UC → endpoint | Cada UC tem pelo menos 1 endpoint correspondente |
| endpoint → UC | Cada endpoint é referenciado por pelo menos 1 UC |
| BR → UC | Cada business rule é aplicável a pelo menos 1 UC |
| error code | Todos os error codes no spec existem em `error-codes.md` |
| schema → entity | Schemas OpenAPI mapeiam para entities do domain model |
| front → back | Endpoints no feature.spec referenciados existem no openapi.yaml |

**Output:** `_validation/{domain}-validation.md` com linha `VALID` ou `INVALID` + lista de findings.

---

## Handoff Manifest

O `handoff-manifest.yaml` é o artefato que faz a bridge entre a fase SDD e a fase Dev. É **gerado por `generate_handoff_manifest.py`** (rodado por `orchestrator-sdd` no Step 6, sobre specs já VALID) e validado pelo gate `handoff_manifest_approved`. A aprovação é **derivada**: não há campo `approval` — um manifesto que passa nas 13 regras do `u-handoff-validator` sobre specs VALID já é o handoff aprovado.

**Schema** (fonte canônica: `u-shared-templates/handoff-manifest.schema.yaml`):
```yaml
handoff:
  id: HANDOFF-<YYYYMMDD-HHMMSS>
  delivered_by: u-spec-orchestrator        # const exigida por FLOW-030 (identificador de protocolo)
  delivered_at: <YYYY-MM-DDTHH:MM:SSZ>
  layer: semi-permanent
  type: new_domain | major_evolution | fast_track | reverse_eng
domains:                                   # >= 1
  - name: <domain>
    spec_version: <semver>
    back_version: <semver>
    openapi_version: <semver>
    compliance_report: <path-ou-mensagem>
frontend_artifacts:                        # omitido em handoffs back-only
  front_md_version: <semver>
  features: [{ name, path }]
  flows: [{ name, path }]
backend_package:                           # >= 1
  - path: specs/domains/<domain>/openapi.yaml
    artifact: conventions | error-codes | openapi | spec | back-spec
    sha256: <64-hex>
frontend_package:                          # presente só quando há specs front
  - path: <path>
    artifact: conventions | error-codes | openapi | spec | front | feature-spec | component-spec | flow
    sha256: <64-hex>
change_summary:                            # apenas em evolução — ausente em new_domain
  type: patch | minor | major
  cr: <CR-NN | none>
  changed_files: [<path>]
  dev_impact: no_action | reevaluate_task_contracts | stop_domain_task_contracts
```

> **Não existe campo `stack`.** O `orchestrator-dev` infere o stack via `parse_manifest_fields()`:
> só `backend_package` → `be`; só `frontend_package` → `fe`; ambos → `fullstack`. Um handoff
> back-only omite `frontend_artifacts`/`frontend_package` e resolve para `stack=be`.

**Regras de validação** (13 regras, `u-handoff-validator/validate.py`; `(be)`/`(fe)` = roda conforme o caller):

| Rule ID | Severity | O que verifica |
|---------|----------|---------------|
| FLOW-030 | blocking | `handoff.delivered_by` == `u-spec-orchestrator` |
| FLOW-031 | blocking | `domains[]` tem ≥ 1 entrada |
| FLOW-032 | blocking (be) | `backend_package[]` tem ≥ 1 entrada |
| FLOW-033 | blocking | `new_domain` NÃO inclui `change_summary` |
| FLOW-034 | blocking | `major_evolution`/`fast_track`/`reverse_eng` incluem `change_summary` |
| FLOW-035 | blocking | `change_summary.dev_impact` é enum válido |
| FLOW-036 | blocking | `fast_track` → `type` ∈ {patch, minor}; `major_evolution` → `major` |
| FLOW-037 | blocking (be) | `backend_package` inclui os artifacts `openapi` e `back-spec` |
| HDF-010 | blocking | `handoff.type` ∈ {new_domain, major_evolution, fast_track, reverse_eng} |
| HDF-020 | blocking (be) | sha256 de cada `backend_package` confere com o arquivo em disco |
| HDF-021 | blocking (fe) | sha256 de cada `frontend_package` confere com o arquivo em disco |
| HDF-030 | blocking | `change_summary.dev_impact = stop_domain_task_contracts` → caller paralisa domains afetados |
| HDF-040 | blocking (fe) | `frontend_artifacts` presente → contém `front_md_version`, `features`, `flows` |

---

## Como specs são usadas na fase Dev

O `orchestrator-dev` lê o `handoff-manifest.yaml` via `parse_manifest_fields()` de `orch_core.py` e extrai:

```python
{
    "stack":        "be | fe | fullstack",
    "handoff_type": "spec_first | fast_track | ...",
    "dev_impact":   "full | partial | no_action",
    "changed_files": [{"path": "...", "domains": [...], "impact": "..."}]
}
```

O **planner** (u-be-planner / u-fe-planner) recebe `SPECS_DIR` como env var e lê diretamente as specs para gerar o backlog. Cada task contract no backlog referencia:

```yaml
execution_contract:
  input:
    references:
      - path: specs/payment/payment.back.md
        section: "§3 — Repository Layer"
      - path: specs/payment/openapi.yaml
        section: "POST /payments"
```

Os **developers** (u-be-developer / u-fe-developer) recebem o task contract completo e lêem as specs referenciadas para implementar.

---

## Spec Divergence Detection

Durante a fase Review, o `orchestrator-review` varre os QA artifacts procurando a string `SPEC-DIVERGENCE:`.

Se um QA worker (u-be-qa-docs, u-fe-qa-docs) identifica que o código não está conforme a spec, deve marcar no `qa.md`:

```markdown
## Findings

**SPEC-DIVERGENCE:** O endpoint `POST /payments` retorna 200 mas a spec exige 201.
Referência: specs/payment/openapi.yaml §responses.201
```

Quando detectado, o orchestrator-review emite uma escalation `E09` separada antes do gate E99 de aprovação humana.

---

## Improve Mode — Atualizando specs existentes

O comando `/u-improve` é o entry point para mudanças incrementais em specs existentes.

### Fluxo

```
1. Usuário: /u-improve "Add rate limiting to payment endpoints" session-1
2. u-improve skill classifica o impacto:
   - Tipo: enhancement | bug-fix | refactoring | ...
   - Specs afetadas: [specs/payment/openapi.yaml, specs/payment/payment.spec.md]
   - mode_hint: patch | minor | full
3. Persiste improve-scope.json em .orch/ ANTES de qualquer confirmação humana
4. Apresenta escopo ao usuário; aguarda confirmação
5. Se specs precisam de mudança: auto-invoca /u-spec (fast-track mode)
6. Se só implementação: delega para /u-dev
```

**improve-scope.json:**
```json
{
  "workflow_id": "<uuid>",
  "improvement_task": "Add rate limiting to payment endpoints",
  "classification": "enhancement",
  "affected_specs": ["specs/payment/openapi.yaml"],
  "mode_hint": "patch",
  "spec_changes_needed": true,
  "execution_policy": "fast_track"
}
```

### Integração com SDD fast-track

O `orchestrator-sdd` detecta o `improve-scope.json` e entra em fast-track mode:
1. Lê `affected_specs` → determina quais domains processar
2. Usa `mode_hint` para truncar o pipeline
3. Pula o gate E99 (confirmação já foi obtida em `/u-improve`)
4. Usa task IDs com prefixo `sdd_improve_`

---

## Reverse Spec — Gerando specs de código existente

O comando `/u-reverse-spec` reverse-engineers specs a partir de código existente.

```bash
/u-reverse-spec src/ specs/ session-reverse-1
```

### Output

Todos os artefatos gerados são marcados `[DRAFT]`:

```
specs/{domain}/
├── openapi.yaml          [DRAFT — inferido de routes/controllers]
├── {domain}.spec.md      [DRAFT — inferido de business logic]
├── {domain}.back.md      [DRAFT — inferido de services/repos]
└── {domain}.feature.spec.md  [DRAFT — inferido de components/pages]
```

### Fluxo após reverse spec

Após o reverse-spec, as specs draft precisam passar pelo pipeline normal de validação antes de serem usadas:

```
Reverse spec → Spec Reviewer (valida quality) → Spec Validator (valida consistency) → aprovação
```

O `orchestrator-sdd` pode ser invocado para processar specs draft existentes.
