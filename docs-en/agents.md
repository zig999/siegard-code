# Agentes do Sistema

> Referência de todos os agentes em `dist/.claude/agents/`.
> Para cada agente: papel, tools, skills, o que spawna, o que emite, envelope de retorno.

---

## Tier 1 — Meta-Orchestrator

### `orchestrator.md`

**Papel:** Entry point único para todos os workflows. Dispatcher puro — lê a fase atual do log, executa infrastructure checks, inicializa phase declarations, spawna o phase orchestrator correto. Contém zero domain logic.

| Atributo | Valor |
|----------|-------|
| Model | `claude-sonnet-4-6` (só roteia e executa scripts Python) |
| Tools | `Agent`, `Bash`, `Read` |
| Skills | `orch-log`, `orch-state`, `orch-infra` |
| Spawna | Phase orchestrators (um por vez, max 20 por invocação) |
| Emite | `phase_declared`, `phase_entered`, `escalation` (E10) |

**Routing table:**

| current_phase | Sub-agent spawned |
|---------------|-------------------|
| `sdd` | `orchestrator-sdd` |
| `dev` | `orchestrator-dev` |
| `review` | `orchestrator-review` |
| `test` | `orchestrator-test` |

**Ciclo de operação (7 steps, com loop interno):**

```
Step 1 → Infrastructure check (preflight, integrity, circuit)
Step 2 → State derivation (reduce.py + current_phase.py)
Step 3 → Terminal state check (completed? escalated?)
Step 4 → First-run init (gera workflow_id, emite phase_declared)
Step 5 → Phase entry (emite phase_entered se current_phase == null)
Step 6 → Spawna phase orchestrator
Step 7 → Avalia return → se phase_complete: volta ao Step 3 (loop)
```

**Envelope de retorno:**
```json
{
  "status": "completed | escalated | blocked | error",
  "workflow_id": "<uuid>",
  "last_seq": 42,
  "phases_completed": ["sdd", "dev", "review", "test"]
}
```

**Regras críticas:**
- Nunca escreve código, specs ou verdicts de QA
- Nunca spawna task workers diretamente
- Nunca interage com o humano durante execução de fase
- Só reporta ao humano em: escalation, blocked, completion

---

## Tier 2 — Phase Orchestrators

### `orchestrator-sdd.md`

**Papel:** Coordena pipeline de especificações. Para cada domain, spawna workers na sequência correta. Gerencia rejection cycles, confirmation gates e exit criteria. Nunca escreve specs.

| Atributo | Valor |
|----------|-------|
| Model | `claude-opus-4-7` |
| Tools | `Agent`, `Bash`, `Read`, `Glob`, `Grep` |
| Skills | `orch-log`, `orch-state`, `orch-infra`, `orch-report`, `phase-sdd-rules` |

**Modos de operação:**

| Modo | Trigger | Comportamento |
|------|---------|--------------|
| **Standard** | Primeiro run ou phase reentrada normal | Scan completo de domains, gate E99, pipeline completo |
| **Fast-track (improve)** | `improve-scope.json` existe em `.orch/` | Patches direcionados, sem gate E99, pipeline truncado por `mode_hint` |

**Pipeline (modo standard):**

```
back leg (POR DOMAIN):
  spec-writer → spec-reviewer → spec-back → spec-validator

front leg (UMA VEZ por requisito, só se triage.ui_task == true):
  spec-front (deps: spec-validator de todos os domains) → spec-validator (front pass)

cross-domain:
  spec-compliance (deps: front-pass validator se houve front leg, senão todos os back validators)
```

**Workers spawned:**

| Task type | Worker sub-agent |
|-----------|-----------------|
| `spec-writer` | `u-spec-writer` |
| `spec-reviewer` | `u-spec-reviewer` |
| `spec-back` | `u-spec-back` |
| `spec-front` | `u-spec-front` |
| `spec-validator` | `u-spec-validator` |
| `spec-compliance` | `u-spec-compliance` |

**Escalation codes emitidos:**

| Code | Condição |
|------|---------|
| `E99_human_confirmation_required` | Gate antes do primeiro dispatch (standard mode) |
| `E05_rejection_cycle_limit` | spec-writer ≥ 3 tentativas ou spec-validator ≥ 2 tentativas |
| `E08_exit_criteria_not_met` | Todas as tasks terminaram mas critérios de exit não passaram |
| `E11_spec_input_missing` | spec-reviewer falhou com arquivos de input ausentes |

**Exit criteria (avaliados por scripts Python):**

| Critério | O que verifica |
|---------|---------------|
| `handoff_manifest_approved` | `handoff-manifest.yaml` existe e tem `status: approved` |
| `all_domains_validated` | Nenhum arquivo em `_validation/` contém `INVALID` |
| `error_codes_synced` | Todos os error codes referenciados nas specs estão em `error-codes.md` |

---

### `orchestrator-dev.md`

**Papel:** Lê `handoff-manifest.yaml`, detecta stack, spawna planning worker, cria backlog de task contracts, despacha implementation workers. Totalmente autônomo — sem human gates.

| Atributo | Valor |
|----------|-------|
| Model | `claude-sonnet-4-6` |
| Tools | `Agent`, `Bash`, `Read`, `Glob`, `Grep` |
| Skills | `orch-log`, `orch-state`, `orch-infra`, `orch-report`, `phase-dev-rules` |

**Roteamento de workers por stack:**

| Task type | Stack | Worker |
|-----------|-------|--------|
| `planning` | `be` | `u-be-planner` |
| `planning` | `fe` / `fullstack` | `u-fe-planner` → depois `u-be-planner` |
| `impl` | `be` | `u-be-developer` |
| `impl` | `fe` | `u-fe-developer` |
| `spec` | `fe` | `u-fe-spec-writer` |

**Short-circuit:** Se `handoff_type` é `fast_track` ou `major_evolution` e `dev_impact == no_action`, pula implementação — emite exit criteria e transiciona imediatamente.

**Escalation codes:**

| Code | Condição |
|------|---------|
| `E07_planning_failed` | Planner falhou de forma não-retryável |
| `E04_critical_task_dlq` | Task crítica foi para DLQ |
| `E08_exit_criteria_not_met` | Todas tasks terminadas mas critérios não passaram |

**Exit criteria:**

| Critério | O que verifica |
|---------|---------------|
| `all_impl_tasks_terminal` | Todas as tasks dev estão em `completed` ou `dlq` |
| `all_deliveries_qa_ready` | Todo `delivery.md` tem `qa_ready: true` |
| `no_open_prohibitions` | Nenhum `delivery.md` tem `prohibition_violations` não-vazio |

---

### `orchestrator-review.md`

**Papel:** Coleta delivery artifacts, spawna QA workers por task, apresenta verdict summary, requer aprovação humana antes de avançar. Se rejected, retorna failing tasks para dev.

| Atributo | Valor |
|----------|-------|
| Model | `claude-sonnet-4-6` |
| Tools | `Agent`, `Bash`, `Read`, `Glob`, `Grep` |
| Skills | `orch-log`, `orch-state`, `orch-infra`, `orch-report`, `phase-review-rules` |

**Roteamento:**

| Task type | Stack | Worker |
|-----------|-------|--------|
| `qa` | `be` | `u-be-qa-docs` |
| `qa` | `fe` | `u-fe-qa-docs` |
| `architecture-review` | qualquer | `u-architecture-reviewer` (manual injection) |
| `security-review` | qualquer | `u-security-reviewer` (manual injection) |

**Human approval gate (E99):** Obrigatório. Opções aceitas via `human_response`:
- `approve` → avança para test
- `return_to_dev` → retorna todas as tasks
- `return_partial` → retorna tasks específicas (IDs no payload)

**Spec divergence detection:** Antes do gate, faz scan dos QA artifacts procurando linhas `SPEC-DIVERGENCE:`. Se encontradas, emite escalation `E09` separada.

**Exit criteria:**

| Critério | O que verifica |
|---------|---------------|
| `all_qa_verdicts_approved` | Todo verdict tem `verdict: approved` ou `approved_with_reservations` |
| `no_open_critical_findings` | Nenhum verdict tem `severity: critical` |
| `documentation_verified` | Pelo menos 1 artifact com `documentation_verified: true`; nenhum com `false` |

---

### `orchestrator-test.md`

**Papel:** Spawna test runners por task de implementação, coleta reports, avalia exit criteria. Totalmente autônomo se testes passam. Escalate se há falhas, aguarda decisão do humano.

| Atributo | Valor |
|----------|-------|
| Model | `claude-sonnet-4-6` |
| Tools | `Agent`, `Bash`, `Read`, `Glob`, `Grep` |
| Skills | `orch-log`, `orch-state`, `orch-infra`, `orch-report`, `phase-test-rules` |

**Worker:** `u-test-runner` (stack-agnostic) para todos os tipos de task.

**Human gate (condicional):** Só se testes falham. Opções:
- `return_to_dev` → cria revision tasks com prefixo `_r{n}`, transiciona de volta para dev
- `accept_with_failures` → emite exit criteria com nota, transiciona para done

**Auto-complete:** Se todos os testes passam, transiciona sem qualquer gate humano.

**Exit criteria:**

| Critério | O que verifica |
|---------|---------------|
| `all_test_tasks_terminal` | Todas as test tasks em `completed` ou `dlq` |
| `all_tests_passed` | Todo test report tem `result: passed` |
| `no_critical_failures` | Nenhum test report tem `severity: critical` |

---

## Workers — Spec Phase

> Todos os workers carregam `orch-report` (obrigatório para emitir ao log).
> Emitem exatamente **um** evento terminal: `task_completed` ou `task_failed`.

### `u-spec-writer`

**Papel:** Escreve o draft inicial de uma spec de domain.

**Skills:** `orch-report`, `u-spec-writing`, `u-spec-globals`, `u-spec-templates`

**Artefatos produzidos:**
- `{SPECS_DIR}/{domain}/openapi.yaml` — endpoints, schemas, security
- `{SPECS_DIR}/{domain}/{domain}.spec.md` — use cases, business rules, flows

---

### `u-spec-reviewer`

**Papel:** Revisa o draft da spec, aprova ou rejeita com feedback estruturado.

**Skills:** `orch-report`, `u-spec-review`, `u-spec-writing`, `u-spec-globals`

**Output:** Aprovação via `task_completed` ou rejeição via `task_failed(retryable=true)` com `feedback` no payload.

---

### `u-spec-back`

**Papel:** Escreve a spec técnica de backend para um domain aprovado.

**Skills:** `orch-report`, `u-spec-writing`, `u-spec-back-writing`, `u-spec-globals`, `u-spec-templates`

**Artefato produzido:**
- `{SPECS_DIR}/{domain}/{domain}.back.md` — repositories, services, middleware, auth

---

### `u-spec-front` / `u-fe-spec-writer`

**Papel:** Escreve specs de frontend para um domain.

**Skills:** `orch-report`, `u-spec-writing`, `u-spec-globals`, `u-spec-templates`

**Artefatos produzidos:**
- `{SPECS_DIR}/{domain}/{domain}.feature.spec.md`
- `{SPECS_DIR}/{domain}/{domain}.component.spec.md`
- `{SPECS_DIR}/{domain}/flows/{flow}.flow.md`

---

### `u-spec-validator`

**Papel:** Cross-valida specs para consistência interna e entre camadas.

**Skills:** `orch-report`, `u-spec-validation`, `u-spec-globals`

**Artefato produzido:**
- `{SPECS_DIR}/{domain}/_validation/{domain}-validation.md` — resultado com `VALID` ou `INVALID` + findings

---

### `u-spec-compliance` (cross-domain)

**Papel:** Check final de compliance: handoff manifest approval + sync de error codes.

**Skills:** `orch-report`, `u-spec-validation`, `u-spec-globals`

---

## Workers — Dev Phase

### `u-be-planner` / `u-fe-planner`

**Papel:** Gera backlog estruturado de task contracts a partir do `handoff-manifest.yaml`.

**Skills:** `orch-report`, `u-planning`, `u-be-standards`/`u-fe-standards`

**Artefato produzido:**
- `.orch/backlog/{task_id}/backlog.json` — array de task contracts (Epic + TC-NN)

---

### `u-be-developer` / `u-fe-developer`

**Papel:** Implementa um task contract específico (um TC-NN).

**Skills BE:** `orch-report`, `u-be-development`, `u-be-standards`, `u-be-templates`

**Skills FE:** `orch-report`, `u-fe-development`, `u-fe-standards`, `u-fe-templates`, `u-ui-design` (condicional)

**Artefato produzido:**
- `delivery.md` em `.orch/deliveries/{task_id}/` — código implementado, testes, documentação, `qa_ready: true/false`

---

### `u-be-qa-docs` / `u-fe-qa-docs`

**Papel:** QA review de uma delivery. Verifica conformidade com spec, qualidade de código, testes, documentação.

**Skills BE:** `orch-report`, `u-be-qa-docs`, `u-be-standards`

**Skills FE:** `orch-report`, `u-fe-qa-docs`, `u-fe-standards`, `u-fe-review`

**Artefato produzido:**
- `qa.md` em `.orch/qa/{task_id}/` — verdict (`approved`/`rejected`), findings, `documentation_verified`

---

## Workers — Reverse-Spec

### `u-reverse-spec-orchestrator`

**Papel:** Orquestra reverse engineering: coordena analyzer e writer. Entry point do reverse-spec flow.

**Spawna:** `u-reverse-spec-analyzer` → `u-reverse-spec-writer`

---

### `u-reverse-spec-analyzer`

**Papel:** Analisa source code existente: identifica entities, endpoints, business rules, UI structure.

**Skills:** `orch-report`, `u-reverse-spec-analysis`

**Artefato produzido:** `analysis-report.md` com mapa do código source

---

### `u-reverse-spec-writer`

**Papel:** Escreve specs a partir do analysis report. Output marcado como `draft`.

**Skills:** `orch-report`, `u-spec-writing`, `u-spec-templates`

**Artefatos produzidos:** mesmos que `u-spec-writer` + `u-spec-back` + `u-spec-front`, todos marcados `[DRAFT]`
