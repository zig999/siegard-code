# Siegard — Fases, Rotas e Gates

> Visão resumida de como o siegard funciona e como a gestão de workflow opera: as **fases**, as **rotas** (entrada e roteamento de workers) e os **gates** (humanos, exit criteria e infraestrutura).
>
> Fonte da verdade: `dist/.claude/`. Para o detalhe interno da engine (event sourcing, dispatch loop, retry, circuit breaker), ver [workflow.md](workflow.md).

---

## 1. Como o siegard funciona (em uma página)

O siegard é uma **engine de orquestração event-sourced** para sub-agentes Claude. Coordena a execução de um workflow multi-fase: cada fase tem um orchestrator próprio, workers especializados e gates determinísticos.

```
Usuário ──/comando──▶ orchestrator (meta) ──spawn──▶ orchestrator-{sdd,dev,review,test} ──spawn──▶ workers
                            │                                   │                                    │
                            └────────── log.jsonl (fonte única de verdade) ◀── emit (orch-report) ──┘
```

Dois tiers:

| Tier | Componente | Responsabilidade |
|------|-----------|------------------|
| 1 — Meta | `orchestrator` | Só **roteia**. Lê a fase atual do log, roda checks de infra, declara fases na primeira execução, faz spawn de **um** phase orchestrator por invocação. Zero lógica de domínio. |
| 2 — Fase | `orchestrator-sdd` / `-dev` / `-review` / `-test` | Executam o **dispatch loop** da fase, fazem spawn dos workers, aplicam retry/DLQ, gerenciam os gates humanos e avaliam os exit criteria. |
| 3 — Worker | `u-spec-*`, `u-be-*`, `u-fe-*`, `u-test-runner`, … | Executores concretos. Só emitem `task_progress` / `task_completed` / `task_failed` via `orch-report`. |

**Regra de ouro:** todo estado é derivado do log. Nenhum componente guarda estado próprio. Crash recovery = releia o log.

---

## 2. Rotas de entrada (comandos)

Os comandos são os pontos de entrada do usuário no sistema. A maioria entra em uma fase; alguns são utilitários que não alteram fase.

| Comando | Rota para | Propósito |
|---------|-----------|-----------|
| `/u-spec` | Inicia/retoma a fase **SDD** | Pipeline de especificação (OpenAPI, `.spec.md`, `.back.md`, telas de UI) para um ou mais domínios. |
| `/u-dev` | Inicia a fase **Dev** | Sessão de desenvolvimento: planner → developers → entregas, a partir de specs aprovadas. |
| `/u-orchestrator` | **Orquestração completa** | Retoma/avança qualquer workflow a partir do estado atual do log; roteia automaticamente entre fases. |
| `/u-improve` | **Fluxo de melhoria** | Registra uma mudança intencional (bug fix, ajuste, enhancement), classifica o impacto em spec e roteia para SDD ou Dev. |
| `/u-reverse-spec` | **Engenharia reversa** | Gera specs (status `draft`) a partir de código existente. |
| `/u-fe-validate` | **Validação avulsa** | Valida qualidade de código e design system de frontend; não cria sessão nem Task Contract. |
| `/u-cleanup` | **Manutenção de runtime** | GC de blobs órfãos, purge de arquivos temporários `.orch`, arquivamento/exclusão de logs. Não muda fase. |
| `/u-doc-cleanup` | **Manutenção de docs** | Remove ruído histórico da documentação, mantendo só o estado atual. Não muda fase. |

A fase corrente é sempre **derivada do log** (`current_phase.py`). Reinvocar o orchestrator depois de um `phase_advanced`, de um `human_response` ou de um crash sempre retoma do ponto correto.

---

## 3. As fases do workflow

Workflow padrão, declarado em `phase_declared` na primeira execução (override via `.orch/workflow.json`):

```
sdd → dev → review → test
```

| Ordem | Fase | Orchestrator | Objetivo | Gate humano |
|-------|------|--------------|----------|-------------|
| 1 | `sdd` | `orchestrator-sdd` | Escrever e aprovar todas as specs antes do handoff. | **Sim** — confirmação antes do 1º dispatch (`E99`), exceto fluxo `improve`. |
| 2 | `dev` | `orchestrator-dev` | Planejar o backlog e implementar os Task Contracts. | **Não** — totalmente autônomo. |
| 3 | `review` | `orchestrator-review` | QA das entregas; aprovação antes de avançar. | **Sim** — aprovação (`E99`), com possível auto-aprovação (`E18`). |
| 4 | `test` | `orchestrator-test` | Executar suites de teste; escalar só em falha. | **Condicional** — `E99` apenas se houver falhas. |

### 3.1 SDD — modos de operação

A fase SDD inicia **sempre** com um worker de triage (`u-spec-triage`) que escreve `triage.json`. A partir dele, o orchestrator deriva o `effective_mode`:

| Modo | Quando | Comportamento |
|------|--------|---------------|
| `standard` | `/u-spec` novo, ou improve com mudança ampla | Back leg por domain: writer → reviewer → back → validator. Front leg uma vez por requisito (só se `ui_task == true`): spec-front → spec-validator. Depois `spec-compliance`. Exit exige `all_domains_validated`. |
| `targeted` | improve com mudança localizada | Só `domain_task_type` + `spec-reviewer` por spec afetada; pula writer/validators/compliance. Exit usa `all_improve_reviewers_completed` no lugar de `all_domains_validated`. |
| (implementation_only) | improve sem mudança de spec | SDD encerra imediatamente via `task_skipped`; segue direto para Dev. |

O fluxo `/u-improve` define `bypass_e99=true` → o gate de confirmação do SDD é dispensado.

---

## 4. Rotas de workers (roteamento dentro da fase)

Cada fase tem um `select_worker.py` que mapeia `task.type` (+ `stack`) → worker. Resumo:

### SDD (`phase-sdd-rules`)

| `task.type` | Worker |
|-------------|--------|
| `spec-triage` | `u-spec-triage` |
| `spec-writer` | `u-spec-writer` |
| `spec-reviewer` | `u-spec-reviewer` |
| `spec-back` | `u-spec-back` |
| `spec-front` | `u-spec-front` |
| `spec-validator` | `u-spec-validator` |
| `spec-compliance` | `u-spec-compliance` |
| *(default)* | `u-spec-writer` |

### Dev (`phase-dev-rules`) — roteia por `type` + `stack`

| `task.type` | `stack` | Worker |
|-------------|---------|--------|
| `planning` | `be` / `fullstack` | `u-be-planner` |
| `planning` | `fe` | `u-fe-planner` |
| `impl` | `be` / `fullstack` | `u-be-developer` |
| `impl` | `fe` | `u-fe-developer` |
| `spec` | `fe` / `fullstack` | `u-fe-spec-writer` |
| `spec` | `be` | `u-be-developer` |
| *(default)* | qualquer | `u-be-developer` |

> `fullstack` no planning faz spawn dos **dois** planners em paralelo. No dispatch loop, cada task usa `task.stack` se definido, senão cai no `project_stack`.

### Review (`phase-review-rules`)

| `task.type` | `stack` | Worker |
|-------------|---------|--------|
| `qa` | `be` / `fullstack` | `u-be-qa-docs` |
| `qa` | `fe` | `u-fe-qa-docs` |
| `architecture-review` | qualquer | `u-architecture-reviewer` |
| `security-review` | qualquer | `u-security-reviewer` |
| *(default)* | — | `u-be-qa-docs` |

### Test (`phase-test-rules`)

| `task.type` | Worker |
|-------------|--------|
| `test-run` (qualquer stack) | `u-test-runner` |
| *(default)* | `u-test-runner` |

---

## 5. Gates

Existem **três tipos de gate**, em camadas distintas. Os exit criteria são a única forma de uma fase transicionar.

### 5.1 Gate de infraestrutura (entrada do meta)

Antes de qualquer fase, o `orchestrator` roda três checks (`orch-infra`). Qualquer falha → `status: blocked`, sem dispatch:

| Check | Script |
|-------|--------|
| Preflight | `run_preflight.py` |
| Integridade do log (hash chain) | `run_integrity.py` |
| Circuit breaker | `run_circuit_check.py` |

### 5.2 Gates humanos (assíncronos via `escalation` + `human_response`)

Nenhum orchestrator bloqueia esperando input. Ele **emite uma escalation, para, e o humano reinvoca** após responder. Exceção (caminho usual): escalations `info` **com `options`** (ex.: gate de confirmação `E99`) são apresentadas interativamente pelo meta-orchestrator via `AskUserQuestion`, que grava o `human_response` e retoma na mesma invocação — sem `append.py` manual.

| Fase | Código | Quando | Opções |
|------|--------|--------|--------|
| `sdd` | `E99_human_confirmation_required` | Antes do 1º dispatch (exceto improve) | `confirm_proceed`, `abort` |
| `review` | `E99_human_approval_required` | Verdicts de QA prontos | `approve`, `return_to_dev`, `return_partial` |
| `review` | `E18_auto_approval_granted` | Tudo `micro` + aprovado + sem findings graves → orchestrator sintetiza a aprovação | (automático; operador pode reverter com `return_to_dev`) |
| `test` | `E99_human_test_intervention_required` | Só se há falhas de teste | `accept_with_failures`, `return_to_dev` |

### 5.3 Exit criteria (gate de transição de fase)

Ao fim de cada iteração do dispatch loop, o orchestrator roda os scripts `check_*.py` da fase (declarados em `exit-criteria.json`). **Todos** precisam retornar `met: true` para a fase transicionar. Antes disso, há um **DLQ guard**: qualquer task em DLQ bloqueia a saída.

| Fase | Critério | Script | Verifica |
|------|----------|--------|----------|
| `sdd` | `handoff_manifest_approved` | `check_handoff_manifest_approved.py` | `handoff-manifest.yaml` existe, passa nas 13 regras do `u-handoff-validator` + sha256, e tem `Status: approved`. Fail-closed. |
| `sdd` | `all_domains_validated` *(standard)* | `check_all_domains_validated.py` | `_validation/` existe e não há nenhum `Status: INVALID`. |
| `sdd` | `all_improve_reviewers_completed` *(targeted)* | `check_all_improve_reviewers_completed.py` | Todo `sdd_improve_*_spec-reviewer` chegou a `completed`. Substitui o critério acima no modo targeted. |
| `sdd` | `error_codes_synced` | `check_error_codes_synced.py` | Todo error code nas specs está registrado em `error-codes.md`. Trivialmente satisfeito se não há codes. |
| `dev` | `all_impl_tasks_terminal` | `check_all_impl_tasks_terminal.py` | Toda task de dev em estado terminal (`completed` ou `dlq`). DLQ é terminal mas bloqueia via guard. |
| `dev` | `all_deliveries_qa_ready` | `check_all_deliveries_qa_ready.py` | Todo `delivery.md` tem `qa_ready: true`. |
| `dev` | `no_open_prohibitions` | `check_no_open_prohibitions.py` | Nenhum `delivery.md` tem `prohibition_violations` não-vazio. |
| `review` | `all_qa_verdicts_approved` | `check_all_qa_verdicts_approved.py` | Existe ≥1 verdict e todos têm `verdict: approved`. |
| `review` | `no_open_critical_findings` | `check_no_open_critical_findings.py` | Nenhum verdict com `severity: critical`. |
| `review` | `documentation_verified` | `check_documentation_verified.py` | ≥1 verdict com `documentation_verified: true` e nenhum `false`. |
| `test` | `all_test_tasks_terminal` | `check_all_test_tasks_terminal.py` | Toda task de teste `completed` e **zero** em DLQ. |
| `test` | `all_tests_passed` | `check_all_tests_passed.py` | Todo report de teste tem `result: passed`. |
| `test` | `no_critical_failures` | `check_no_critical_failures.py` | Nenhum report com falha `severity: critical`. |

> Protocolo dos checkers: imprimem JSON `{"criterion","met","evidence","details"}` em stdout, exit code 0 sempre (erros vão no JSON). Ver [phases.md](../extras/phases.md) para o contrato completo.

---

## 6. Como uma fase transiciona (gate flow)

```
orchestrator (meta)
  ├─ Step 1  infra gate (preflight/integrity/circuit)  ── falha → blocked
  ├─ Step 2  deriva estado do log (current_phase, run_status)
  ├─ Step 4  primeira execução → phase_declared [sdd,dev,review,test]
  ├─ Step 5  phase_entered (com evidence_seq)
  └─ Step 6  spawn de UM phase orchestrator
                │
                ▼
        orchestrator-{fase}
          ├─ dispatch loop (máx 30 iterações): select batch → claim → spawn paralelo → verify → retry/DLQ
          ├─ [gate humano se aplicável]  → escalation → para → reinvocação
          └─ exit criteria todos met?
                ├─ não → continua / repair loop / E08
                └─ sim → phase_exit_criterion_met × N
                         phase_exit_approved
                         phase_transitioned (fase → próxima)
                         return phase_complete
                │
                ▼
  Step 7  meta recebe phase_complete
          ├─ todas as fases completas → status: completed
          └─ senão → status: phase_advanced  (usuário reinvoca p/ a próxima fase)
```

Cada invocação do meta processa **exatamente uma** fase (invariante I5), o que limita o crescimento de contexto. O caller (ex.: `/u-dev`) faz o loop de reinvocações.

---

## 7. Escalation codes (referência rápida)

Gates e pontos de intervenção. Referência completa: `dist/.claude/ESCALATION_CODES.md`.

| Código | Severidade | Emitido por | Condição |
|--------|-----------|-------------|----------|
| `E04_critical_task_dlq` | critical | dev, test | Task de impl/test não-retryável foi para DLQ. |
| `E05_rejection_cycle_limit` | critical | sdd | spec-writer ≥3 tentativas ou spec-validator ≥2. |
| `E06_dispatch_loop_limit` | critical | sdd | Dispatch loop atingiu 30 iterações sem convergir. |
| `E07_planning_failed` | critical | dev | Task de planning falhou de forma não-retryável. |
| `E08_exit_criteria_not_met` | warning | todas | Tasks terminais, mas exit criteria não passaram. |
| `E09_spec_divergences_found` | warning | review | QA encontrou divergências de spec (`SPEC-DIVERGENCE:`). |
| `E10_phase_orchestrator_error` | critical | meta | Phase orchestrator retornou error + circuit tripped. |
| `E11_spec_input_missing` | critical | sdd | spec-reviewer falhou não-retryável — inputs ausentes. |
| `E12_state_reduction_failed` | critical | todas | `reduce.py` falhou — log corrompido ou versão divergente. |
| `E13_subagent_invalid_response` | critical | meta | Phase orchestrator retornou não-JSON/vazio (após auto-retry). |
| `E14_improve_spec_confirmation` | info | meta (`u-improve`) | Confirmação pré-pipeline do fluxo improve. |
| `E16_shared_build_failure` | critical | review | Build compartilhado falhou — QA não pode iniciar. |
| `E17_suite_parser_degraded` | warning | review | Parser de testes degradado — fallback para modo legado. |
| `E18_auto_approval_granted` | info | review | Gate de auto-aprovação satisfeito. |
| `E19_qa_mode_classifier_failed` | warning | review | Classificador de qa_mode falhou — task criada como `standard`. |
| `E99_human_confirmation_required` | info | sdd | Gate antes do 1º dispatch. |
| `E99_human_approval_required` | info | review | Verdicts prontos para aprovação. |
| `E99_human_test_intervention_required` | warning | test | Falhas de teste detectadas. |
