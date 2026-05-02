# Workflow Reference — Orchestration Engine

> Documento de referência técnica do framework de orquestração em `dist2/`.
> Descreve o ciclo de vida completo de um workflow: fases, etapas, estados e log.

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [Como um workflow começa](#2-como-um-workflow-começa)
3. [Meta-orquestrador — ciclo de invocação](#3-meta-orquestrador--ciclo-de-invocação)
4. [Fase SDD](#4-fase-sdd)
5. [Fase Dev](#5-fase-dev)
6. [Fase Review](#6-fase-review)
7. [Fase Test](#7-fase-test)
8. [Sistema de log — event sourcing](#8-sistema-de-log--event-sourcing)
9. [Estados de task](#9-estados-de-task)
10. [Estados de fase](#10-estados-de-fase)
11. [Retry e circuit breaker](#11-retry-e-circuit-breaker)
12. [Escalações](#12-escalações)
13. [Tabela de eventos](#13-tabela-de-eventos)

---

## 1. Visão geral

O workflow é uma sequência de fases executadas por orquestradores hierárquicos:

```
Usuário → /u-dev
            └─ meta-orchestrator (orchestrator.md)
                 ├─ orchestrator-sdd     → workers: u-spec-writer, u-spec-reviewer, u-spec-back, ...
                 ├─ orchestrator-dev     → workers: u-be-planner, u-be-developer, ...
                 ├─ orchestrator-review  → workers: u-be-qa-docs, u-fe-qa-docs
                 └─ orchestrator-test    → workers: u-test-runner
```

**Profundidade de nesting:**

| Nível | Agente | nesting_depth |
|-------|--------|---------------|
| 0 | meta-orchestrator | — (root) |
| 1 | phase orchestrator | 1 |
| 2 | worker | 2 |

Workers que tentarem spawnar sub-agentes recebem `nesting_depth=3` e são bloqueados.

**Fases padrão (ordem de execução):**

| Ordem | Nome | Obrigatória |
|-------|------|-------------|
| 1 | `sdd` | sim |
| 2 | `dev` | sim |
| 3 | `review` | sim |
| 4 | `test` | sim |

A sequência pode ser customizada via `.orch/workflow.json` antes da primeira invocação.

---

## 2. Como um workflow começa

O usuário invoca `/u-dev [SPECS_DIR] {workflow_id}`.

O comando `/u-dev`:
1. Resolve `SPECS_DIR` (do `CLAUDE.md` ou argumento)
2. Resolve `workflow_id` (argumento ou sessões existentes em `.orch/sessions/`)
3. Detecta specs existentes e exibe estimativa de custo/tempo
4. Invoca o meta-orquestrador em loop até status terminal

**Loop de re-invocação do `/u-dev`:**

| Status retornado | Ação |
|-----------------|------|
| `phase_advanced` | Exibe status de progresso e re-invoca imediatamente |
| `escalated` | Surfacing ao humano; aguarda `human_response` |
| `completed` | Exibe relatório final; para |
| `blocked` | Surfacing ao humano; para |
| `error` | Surfacing ao humano; para |

Safety limit: máximo de 10 re-invocações. Se atingido, para com erro `reivocation_limit_reached`.

---

## 3. Meta-orquestrador — ciclo de invocação

Arquivo: `agents/orchestrator.md`  
Modelo: `claude-sonnet-4-6`  
Cada invocação processa exatamente **uma** fase (invariante I5).

### Steps

```
Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 6 → Step 7
```

---

**Step 1 — Infrastructure check**

```bash
run_preflight.py      # verifica ambiente (Python, diretórios, Agent tool)
run_integrity.py      # verifica hash chain do log
run_circuit_check.py  # verifica se circuit breaker está ativado
```

Se qualquer script retornar `"status": "blocked"`: para com `{status: "blocked"}`.

---

**Step 2 — State derivation**

```bash
reduce.py       # reconstrói OrchState a partir do log completo
current_phase.py  # deriva a fase atual
```

Extrai: `workflow_id`, `current_phase`, `phase_status`, `last_seq`, `phases`, `escalation`, `run_status`.

`run_status` é derivado assim:

| Condição | run_status |
|----------|------------|
| `raw_run_status == "escalated"` | `escalated` |
| Todas as fases obrigatórias `completed` | `completed` |
| Nenhuma fase existe | `pending` |
| Default | `active` |

---

**Step 3 — Terminal state check**

- `completed` → emite relatório final e para
- `escalated` → exibe escalação, emite `human_response`, para

---

**Step 4 — First-run initialization** *(só na primeira invocação)*

Gera `workflow_id` (UUID), lê `workflow.json` (se existir) ou usa fases padrão, emite `phase_declared`.

---

**Step 5 — Phase entry**

Determina a próxima fase pendente (menor `order` com `status == "pending"`).  
Emite `phase_entered` com `evidence_seq`.

---

**Step 6 — Spawn phase orchestrator**

Contador de ciclo (máximo 2 — proteção contra loop). Consulta a routing table:

| current_phase | Phase orchestrator |
|---------------|--------------------|
| `sdd` | `orchestrator-sdd` |
| `dev` | `orchestrator-dev` |
| `review` | `orchestrator-review` |
| `test` | `orchestrator-test` |

Spawn via `Agent` tool com `nesting_depth: 1`.

---

**Step 7 — Evaluate return**

**Envelope guard obrigatório:**
- Retorno contendo `"Tool result missing due to internal error"` ou vazio → `{status: "error", reason: "subagent_invalid_response"}`
- Retorno que não é JSON válido → `{status: "error", reason: "subagent_invalid_response", raw: "<primeiros 200 chars>"}`

Em `error`, `blocked` ou `escalated`: lê o último evento do log (`read.py --tail 1`) e inclui como `last_log_event` no relatório ao humano.

| Status recebido | Ação |
|-----------------|------|
| `phase_complete` | Re-lê estado; se `run_status == "completed"` → vai ao Step 3; senão → output `phase_advanced` e para |
| `blocked` | Exibe blocked report com `last_log_event`; para |
| `escalated` | Re-lê estado (`run_status` agora é `escalated`); vai ao Step 3 |
| `error` | Roda circuit breaker check; se tripped → escalação E10; senão → output error e para |

---

## 4. Fase SDD

Arquivo: `agents/orchestrator-sdd.md`  
**Objetivo:** produzir e validar especificações técnicas para todos os domínios.

### Steps

```
Step 0 → Step 0.5 → Step 1 → Step 2 → Step 3 → Step 4 → Step 5 (loop) → Step 6
```

---

**Step 0 — Infrastructure check + nesting depth guard**

Depth guard primeiro: se `nesting_depth >= 3` → blocked.  
Se `log_seq_at_spawn == 0`: roda preflight + integrity + circuit check.

---

**Step 0.5 — Detect workflow_type**

Lê o evento `phase_declared` para determinar o modo de operação:

| workflow_type | Modo | Comportamento |
|---------------|------|---------------|
| `standard` (padrão) | Standard | Scan completo de domínios, gate E99, pipeline completa |
| `improve` | Fast-Track | Patch direcionado de `improve-scope.json`, sem gate E99, pipeline truncada |

---

**Step 1 — State derivation**

Extrai `sdd_tasks` (todas as tasks com `phase == "sdd"`) e `last_seq`.

---

**Step 2 — Assess spec pipeline state** *(Standard mode)*

Escaneia `$SPECS_DIR/domains/*/openapi.yaml` para listar domínios.

Classifica cada domínio:

| Classificação | Condição |
|---------------|----------|
| `new` | Nenhuma sdd task existe para este domínio |
| `in_progress` | Algumas sdd tasks existem mas pipeline incompleta |
| `complete` | Todos os 6 passos em status terminal |
| `failed` | Qualquer passo em `dlq` |

**Step 2 (Fast-Track):** lê `improve-scope.json` com `affected_specs`, `mode_hint`, `improvement_task`.

---

**Step 3 — Human confirmation gate** *(Standard mode)*

Procura por escalação `E99_human_confirmation_required` existente:
- Se existe e tem `human_response(action: confirm_proceed)` → pula para Step 4
- Se existe e tem `human_response(action: abort)` → para
- Se existe sem resposta → retorna `escalated`
- Se não existe → emite painel de progresso + escalação E99 → retorna `escalated`

**Step 3 (Fast-Track):** sem gate (confirmação já foi dada no `/u-improve`).

---

**Step 4 — Task creation**

Pipeline por domínio (dependências encadeadas):

```
spec-writer → spec-reviewer → spec-back → spec-validator → spec-front → spec-validator-front
```

IDs: `sdd_{domain}_{step}`  
Após todos os domínios: cria `sdd_compliance` com dep em todos os `spec-validator-front`.

| Task type | Worker | Tier |
|-----------|--------|------|
| `spec-writer` | `u-spec-writer` | standard |
| `spec-reviewer` | `u-spec-reviewer` | standard |
| `spec-back` | `u-spec-back` | standard |
| `spec-validator` | `u-spec-validator` | standard |
| `spec-front` | `u-spec-front` | standard |
| `spec-compliance` | `u-spec-compliance` | standard |

**Step 4 (Fast-Track):** cria apenas as tasks afetadas por `affected_specs`, conforme `mode_hint`:

| mode_hint | Tasks criadas |
|-----------|---------------|
| `fast-track:patch` | Somente `spec-reviewer` |
| `fast-track:minor` | `{domain_task_type}` → `spec-reviewer` |
| `full` | Pipeline completa para o domínio afetado |

---

**Step 5 — Dispatch loop** *(máx. 30 iterações)*

Cada iteração:

**5.0 — Refresh + stop conditions**
- Roda `reduce.py` e circuit check
- DLQ cascade: tasks pendentes cujo dep está em `dlq` → `task_dlq` imediato
- Stale detection: tasks `running` sem atividade há > 300s (standard) → `task_failed(reason: stale_timeout, retryable: true)`
- Retry re-queue: tasks `scheduled` com `next_retry_at <= now` → `task_retried`
- Rejection cycle check: `spec-writer` ≥ 3 tentativas → escalação E05

**5.1 — Select batch** (até 2 tasks da ready queue, por prioridade de tier)

**5.2 — Claim batch** — emite `task_claimed` + registra worker antes de spawnar

**5.3 — Spawn batch in parallel** — todos os Agent calls em um único response turn

**5.4 — Verify terminal events** — após retorno dos workers, re-lê estado; tasks sem terminal → sintetiza `task_failed(reason: worker_exited_without_terminal, retryable: true)`

**5.5 — Retry decisions** — para cada task `failed`: aplica `should_retry()`

---

**Step 6 — Exit criteria**

```bash
check_handoff_manifest_approved.py   # handoff-manifest.yaml existe e está aprovado
check_all_domains_validated.py       # todos os domínios passaram pela pipeline
check_error_codes_synced.py          # error-codes.md está sincronizado
```

Se todos `"met": true`:  
Emite `phase_exit_criterion_met` (×3) → `phase_exit_approved` → `phase_transitioned(sdd→dev)`  
Retorna `{status: "phase_complete"}`.

---

**Escalações da fase SDD:**

| Código | Condição |
|--------|----------|
| `E99_human_confirmation_required` | Gate de confirmação antes do primeiro dispatch |
| `E05_rejection_cycle_limit` | spec-writer ≥ 3 tentativas ou spec-validator ≥ 2 tentativas |
| `E11_spec_input_missing` | spec-reviewer falhou por arquivos de input ausentes |
| `E08_exit_criteria_not_met` | Todas tasks terminais mas critérios não atendidos |

---

## 5. Fase Dev

Arquivo: `agents/orchestrator-dev.md`  
**Objetivo:** gerar backlog e implementar todas as task contracts.

### Steps

```
Step 0 → Step 1 → Step 2 → Step 3 → Step 4 → Step 5 (loop) → Step 6
```

---

**Step 0 — Infrastructure check + nesting depth guard**

Depth guard: se `nesting_depth >= 3` → blocked.

---

**Step 1 — State derivation**

Extrai:
- `dev_tasks`: tasks com `phase == "dev"`
- `planning_task`: task `dev_planning`
- `impl_tasks`: tasks com ID começando por `dev_tc_`

---

**Step 2 — Validate handoff-manifest + detect stack**

```bash
check_handoff_manifest_approved.py   # manifest deve estar aprovado (SDD completa)
```

Lê o manifest para extrair `stack` (be/fe/fullstack), `handoff_type`, `dev_impact`, `changed_files`.

**Short-circuit:** se `dev_impact == "no_action"` → emite critérios vacuamente → `phase_complete`.

---

**Step 3 — Planning dispatch**

Se `planning_task` ainda não existe: cria task `dev_planning` (tier: `critical`).

Spawn do planner worker:

| Stack | Worker |
|-------|--------|
| `be` ou `fullstack` | `u-be-planner` |
| `fe` | `u-fe-planner` |

Prompt inclui: manifest path, handoff_type, changed_files, dev_impact, paths de saída (`backlog.json`, `backlog.md`, `tc-NNN.md`).

Após retorno: verifica `planning_task.status == "completed"`. Se não → aplica retry ou escalação E07.

---

**Step 4 — Impl task creation**

Lê `backlog.json` gerado pelo planner.  
Para cada task contract, cria `dev_tc_{n}` com:

| Campo | Valor |
|-------|-------|
| `task_id` | `dev_tc_001`, `dev_tc_002`, ... |
| `spec` | caminho do arquivo TC (`session_dir/backlog/tc-NNN.md`) |
| `deps` | lista de outros `dev_tc_{n}` (do grafo de dependências) |
| `tier` | `standard` (ou `critical` se marcado no backlog) |

---

**Step 5 — Dispatch loop** *(máx. 30 iterações)*

Idêntico ao SDD em estrutura. Específico do Dev:

- Batches de até **2 tasks** em paralelo
- Workers por stack:

| Stack | Task type | Worker |
|-------|-----------|--------|
| `be` | `impl` | `u-be-developer` |
| `fe` | `impl` | `u-fe-developer` |

- Falhas não-retryáveis de impl → DLQ + escalação E04

---

**Step 6 — Exit criteria**

```bash
check_all_impl_tasks_terminal.py     # todas as tasks dev_tc_* em estado terminal
check_all_deliveries_qa_ready.py     # todos os delivery.md com qa_ready: true
check_no_open_prohibitions.py        # nenhum prohibition_violation em deliveries
```

Se todos `"met": true`:  
Emite critérios → `phase_exit_approved` → `phase_transitioned(dev→review)`  
Retorna `{status: "phase_complete"}`.

---

**Escalações da fase Dev:**

| Código | Condição |
|--------|----------|
| `E07_planning_failed` | Planning task falhou e não é retryable |
| `E04_critical_task_dlq` | Impl task falhou de forma não-retryável |
| `E08_exit_criteria_not_met` | Todas tasks terminais mas critérios não atendidos |

---

## 6. Fase Review

Arquivo: `agents/orchestrator-review.md`  
**Objetivo:** executar QA em todos os deliverables do Dev e obter aprovação humana.  
**Semi-autônoma:** QA roda sem intervenção humana; transição requer aprovação.

### Steps

```
Step 0 → Step 1 → Step 2 → Step 3 → Step 4 (loop) → Step 5 → Step 6
```

---

**Step 0 — Infrastructure check + nesting depth guard**

---

**Step 1 — State derivation**

Extrai: `review_tasks`, `dev_completed_tasks`.

---

**Step 2 — Detect stack**

Lê `handoff-manifest.yaml` para `stack`.

---

**Step 3 — QA task creation**

Para cada `dev_completed_task` com artifacts:  
Cria task `review_{dev_task_id}` com `spec` apontando para o `delivery.md` correspondente.

Se nenhuma delivery artifact existir → `{status: "blocked"}`.

Workers por stack:

| Stack | Worker |
|-------|--------|
| `be` | `u-be-qa-docs` |
| `fe` | `u-fe-qa-docs` |

---

**Step 4 — Dispatch loop** *(máx. 30 iterações)*

Stale threshold: 300s para tasks `standard`.  
Falhas não-retryáveis → DLQ + escalação E04.

Se QA encontrar divergências de spec (`SPEC-DIVERGENCE:` markers):  
→ escalação E09_spec_divergences_found.

---

**Step 5 — Human approval gate** *(obrigatório antes de qualquer transição)*

Exibe painel de veredictos:

```
Review Phase — QA Verdict Summary
===================================
Task              | Worker         | Verdict   | Issues
──────────────────────────────────────────────────────
dev_tc_001        | u-be-qa-docs   | APPROVED  | —
dev_tc_002        | u-fe-qa-docs   | APPROVED  | 1 warning
```

Emite escalação `E99_human_approval_required` e retorna `escalated`.

Na re-invocação, busca `human_response`:

| action | Ação |
|--------|------|
| `approve` | Prossegue para Step 6 (transição para test) |
| `return_to_dev` | Cria tasks `dev_tc_*` para revisão; emite `phase_transitioned(review→dev)` |
| `return_partial` | Retorna subset de tasks para dev; aprova o restante |

---

**Step 6 — Exit criteria**

```bash
check_all_qa_verdicts_approved.py    # todos os veredictos aprovados
check_documentation_verified.py      # documentação verificada
check_no_open_critical_findings.py   # sem findings críticos abertos
```

Transição: `phase_transitioned(review→test)`.

---

**Escalações da fase Review:**

| Código | Condição |
|--------|----------|
| `E99_human_approval_required` | QA completa; aguardando aprovação |
| `E09_spec_divergences_found` | QA encontrou divergências de spec |
| `E04_critical_task_dlq` | QA task falhou de forma não-retryável |
| `E08_exit_criteria_not_met` | Todas tasks terminais mas critérios não atendidos |

---

## 7. Fase Test

Arquivo: `agents/orchestrator-test.md`  
**Objetivo:** executar test suites em todos os deliverables e validar os resultados.  
**Fully autonomous** quando todos os testes passam; requer intervenção humana em falhas.

### Steps

```
Step 0 → Step 1 → Step 2 → Step 3 → Step 4 (loop) → Step 5
```

---

**Step 0 — Infrastructure check + nesting depth guard**

---

**Step 1 — State derivation**

Extrai: `test_tasks`, `dev_completed_tasks`.

---

**Step 2 — Detect stack**

Lê `handoff-manifest.yaml` para `stack`.

---

**Step 3 — Test task creation**

Para cada `dev_completed_task` com artifacts:  
Cria task `test_{dev_task_id}` com `spec` apontando para o `delivery.md`.

Worker: `u-test-runner` (todos os stacks).

---

**Step 4 — Dispatch loop** *(máx. 30 iterações)*

Stale thresholds por tier: critical 600s, standard 300s, bulk 120s.

Falhas retryáveis: erros de ambiente transitório.  
Falhas não-retryáveis: artifact ausente ou ambiente quebrado → DLQ + E04.

Se testes falharem → escalação `E99_human_test_intervention_required`:

| action | Ação |
|--------|------|
| `return_to_dev` | Retorna tasks com falha para dev |
| `accept_with_failures` | Aceita resultado com falhas documentadas |

---

**Step 5 — Exit criteria**

```bash
check_all_test_tasks_terminal.py   # todas as tasks test_* em estado terminal
check_all_tests_passed.py          # todos os test reports com passed: true
check_no_critical_failures.py      # sem falhas críticas
```

Transição: `phase_transitioned(test→[end])`.  
Retorna `{status: "phase_complete"}` → meta-orchestrator detecta `run_status == "completed"`.

---

**Escalações da fase Test:**

| Código | Condição |
|--------|----------|
| `E99_human_test_intervention_required` | Falhas detectadas; decisão humana necessária |
| `E04_critical_task_dlq` | Test task falhou de forma não-retryável |
| `E08_exit_criteria_not_met` | Todas tasks terminais mas critérios não atendidos |

---

## 8. Sistema de log — event sourcing

### Arquivo

```
.orch/log.jsonl        ← append-only, uma linha JSON por evento
.orch/log.jsonl.lock   ← lock exclusivo POSIX (fcntl.flock)
.orch/blobs/           ← payloads > 3500 bytes externalizados
```

### Estrutura de cada evento

```json
{
  "seq":       1,
  "event_id":  "uuid-v4",
  "ts":        "2024-01-01T00:00:00+00:00",
  "agent":     "orchestrator-dev",
  "event_type": "task_created",
  "task_id":   "dev_tc_001",
  "attempt":   1,
  "data":      { ...payload específico do tipo... },
  "prev_hash": "sha256-do-evento-anterior",
  "hash":      "sha256-deste-evento"
}
```

### Hash chain

Cada evento inclui o SHA-256 do evento anterior (`prev_hash`). O primeiro evento usa `"0" * 64` como `prev_hash`.

Isso cria uma cadeia verificável: qualquer adulteração ou inserção no meio do log quebra todos os hashes subsequentes.

**Verificação:**

```bash
python3 .claude/skills/orch-log/scripts/verify.py
```

Modos: `strict` (para na primeira quebra) ou `audit` (reporta todas as quebras).

### Externalization de blobs

Payloads maiores que 3.500 bytes são armazenados em `.orch/blobs/{event_id}.json` com hash SHA-256 para integridade. O evento no log contém `"_blob_ref": true` e `"_blob_hash": "<sha256>"`.

### Estado derivado — reducer

O estado do sistema **não é armazenado** — é sempre recomputado:

```bash
python3 .claude/skills/orch-state/scripts/reduce.py
```

O reducer lê todos os eventos do log em ordem e aplica handlers:

| Evento | Efeito no estado |
|--------|-----------------|
| `phase_declared` | Inicializa `state.workflow_id`, `state.phases` |
| `phase_entered` | `state.current_phase` = phase; `phase.status` = `active` |
| `phase_exit_criterion_met` | Registra critério como atendido |
| `phase_exit_approved` | `phase.status` = `exit_approved` |
| `phase_transitioned` | `phase.status` = `completed`; limpa `current_phase` |
| `task_created` | Cria `TaskState(status=pending)` |
| `task_claimed` | `task.status` = `running`; registra `worker_id` |
| `task_completed` | `task.status` = `completed`; armazena artifacts |
| `task_failed` | `task.status` = `failed`; incrementa `attempts`; armazena reason |
| `task_scheduled_retry` | `task.status` = `scheduled`; armazena `next_retry_at` |
| `task_retried` | `task.status` = `pending`; incrementa `attempts` |
| `task_dlq` | `task.status` = `dlq` |
| `escalation` | Armazena em `state.escalation` |
| `human_response` | Limpa `state.escalation`; pode resetar circuit breaker |
| `circuit_breaker_tripped` | Armazena em `state.circuit_breaker` |

**Ready promotion:** após cada event que muda status de uma task, o reducer re-avalia deps de todas as tasks `pending`. Se todos os deps estão `completed`, a task passa para `ready`.

### Ferramentas do log

```bash
# Ler eventos com filtros
python3 .claude/skills/orch-log/scripts/read.py \
  [--from-seq N] [--tail N] [--task-id ID] [--event-type TYPE] [--phase NAME]

# Adicionar evento (uso exclusivo dos orchestrators)
python3 .claude/skills/orch-log/scripts/append.py \
  --agent NAME --event-type TYPE [--task-id ID] [--attempt N] --data '{...}'

# Verificar integridade da chain
python3 .claude/skills/orch-log/scripts/verify.py
```

### Hooks automáticos

| Hook | Trigger | Ação |
|------|---------|------|
| `on_stop.py` | Fim de sessão Claude Code | Escreve `.orch/metrics/current.json`; se estado de erro → escreve `.orch/last_error.json` |
| `on_subagent_stop.py` | Worker para sem emitir terminal | Sintetiza `task_failed(retryable=true)` no log para evitar deadlock |

---

## 9. Estados de task

### Diagrama de transições

```
                   ┌─ task_created ──────────────────────────────────────┐
                   ↓                                                      │
              [pending]                                                   │
                   │ deps satisfeitos (reducer)                           │
                   ↓                                                      │
              [ ready ]                                                   │
                   │ task_claimed                                         │
                   ↓                                                      │
             [running]                                                    │
                   │ task_completed           task_failed                 │
                   ↓                               │                      │
           [completed] ◄────(terminal)      retryable?                   │
                                                   │                      │
                              sim ────────────────→│                      │
                           task_scheduled_retry    │                      │
                               [scheduled]         │                      │
                                   │ next_retry_at │ não                  │
                                   │ <= now        ↓                      │
                           task_retried       task_dlq ──────────────────►│
                           [pending]          [ dlq ] (terminal)          │
```

### Tabela de estados

| Status | Significado | É terminal? |
|--------|-------------|-------------|
| `pending` | Aguardando deps | Não |
| `ready` | Deps satisfeitos; pronto para dispatch | Não |
| `running` | Worker em execução | Não |
| `scheduled` | Retry agendado; aguardando `next_retry_at` | Não |
| `failed` | Última tentativa falhou; aguardando decisão | Não |
| `completed` | Executado com sucesso | **Sim** |
| `dlq` | Dead Letter Queue; sem mais retries | **Sim** |
| `cancelled` | Cancelado (reservado; não usado atualmente) | **Sim** |

`TaskStatus.is_terminal()` retorna `True` apenas para `completed` e `dlq`.

---

## 10. Estados de fase

### Diagrama de transições

```
[pending] → phase_entered → [active] → phase_exit_approved → [exit_approved] → phase_transitioned → [completed]
                                ↕
                           phase_paused ↔ phase_resumed → [paused]
```

### Tabela de estados

| Status | Evento que gera | Significado |
|--------|----------------|-------------|
| `pending` | Inicial (após `phase_declared`) | Fase ainda não entrou |
| `active` | `phase_entered` | Fase em execução |
| `exit_approved` | `phase_exit_approved` | Critérios atendidos; aguardando transição |
| `completed` | `phase_transitioned` | Fase concluída |
| `paused` | `phase_paused` | Fase pausada por intervenção humana |

---

## 11. Retry e circuit breaker

### Política de retry por tier

| Tier | max_attempts | base_delay_s | cap_s | Stale threshold |
|------|-------------|--------------|-------|----------------|
| `critical` | 5 | 15s | 600s | 600s |
| `standard` | 3 | 30s | 600s | 300s |
| `bulk` | 1 | 0s | 600s | 120s |

**Backoff:** `min(base * 2^(attempts-1), cap) * uniform(0.8, 1.2)`

### Cap para falhas estruturais

Falhas que indicam que o agente **não conseguiu executar** (não é erro lógico da task) são limitadas a 1 retry independentemente da política do tier:

| Reason | Significado |
|--------|-------------|
| `subagent_invalid_response` | Agent retornou inválido ou erro de ferramenta |
| `worker_exited_without_terminal` | Worker parou sem emitir evento terminal |
| `stale_timeout` | Worker ficou sem atividade além do threshold |

Após 2 tentativas com esses reasons → `should_retry()` retorna `False` → DLQ.

### Circuit breaker

Monitora a frequência de falhas numa janela deslizante.

| Parâmetro | Valor padrão |
|-----------|-------------|
| Janela | 10 minutos |
| Threshold | 50 falhas |
| Escopo | workflow |

Quando tripped:
- `orchestrator-dev` para o loop com `{status: "error", summary: "circuit_tripped"}`
- Meta-orchestrator emite escalação E10 e para

Reset manual:
```bash
python3 .claude/scripts/circuit_breaker.py --reset --confirm --operator <email> --notes "..."
```
Emite `human_response(action: reset_circuit_breaker)` que limpa o estado no reducer.

---

## 12. Escalações

Todas as escalações pausam o workflow e exigem `human_response` para retomar.

### Como responder

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent operator \
  --event-type human_response \
  --data '{"escalation_seq": <seq_do_evento_escalation>, "action": "<action>", "notes": "<opcional>"}'
```

Após responder: re-invocar o orquestrador (o `/u-dev` loop faz isso automaticamente).

### Tabela completa de escalações

| Código | Severidade | Emitido por | Condição | Actions válidas |
|--------|-----------|-------------|----------|-----------------|
| `E04_critical_task_dlq` | critical | orchestrator-dev, orchestrator-test | Impl/test task não-retryável em DLQ | (resolve + re-invoke) |
| `E05_rejection_cycle_limit` | critical | orchestrator-sdd | spec-writer ≥ 3 tentativas | `confirm_proceed`, `abort` |
| `E07_planning_failed` | critical | orchestrator-dev | Planning task falhou e não é retryable | (resolve + re-invoke) |
| `E08_exit_criteria_not_met` | warning | todos os phase orchestrators | Tasks terminais mas critérios não atendidos | (resolve + re-invoke) |
| `E09_spec_divergences_found` | warning | orchestrator-review | QA encontrou divergências de spec | (abrir CRs + re-invoke) |
| `E10_phase_orchestrator_error` | critical | meta-orchestrator | Phase orchestrator retornou error + circuit tripped | `inspect log`, `circuit_breaker.py reset` |
| `E11_spec_input_missing` | critical | orchestrator-sdd | spec-reviewer falhou por arquivos ausentes | (criar arquivos + re-invoke) |
| `E99_human_confirmation_required` | info | orchestrator-sdd | Gate antes do primeiro dispatch (SDD) | `confirm_proceed`, `abort` |
| `E99_human_approval_required` | info | orchestrator-review | QA completa; aprovação necessária | `approve`, `return_to_dev`, `return_partial` |
| `E99_human_test_intervention_required` | warning | orchestrator-test | Falhas em testes | `return_to_dev`, `accept_with_failures` |

---

## 13. Tabela de eventos

Os 21 tipos de evento formam a linguagem completa do sistema.

### Task lifecycle (8 tipos)

| Evento | Emitido por | Campos obrigatórios em `data` | Efeito no estado |
|--------|------------|------------------------------|-----------------|
| `task_created` | orchestrator | `phase`, `tier`, `type`, `spec`, `deps` | Cria task em `pending` |
| `task_claimed` | orchestrator | `phase`, `worker_type`, `worker_id` | task → `running` |
| `task_progress` | **worker only** | `phase`, `note` | Atualiza `last_event_at` (sem mudança de status) |
| `task_completed` | **worker only** | `phase`, `artifacts`, `summary` | task → `completed`; deps downstream → avalia `ready` |
| `task_failed` | worker ou synthesized | `phase`, `reason`, `retryable` | task → `failed`; incrementa `attempts` |
| `task_scheduled_retry` | orchestrator | `phase`, `next_retry_at`, `backoff_seconds`, `previous_failure_seq` | task → `scheduled` |
| `task_retried` | orchestrator | `phase`, `previous_attempt`, `scheduled_retry_seq` | task → `pending`; permite novo dispatch |
| `task_dlq` | orchestrator | `phase`, `reason`, `last_error` | task → `dlq` (terminal) |

### Phase lifecycle (7 tipos)

| Evento | Emitido por | Campos obrigatórios em `data` | Efeito no estado |
|--------|------------|------------------------------|-----------------|
| `phase_declared` | meta-orchestrator | `workflow_id`, `phases` (array) | Inicializa `OrchState` com lista de fases |
| `phase_entered` | meta-orchestrator | `phase`, `order`, `evidence_seq` | fase → `active`; define `current_phase` |
| `phase_exit_criterion_met` | phase orchestrator | `phase`, `criterion` | Registra critério atendido |
| `phase_exit_approved` | phase orchestrator | `phase`, `criteria_met`, `next_phase` | fase → `exit_approved` |
| `phase_transitioned` | phase orchestrator | `from_phase`, `to_phase`, `evidence_seq` | fase → `completed`; limpa `current_phase` |
| `phase_paused` | operator | `phase`, `reason` | fase → `paused` |
| `phase_resumed` | operator | `phase`, `reason` | fase → `active` |

### Management e operações (6 tipos)

| Evento | Emitido por | Campos obrigatórios em `data` | Efeito no estado |
|--------|------------|------------------------------|-----------------|
| `escalation` | orchestrator | `code`, `severity`, `reason`, `evidence`, `suggested_actions` | Armazena em `state.escalation`; bloqueia progresso |
| `human_response` | operador | `escalation_seq`, `action`, `operator` | Limpa `state.escalation`; pode resetar circuit breaker |
| `circuit_breaker_tripped` | orchestrator | `failure_count`, `window_minutes`, `threshold` | Armazena em `state.circuit_breaker` |
| `snapshot` | on_stop hook | `state` (OrchState serializado) | Ponto de restauração (otimização — não usado no restore atual) |
| `log_recovered` | recovery | `recovered_events`, `reason` | Documenta recovery de log corrompido |
| `preflight_failed` | preflight script | `check`, `reason`, `detail` | Documenta falha de pré-condição |

---

*Gerado a partir do código-fonte em `dist2/` — commit `5ca3ab9`.*
