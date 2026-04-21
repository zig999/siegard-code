# Orquestrador Multi-Fase de Agents Claude Code — Arquitetura

> Documento de arquitetura técnica consolidado.
> Stack: Claude Code v2.1+, Python 3.10+ (stdlib pura), sub-agents nativos.
> Escopo: single-machine, workflows multi-fase, pequeno/médio time.

---

## Metadados

| Campo | Valor |
|---|---|
| Status | Design validado |
| Stack | Python 3.10+, Claude Code v2.1+ |
| Plataformas | Linux, macOS, WSL2 |
| Dependências runtime | Zero (stdlib Python) |
| Maturidade | 7-8/10 com testes automatizados, 8-9/10 com uso prolongado |

---

## Sumário

1. [Contexto e problema](#1-contexto-e-problema)
2. [Requisitos](#2-requisitos)
3. [Decisões arquiteturais](#3-decisões-arquiteturais)
4. [Princípios invariantes](#4-princípios-invariantes)
5. [Visão de alto nível](#5-visão-de-alto-nível)
6. [Modelo de fases](#6-modelo-de-fases)
7. [Modelo de dados](#7-modelo-de-dados)
8. [Máquinas de estados](#8-máquinas-de-estados)
9. [Componentes](#9-componentes)
10. [Retry, backoff e circuit breaker](#10-retry-backoff-e-circuit-breaker)
11. [Integridade e recovery de log](#11-integridade-e-recovery-de-log)
12. [Validação de payloads](#12-validação-de-payloads)
13. [Preflight de premissas](#13-preflight-de-premissas)
14. [Fluxos principais](#14-fluxos-principais)
15. [Concorrência e consistência](#15-concorrência-e-consistência)
16. [Observabilidade](#16-observabilidade)
17. [Modelo de falhas](#17-modelo-de-falhas)
18. [Segurança](#18-segurança)
19. [Configuração](#19-configuração)
20. [Estrutura de arquivos](#20-estrutura-de-arquivos)
21. [Trade-offs e limitações](#21-trade-offs-e-limitações)
22. [Glossário](#22-glossário)

---

## 1. Contexto e problema

Desenvolvedores usando Claude Code em workflows complexos enfrentam três limitações recorrentes:

**Perda de contexto entre tasks**: quando uma tarefa envolve múltiplos passos (criar migration → gerar types → criar endpoint → criar cliente), o encadeamento manual via prompt perde contexto entre invocações.

**Inconsistência de execução**: o mesmo tipo de workflow produz resultados diferentes dependendo de como é invocado, quais sub-agents são escolhidos automaticamente, e da ordem dos pedidos.

**Falta de rastreabilidade**: quando algo dá errado, é difícil reconstruir o que aconteceu — qual agent fez o quê, em que ordem, com que resultado.

Esta arquitetura endereça esses três problemas através de orquestração explícita baseada em event sourcing, com workflows multi-fase auditáveis e regras de negócio modulares.

---

## 2. Requisitos

### 2.1 Funcionais

| ID | Requisito |
|---|---|
| F1 | Executar workflows com múltiplas tasks dependentes |
| F2 | Coordenar execução paralela respeitando dependências |
| F3 | Suportar retry automático com backoff exponencial |
| F4 | Isolar falhas — uma task falhada não derruba o workflow |
| F5 | Permitir inspeção do estado corrente a qualquer momento |
| F6 | Suportar reconstrução de estado após crash |
| F7 | Registrar trilha de auditoria de cada decisão |
| F8 | Permitir intervenção humana via escalação |
| F9 | Suportar workflows multi-fase com regras de negócio isoladas por fase |
| F10 | Critérios de saída de fase expressos em código testável |

### 2.2 Não-funcionais

| ID | Requisito | Alvo |
|---|---|---|
| NF1 | Tempo de decisão do orquestrador | < 5s (p95) |
| NF2 | Overhead por task coordenada | < 1s |
| NF3 | Custo adicional por workflow | < 20% vs. execução manual |
| NF4 | Tempo de recuperação após crash | < 30s |
| NF5 | Integridade do log sob concorrência | 100% (zero corrupção) |
| NF6 | Dependências externas (runtime) | Zero |
| NF7 | Throughput de eventos | ~1000/s (suficiente para caso de uso) |

### 2.3 Fora de escopo

- Execução distribuída em múltiplas máquinas
- Comunicação peer-to-peer entre workers
- Fases executando em paralelo
- Suporte nativo a Windows (requer WSL2)
- Integração com observabilidade enterprise (OTEL export)
- Multi-tenancy ou isolamento por usuário

---

## 3. Decisões arquiteturais

### 3.1 Event sourcing como fonte única da verdade

Todo estado do sistema é derivado de um log append-only de eventos.

**Motivação**: auditabilidade completa, reprodutibilidade, tolerância a crash, time-travel.

**Consequência**: nenhum componente mantém estado próprio; correções são novos eventos, nunca edições.

### 3.2 JSONL append-only com hash chain SHA-256

Eventos são persistidos em `.orch/log.jsonl`, uma linha por evento, encadeados por hash.

**Motivação**: append atômico POSIX, legibilidade com ferramentas Unix, detecção mecânica de corrupção.

**Alternativas rejeitadas**: SQLite (complexidade sem ganho), JSON único (não suporta append concorrente), binary formats (não grep-friendly).

### 3.3 Locking via `fcntl.flock`

Escritas concorrentes coordenadas via POSIX file lock.

**Motivação**: padrão de 40+ anos, kernel-managed, zero dependências, libera automaticamente em crash.

**Consequência**: requer POSIX (Windows via WSL2).

### 3.4 Sub-agent como orquestrador

O orquestrador é um sub-agent (`.claude/agents/orchestrator.md`) que decide ações lendo o log.

**Motivação**: isola context window, permite model routing (Opus no orquestrador, Sonnet/Haiku em workers), integra nativamente com Agent tool.

**Consequência**: cada ciclo de decisão é uma nova invocação; sem loop contínuo.

### 3.5 Workers como sub-agents especializados com tools restritas

Cada tipo de task tem um sub-agent worker dedicado (code-writer, test-runner, code-reviewer), com tools mínimas necessárias.

**Motivação**: least privilege, context isolado, model routing por tier.

### 3.6 Skills para coordenação e regras de fase

Funcionalidades determinísticas vivem em skills (`orch-log`, `orch-state`, `orch-report`, `phase-{nome}-rules`), com scripts Python em `scripts/`.

**Motivação**: progressive disclosure (scripts não consomem context), alinhamento com padrão oficial Anthropic, testabilidade.

### 3.7 Hooks para robustez fora do LLM

Comportamentos críticos de robustez (detecção de worker silencioso, snapshot final) rodam em hooks Python, não no LLM.

**Motivação**: determinismo, resiliência, zero consumo de tokens.

### 3.8 Python stdlib pura

Scripts usam apenas Python 3.10+ stdlib.

**Motivação**: zero dependências, startup rápido, presente em qualquer ambiente, alinhado com skills oficiais da Anthropic.

### 3.9 Fases como primitiva de primeira classe

Workflows multi-fase (SDD → Dev → Review → Test) são suportados nativamente através de fase como conceito modelado no log, com skills dedicadas por fase.

**Motivação**: sub-agents do Claude Code não podem spawnar outros sub-agents; orquestrador único com skills por fase resolve isso preservando separação de regras de negócio.

**Consequência**: uma fase ativa por vez (paralelismo entre fases não suportado).

---

## 4. Princípios invariantes

Invariantes que não podem ser violados. Servem como critério de review para qualquer mudança arquitetural.

| # | Princípio |
|---|---|
| P1 | Log é a verdade. Todo estado é derivado. |
| P2 | Orquestrador é função pura do log. Sem estado próprio. |
| P3 | Append-only. Correções via novos eventos. |
| P4 | Idempotência por chave `(task_id, attempt, event_type)`. |
| P5 | Determinismo ordenado. Ties resolvidos por (priority, seq). |
| P6 | Least privilege. Workers têm só as tools necessárias. |
| P7 | Robustez via hooks. Garantias críticas fora do LLM. |
| P8 | Evidência obrigatória. Toda decisão cita eventos que a justificam. |
| P9 | Toda task pertence a exatamente uma fase. |
| P10 | Transição de fase é evento auditável. |
| P11 | Critérios de saída em código testável, não em prompt. |
| P12 | Fase corrente é derivada do log, não armazenada fora dele. |

---

## 5. Visão de alto nível

### 5.1 Diagrama de componentes

```
┌─────────────────────────────────────────────────────────────────┐
│  Sessão Claude Code                                             │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Main Thread (humano conversa aqui)                       │  │
│  │  Invoca: "Use o orchestrator para..."                     │  │
│  └────────────────────────┬──────────────────────────────────┘  │
│                           │                                     │
│                           ▼                                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Orchestrator (sub-agent, Opus)                           │  │
│  │                                                           │  │
│  │  Carrega: orch-log, orch-state, phase-{corrente}-rules    │  │
│  │  Tools: Agent, Bash, Read                                 │  │
│  │                                                           │  │
│  │  Ciclo: verify → phase → state → decide → emit → spawn   │  │
│  └──────────┬────────────────────────────────────┬───────────┘  │
│             │ Agent()                            │ Bash()       │
│             ▼                                    ▼              │
│  ┌──────────────────────┐              ┌──────────────────┐    │
│  │  Workers             │              │  Skill scripts   │    │
│  │  (sub-agents,        │              │  (Python puro)   │    │
│  │   Sonnet/Haiku)      │              │                  │    │
│  │                      │              │  append.py       │    │
│  │  code-writer         │              │  read.py         │    │
│  │  test-runner         │              │  verify.py       │    │
│  │  code-reviewer       │              │  reduce.py       │    │
│  │  migration-writer    │              │  snapshot.py     │    │
│  │  ...                 │              │  emit.py         │    │
│  │                      │              │  check_*.py      │    │
│  │  Carregam:           │              │  preflight.py    │    │
│  │   orch-report        │              │  circuit_*.py    │    │
│  └──────────┬───────────┘              └─────────┬────────┘    │
│             │                                    │              │
│             └──────────────┬─────────────────────┘              │
│                            │                                    │
│                            ▼                                    │
│               ┌────────────────────────┐                        │
│               │  Event Log             │                        │
│               │  .orch/log.jsonl       │                        │
│               │  (append-only +        │                        │
│               │   hash chain)          │                        │
│               └────────────────────────┘                        │
│                            ▲                                    │
│                            │ observa                            │
│               ┌────────────────────────┐                        │
│               │  Hooks (Python)        │                        │
│               │  on_subagent_stop      │                        │
│               │  on_stop               │                        │
│               └────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ (filesystem)
          ┌──────────────────────────────────────┐
          │  .orch/                              │
          │  ├── log.jsonl         ← verdade     │
          │  ├── log.jsonl.lock                  │
          │  ├── config.json                     │
          │  ├── state/snapshot-NNNN.json        │
          │  ├── blobs/{event_id}.json           │
          │  ├── dlq/t_NNNN.json                 │
          │  ├── audit/YYYY-MM-DD.jsonl          │
          │  └── metrics/current.json            │
          └──────────────────────────────────────┘
```

### 5.2 Camadas conceituais

| Camada | Responsabilidade |
|---|---|
| **Global** (`orch_core.py`, skills orch-*) | Event sourcing, locking, hash chain, reducer genérico, retry genérico |
| **Meta** (`orchestrator.md`) | Qual fase está ativa, que skill usar, transições |
| **Por fase** (`phase-{nome}-rules/`) | Regras específicas da fase, routing de workers, critérios de saída |
| **Execução** (workers: `code-writer.md`, etc.) | Implementação concreta de tasks |

Cada camada tem bounded context — não conhece detalhes das outras além da interface acordada.

---

## 6. Modelo de fases

### 6.1 O que é uma fase

Um estágio bem-definido de um workflow, com:

- **Nome** único (ex: `sdd`, `dev`, `review`, `test`)
- **Entrada**: pré-condições para começar
- **Saída**: critérios formais que permitem transição
- **Regras de negócio**: em skill dedicada `phase-{nome}-rules/`
- **Tasks**: conjunto de tasks com `data.phase` correspondente

### 6.2 Fases canônicas

Para workflows de desenvolvimento de software:

| Fase | Propósito | Workers típicos | Critério de saída típico |
|---|---|---|---|
| SDD | Produzir specs completas e decompor em tasks | sdd-analyst, sdd-decomposer | Todas tasks futuras declaradas, specs validadas, deps acíclicas |
| Dev | Implementar código conforme specs | code-writer, migration-writer, component-builder | Todas tasks de impl em estado terminal |
| Review | Validar qualidade e padrões | code-reviewer, security-reviewer | Zero findings críticos em aberto |
| Test | Validar via testes automatizados | test-writer, test-runner | Testes passam, cobertura ≥ alvo |

### 6.3 Workflows customizados

Fases não são hardcoded. Projeto pode definir via `.orch/config.json`:

```json
{
  "phases": {
    "default_workflow": "dev-cycle",
    "workflows": {
      "dev-cycle": {"phases": ["sdd", "dev", "review", "test"]},
      "bug-fix":   {"phases": ["reproduce", "fix", "verify", "regression"]},
      "refactor":  {"phases": ["analyze", "migrate", "verify"]},
      "spike":     {"phases": ["research", "document"]}
    }
  }
}
```

### 6.4 Relação fase ↔ task

**Uma task pertence a exatamente uma fase**. Declarada em `task_created`:

```json
{
  "event_type": "task_created",
  "task_id": "t_0042",
  "data": {
    "phase": "dev",
    "deps": ["t_0041"],
    "tier": "standard",
    "type": "implementation",
    "spec": "..."
  }
}
```

Dependências cross-phase são permitidas, mas task só vira `ready` quando:
1. Todas as `deps` explícitas estão `completed` **E**
2. A fase da task está em estado `active`

### 6.5 Tiers de task

Tier classifica criticidade e governa retry, timeout, modelo:

| Tier | max_attempts | stale_seconds | Modelo sugerido |
|---|---|---|---|
| `critical` | 5 | 600 | opus/sonnet |
| `standard` | 3 | 300 | sonnet |
| `bulk` | 1 | 120 | haiku |

---

## 7. Modelo de dados

### 7.1 Schema de evento

```json
{
  "seq": 42,
  "event_id": "evt_01HK7XZY8K9M3P4Q5R6S7T8U9V",
  "ts": "2026-04-20T10:00:42.123Z",
  "agent": "worker-code-writer-1",
  "event_type": "task_completed",
  "task_id": "t_0042",
  "attempt": 1,
  "data": {
    "phase": "dev",
    "artifacts": ["src/auth/jwt.py"],
    "summary": "Implemented JWT signing"
  },
  "prev_hash": "a3f2...",
  "hash": "7b91..."
}
```

### 7.2 Campos obrigatórios

| Campo | Tipo | Descrição |
|---|---|---|
| `seq` | int | Monotônico global |
| `event_id` | string | ULID-like, único |
| `ts` | string | ISO 8601 UTC, precisão ms |
| `agent` | string | `orchestrator`, `worker-{type}-{n}`, `hook-*`, `operator` |
| `event_type` | enum | Tipo do evento (tabela abaixo) |
| `task_id` | string\|null | `t_NNNN` ou null para eventos globais |
| `attempt` | int | Tentativa corrente, começa em 1 |
| `data` | object | Payload; inclui `phase` para eventos de task |
| `prev_hash` | string | Hash do evento anterior ou `GENESIS` |
| `hash` | string | SHA-256 do evento (excluindo `hash` field) |

### 7.3 Vocabulário completo de eventos

**Ciclo de task:**

| Tipo | Emissor | Propósito |
|---|---|---|
| `task_created` | orchestrator | Declara nova task com phase, deps, tier, spec |
| `task_claimed` | orchestrator | Atribui worker a task ready |
| `task_progress` | worker | Heartbeat ou marco intermediário |
| `task_completed` | worker | Conclusão com sucesso; lista artifacts |
| `task_failed` | worker ou hook | Falha com `retryable` flag |
| `task_scheduled_retry` | orchestrator | Retry agendado; aguarda backoff |
| `task_retried` | orchestrator | Backoff expirou; task volta a pending |
| `task_dlq` | orchestrator | Task permafailed |

**Ciclo de fase:**

| Tipo | Emissor | Propósito |
|---|---|---|
| `phase_declared` | orchestrator | Declara todas as fases do workflow |
| `phase_entered` | orchestrator | Fase se torna `active` |
| `phase_exit_criterion_met` | orchestrator | Critério individual atingido |
| `phase_exit_approved` | orchestrator | Todos os critérios atingidos |
| `phase_transitioned` | orchestrator | Fase anterior → completed, próxima → active |
| `phase_paused` | orchestrator | Fase pausada por escalation |
| `phase_resumed` | orchestrator | Fase retoma após pausa |

**Gestão e operação:**

| Tipo | Emissor | Propósito |
|---|---|---|
| `circuit_breaker_tripped` | orchestrator | Falha em massa detectada |
| `escalation` | orchestrator | Pede intervenção humana |
| `human_response` | operator | Resposta humana a escalação |
| `snapshot` | orchestrator | Estado agregado persistido |
| `log_recovered` | operator | Recovery manual de corrupção |
| `preflight_failed` | orchestrator | Check de premissa falhou |

### 7.4 Payloads de eventos principais

**`task_created`**:
```json
{
  "phase": "dev",
  "deps": ["t_0040"],
  "tier": "standard",
  "type": "implementation",
  "spec": "Implement JWT signing with RS256"
}
```

**`task_completed`** (artifacts são paths, não conteúdo):
```json
{
  "phase": "dev",
  "artifacts": ["src/auth/jwt.py", "tests/test_jwt.py"],
  "summary": "Implemented JWT with RS256; 12 tests passing"
}
```

**`task_failed`**:
```json
{
  "phase": "dev",
  "reason": "spec_unclear: dependency X not specified",
  "retryable": false
}
```

**`task_scheduled_retry`**:
```json
{
  "next_retry_at": "2026-04-20T10:05:42.000Z",
  "reason": "worker_transient_error",
  "backoff_seconds": 45.2,
  "previous_failure_seq": 38
}
```

**`phase_declared`**:
```json
{
  "workflow_id": "wf_feature_auth",
  "phases": [
    {"name": "sdd", "order": 1, "required": true},
    {"name": "dev", "order": 2, "required": true},
    {"name": "review", "order": 3, "required": true},
    {"name": "test", "order": 4, "required": true}
  ]
}
```

**`phase_transitioned`**:
```json
{
  "from_phase": "sdd",
  "to_phase": "dev",
  "transitioned_at": "2026-04-20T10:15:00Z",
  "evidence_seq": 42
}
```

**`escalation`**:
```json
{
  "code": "E03_dependency_cycle",
  "evidence": [12, 18, 25],
  "severity": "critical",
  "reason": "t_01 ↔ t_02 cycle detected"
}
```

### 7.5 Externalização de payloads grandes

Append atômico POSIX só garante atomicidade até ~4KB (PIPE_BUF). Evento maior pode corromper log sob concorrência.

**Solução**: payloads > 3500 bytes são externalizados para `.orch/blobs/{event_id}.json`. Evento inline mantém referência com hash:

```json
{
  "event_type": "task_completed",
  "data": {
    "_blob_ref": ".orch/blobs/evt_XYZ.json",
    "_size": 15000,
    "_blob_hash": "sha256:abc123..."
  }
}
```

O `_blob_hash` é parte do `data`, logo é incluído no `hash` do evento. Adulteração do blob quebra verificação ao carregar.

**Convenção primária**: artifacts são **paths**, não conteúdo inline. Isso evita a maioria dos casos que precisariam externalização.

---

## 8. Máquinas de estados

### 8.1 Estados de task

```
          task_created
                │
                ▼
            ┌────────┐
            │pending │
            └───┬────┘
      deps completas +
      fase ativa
                ▼
            ┌────────┐
            │ ready  │
            └───┬────┘
                │ task_claimed
                ▼
            ┌────────┐
   ┌────────│running │────────┐
   │        └────────┘        │
task_completed           task_failed
   │                          │
   ▼                   ┌──────┴──────┐
┌─────────┐     retryable=true   retryable=false
│completed│     attempts<max     OR attempts>=max
│  (end)  │            │                │
└─────────┘            ▼                ▼
                  ┌──────────┐     ┌──────────┐
                  │scheduled │     │   dlq    │
                  │ (backoff │     │  (end)   │
                  │ waiting) │     └──────────┘
                  └────┬─────┘
                       │ backoff expira
                       ▼ task_retried
                   (volta a pending)
```

Estados terminais: `completed`, `dlq`, `cancelled`.

### 8.2 Estados de fase

```
                 phase_declared
                      │
                      ▼
                 ┌─────────┐
                 │ pending │
                 └────┬────┘
                      │ phase_entered
                      ▼
                 ┌─────────┐
          ┌──────│ active  │──────┐
          │      └─────────┘      │
    exit_criteria               phase_paused
    met                           │
          │                       ▼
          ▼                  ┌─────────┐
    ┌──────────────┐         │ paused  │
    │exit_approved │         └────┬────┘
    └──────┬───────┘              │ phase_resumed
           │ phase_transitioned   ▼
           ▼                 (volta a active)
     ┌──────────┐
     │completed │
     │  (end)   │
     └──────────┘
```

**Invariante**: apenas uma fase em `active` ou `exit_approved` por vez.

### 8.3 Transições permitidas (task)

| De | Para | Gatilho | Condição |
|---|---|---|---|
| – | `pending` | `task_created` | – |
| `pending` | `ready` | derivado | deps completas E fase da task ativa |
| `ready` | `running` | `task_claimed` | worker disponível |
| `running` | `completed` | `task_completed` | – |
| `running` | `failed` | `task_failed` ou stale | – |
| `failed` | `scheduled` | `task_scheduled_retry` | retryable=true E attempts<max |
| `failed` | `dlq` | `task_dlq` | retryable=false OR attempts>=max |
| `scheduled` | `pending` | `task_retried` | now >= next_retry_at |
| `completed`, `dlq` | – | – | terminal |

### 8.4 Semântica de `retryable`

| Situação | Ação do orquestrador |
|---|---|
| `task_failed(retryable=true, attempts<max)` | `task_scheduled_retry` → `scheduled` |
| `task_failed(retryable=true, attempts>=max)` | `task_dlq(reason="max_attempts_exceeded")` → `dlq` |
| `task_failed(retryable=false)` | `task_dlq(reason="non_retryable")` → `dlq` **imediato** |

**`retryable=false` consome zero tentativas restantes**. Worker usa para falhas determinísticas (spec inválida, permissão negada).

---

## 9. Componentes

### 9.1 Orchestrator sub-agent

**Responsabilidade**: decidir próxima ação baseado no log.

**Características**:
- Modelo: `opus` (reasoning crítico)
- Tools: `Agent`, `Bash`, `Read`, `Glob`, `Grep`
- Skills carregadas estáticas: `orch-log`, `orch-state`
- Skills carregadas dinamicamente: `phase-{corrente}-rules` conforme fase ativa
- Context: isolado, reconstrói estado a cada invocação

**Entrada**: invocação explícita do usuário ou evento de conclusão de worker.

**Saída**:
- Eventos escritos no log
- Chamadas à Agent tool para spawnar workers
- Relatório estruturado para o usuário

**Restrições**:
- Nunca executa trabalho concreto
- Não mantém estado entre invocações
- Máx 100 turns por invocação

### 9.2 Workers sub-agents

**Responsabilidade**: executar uma task atomicamente, emitir eventos de progresso e conclusão.

**Tipos canônicos**:

| Worker | Modelo | Tools |
|---|---|---|
| `code-writer` | sonnet | Read, Write, Edit, Bash, Glob, Grep |
| `test-runner` | sonnet | Read, Write, Edit, Bash, Glob, Grep |
| `code-reviewer` | haiku | Read, Glob, Grep, Bash |
| `migration-writer` | sonnet | Read, Write, Edit, Bash |

**Invariantes enforçadas**:
- Emitem exatamente **um** evento terminal (`task_completed` ou `task_failed`)
- NÃO podem emitir eventos de orquestrador — script `emit.py` bloqueia
- NÃO se comunicam entre si — toda comunicação via log
- Cada worker carrega skill `orch-report` obrigatoriamente

### 9.3 Biblioteca compartilhada (`orch_core.py`)

**Responsabilidade**: lógica comum usada por todos os scripts.

**Módulos lógicos**:

| Módulo | Conteúdo |
|---|---|
| Schema | `Event`, `TaskState`, `OrchState`, `PhaseState`; enums `EventType`, `TaskStatus`, `PhaseStatus`, `Tier` |
| I/O | `append_event()`, `read_events()`, `last_event()` |
| Integridade | `verify_chain(mode)` com modos strict/recover/audit |
| Blobs | `externalize_blob()`, `load_blob_data()` com verificação de hash |
| Reducer | `apply_event()`, `reduce_all()`, `reduce_incremental()` |
| Snapshots | `save_snapshot()`, `latest_snapshot()` |
| Locking | `LogLock` context manager sobre `fcntl.flock` |
| Retry | `backoff_seconds()`, policy lookup por tier |
| Circuit breaker | `evaluate_circuit_state()`, detecção em janela |

**Propriedades**:
- Zero dependências externas (stdlib pura)
- Funções puras onde aplicável
- Testável isoladamente
- Thread-safe e process-safe via flock

### 9.4 Skills

#### 9.4.1 `orch-log`

Leitura e escrita no event log.

**Scripts**:
- `append.py` — emite evento com lock, hash chain, validação de tamanho
- `read.py` — lê eventos com filtros (seq, task_id, event_type, tail, phase)
- `verify.py` — verifica integridade em três modos (strict/recover/audit)

#### 9.4.2 `orch-state`

Deriva e inspeciona estado agregado.

**Scripts**:
- `reduce.py` — executa reducer, imprime estado JSON
- `snapshot.py` — persiste snapshot, emite evento
- `summary.py` — resumo legível para humano
- `current_phase.py` — retorna fase corrente e status

#### 9.4.3 `orch-report`

Workers emitem eventos de progresso e conclusão.

**Scripts**:
- `emit.py` — wrapper restrito que só permite eventos worker-emittable

**Validação crítica**: rejeita tentativas de emitir eventos de orquestrador. Guard-rail independente do prompt.

#### 9.4.4 `phase-{nome}-rules` (uma por fase)

Regras de negócio específicas da fase.

**Estrutura padrão**:

```
phase-{nome}-rules/
├── SKILL.md                    # quando e como usar
├── exit-criteria.json          # manifesto de critérios
├── references/
│   ├── task-templates.md       # templates de spec
│   ├── worker-routing.md       # task.type → worker
│   └── decision-matrix.md      # árvore de decisão
└── scripts/
    ├── decompose.py            # input → tasks (fase SDD)
    ├── select_worker.py        # task → worker apropriado
    └── check_*.py              # checkers de critérios
```

**Invocável apenas pelo orchestrator** (`user-invocable: false`).

### 9.5 Hooks

#### 9.5.1 `on_subagent_stop.py`

**Trigger**: Claude Code dispara ao fim de cada sub-agent.

**Responsabilidade**: detectar workers que pararam sem emitir terminal e sintetizar `task_failed`.

**Mecanismo**:
1. Lê env vars `ORCH_TASK_ID`, `ORCH_ATTEMPT`, `ORCH_WORKER_ID` (setadas pelo orquestrador ao spawnar)
2. Se ausentes: no-op (não é contexto de worker orquestrado)
3. Se presentes: verifica se último evento da task é terminal
4. Se não: emite `task_failed` com `retryable=true, reason="worker_stopped_without_terminal_event"`

#### 9.5.2 `on_stop.py`

**Trigger**: fim da sessão Claude Code.

**Responsabilidade**: persistir snapshot final e agregar métricas.

**Output**: `.orch/metrics/current.json` com contagens por status, total de eventos, escalações.

### 9.6 Scripts operacionais

| Script | Propósito |
|---|---|
| `preflight.py` | Valida premissas do Claude Code antes de workflow |
| `circuit_breaker.py` | Reset manual do breaker após investigação |
| `dlq_triage.py` | Classifica tasks em DLQ em buckets |
| `gc_orphan_blobs.py` | Limpa blobs órfãos (opcional) |

---

## 10. Retry, backoff e circuit breaker

### 10.1 Backoff exponencial com jitter

```python
def backoff_seconds(attempts: int, base_delay_s: float = 30.0,
                    cap_s: float = 600.0) -> float:
    delay = min(base_delay_s * (2 ** (attempts - 1)), cap_s)
    jitter = random.uniform(0.8, 1.2)
    return delay * jitter
```

Jitter ±20% evita thundering herd em falhas simultâneas. Jitter aplicado **após** decisão determinística (preserva P5).

### 10.2 Retry policy por tier

Configuração em `.orch/config.json`:

```json
{
  "retry_policy": {
    "defaults_by_tier": {
      "critical": {"max_attempts": 5, "base_delay_s": 15, "cap_s": 600},
      "standard": {"max_attempts": 3, "base_delay_s": 30, "cap_s": 600},
      "bulk":     {"max_attempts": 1, "base_delay_s": 0,  "cap_s": 0}
    },
    "overrides_by_task_type": {
      "e2e-test": {"max_attempts": 5, "base_delay_s": 60}
    }
  }
}
```

**Precedência**: override por `task_type` > default por `tier`.

### 10.3 Circuit breaker

Endereça risco de bug em worker que falha instantaneamente em todas as tasks.

**Configuração default:**

```json
{
  "circuit_breaker": {
    "enabled": true,
    "window_minutes": 10,
    "failure_threshold": 50,
    "scope": "workflow",
    "cooldown_minutes": 30,
    "reset_on_success_count": 5
  }
}
```

**Comportamento ao disparar:**

1. Emite `circuit_breaker_tripped` com counts, window, affected_workers
2. Para spawns novos no escopo afetado
3. Tasks em `scheduled` ficam congeladas até reset
4. Tasks em `running` continuam (não canceladas)
5. Usuário notificado para investigar

**Reset manual:**

```bash
python3 .claude/scripts/circuit_breaker.py --reset --confirm
```

---

## 11. Integridade e recovery de log

### 11.1 Hash chain

Cada evento contém `prev_hash` apontando para `hash` do anterior. Chain começa com `GENESIS`. SHA-256 detecta:

- Edição manual de eventos passados
- Reordenação de eventos
- Corrupção acidental (disco, crash)

### 11.2 Três modos de verificação

```python
def verify_chain(mode: Literal["strict", "recover", "audit"]) -> VerifyResult:
    """
    strict:  primeiro erro = aborta. Usado em startup do orquestrador.
    recover: trunca no último hash válido, move resto para .corrupt.{ts}.
             Requer flag --confirm explícita. Nunca automático.
    audit:   reporta todos os erros sem modificar. Para investigação.
    """
```

### 11.3 Regras operacionais

- **R1**: Startup do orquestrador usa `strict`. Falha → `escalation(code="E09_corrupted_log")`.
- **R2**: Recovery nunca automático. Exige `--confirm` manual pelo operador.
- **R3**: Parte removida vai para `.orch/log.jsonl.corrupt.{timestamp}` — nunca descartada.
- **R4**: Recovery emite `log_recovered` com operator, hashes, seq truncado.

### 11.4 Fluxo de recovery manual

```bash
# 1. Investigação
python3 .claude/skills/orch-log/scripts/verify.py --mode audit
# Output: detalhes de corrupção

# 2. Decisão: truncar ou restaurar backup

# Se truncar:
python3 .claude/skills/orch-log/scripts/verify.py \
  --recover --confirm --from-seq 1423 \
  --operator "user@example.com"

# 3. Retomar workflow
# Próxima invocação do orquestrador rodará strict, passará
```

### 11.5 Recovery de desastre

| Cenário | Recuperação |
|---|---|
| Perda total de `.orch/` | Impossível; workflow reinicia do zero. Mitigação: backup periódico |
| Perda parcial (snapshots) | Reducer reconstrói de log completo |
| Corrupção no meio do log | Escala E09, não auto-repara; recovery manual |
| Última linha truncada | Tolerado automaticamente pelo reader |

---

## 12. Validação de payloads

### 12.1 Limite

```python
MAX_INLINE_PAYLOAD = 3500  # bytes, margem abaixo de PIPE_BUF 4KB
```

### 12.2 Mecanismo

```python
def append_event(event: Event) -> None:
    serialized = json.dumps(event.to_dict(), sort_keys=True) + "\n"
    size = len(serialized.encode("utf-8"))

    if size > MAX_INLINE_PAYLOAD:
        blob_path, blob_hash = externalize_blob(event.data, event.event_id)
        event.data = {
            "_blob_ref": blob_path,
            "_size": size,
            "_blob_hash": blob_hash
        }
        serialized = json.dumps(event.to_dict(), sort_keys=True) + "\n"

    with LogLock():
        with open(LOG_PATH, "ab") as f:
            f.write(serialized.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
```

### 12.3 Preservação de integridade do blob

O `_blob_hash` faz o blob parte da hash chain indiretamente. Ao carregar:

```python
def load_blob_data(event: Event) -> dict:
    if "_blob_ref" not in event.data:
        return event.data

    expected_hash = event.data["_blob_hash"]
    payload_bytes = Path(event.data["_blob_ref"]).read_bytes()
    actual_hash = hashlib.sha256(payload_bytes).hexdigest()

    if actual_hash != expected_hash:
        raise BlobIntegrityError(...)

    return json.loads(payload_bytes.decode("utf-8"))
```

### 12.4 Convenção primária para workers

**Artifacts são paths**, não conteúdo. Evita a maioria dos casos de externalização.

Correto:
```json
{"artifacts": ["src/auth/jwt.py"], "summary": "Implemented JWT"}
```

Antipadrão:
```json
{"artifacts": ["src/auth/jwt.py"], "diff": "--- a/src/auth/jwt.py\n+++ ..."}
```

---

## 13. Preflight de premissas

### 13.1 Propósito

A arquitetura depende de comportamentos do Claude Code sem contrato formal de estabilidade (hooks, env var propagation, Agent tool, skills loading). Preflight valida empiricamente antes de workflows importantes.

### 13.2 Checks

**Locais (não invocam Claude Code):**

| Check | Verifica |
|---|---|
| `python_version` | Python 3.10+ |
| `flock_works` | POSIX flock exclusivo funciona |
| `filesystem_writable` | `.orch/` writável |
| `claude_code_installed` | binário `claude` disponível |
| `claude_code_version` | versão >= 2.1.0 |

**Remotos (invocam Claude Code via subprocess):**

| Check | Verifica |
|---|---|
| `agent_tool_available` | Tool `Agent()` presente em sub-agent |
| `skills_loadable` | Skills carregam em sub-agent |
| `hook_on_subagent_stop` | Hook dispara ao fim de sub-agent |
| `hook_on_stop` | Hook dispara ao fim de sessão |
| `env_var_propagation` | ORCH_* chegam ao sub-agent spawnado |
| `turn_limit_honored` | maxTurns é respeitado |

### 13.3 Integrações

- **CI**: roda a cada PR e release do Claude Code. Falha bloqueia merge.
- **Runtime**: orquestrador chama modo `--quick` antes de workflows > 10 tasks. Falha emite `preflight_failed` e pausa.
- **Pós-update**: README instrui rodar manualmente após atualizar Claude Code.

### 13.4 Execução

```bash
# Completo (requer Claude Code instalado)
python3 .claude/scripts/preflight.py

# Rápido (só checks locais)
python3 .claude/scripts/preflight.py --quick
```

Saída JSON estruturada para integração em CI.

---

## 14. Fluxos principais

### 14.1 Início de workflow multi-fase

```
1. Humano: "Use o orchestrator para implementar feature X via workflow completo"

2. Orchestrator Ciclo 1:
   a. verify.py --mode strict → ok
   b. current_phase.py → null (log vazio)
   c. Lê config.json, escolhe workflow (default: dev-cycle)
   d. Emite phase_declared(workflow_id, phases=[sdd, dev, review, test])
   e. Emite phase_entered(sdd)
   f. Carrega phase-sdd-rules
   g. Roda decompose.py com descrição "feature X"
   h. Emite 3 task_created(phase=sdd, type=spec_analysis)
   i. Reporta ao usuário: "SDD iniciada com 3 tasks"

3. Orchestrator Ciclos 2-N:
   a. verify + current_phase → sdd active
   b. Carrega phase-sdd-rules
   c. Promove tasks ready, spawna workers SDD
   d. Aguarda

4. [Workers SDD completam]

5. Orchestrator Ciclo N+1:
   a. Roda checkers de exit-criteria SDD
   b. Todos met → emite phase_exit_criterion_met × 3
   c. Emite phase_exit_approved(sdd, next_phase=dev)

6. Orchestrator Ciclo N+2:
   a. Detecta phase_exit_approved sem transitioned subsequente
   b. Emite phase_transitioned(sdd → dev)
   c. Emite phase_entered(dev)
   d. Tasks com phase=dev (criadas em SDD) ficam elegíveis

7. ... continua até test completar
```

### 14.2 Execução de task

```
1. Orchestrator seleciona task ready, worker disponível
2. Orchestrator: append_event(task_claimed, task_id, worker_id)
3. Orchestrator: Agent(subagent_type=worker_type, prompt=..., env={ORCH_*})
4. Worker carrega orch-report skill
5. Worker: emit.py --kind progress --note "started"
6. Worker executa trabalho (multi-turn)
7. Worker checkpoint: emit.py --kind progress (marcos importantes)
8. Worker finaliza:
   - Sucesso: emit.py --kind completed --artifacts [...]
   - Falha recuperável: emit.py --kind failed --retryable true
   - Falha determinística: emit.py --kind failed --retryable false
9. Agent tool retorna; hook on_subagent_stop valida terminal emitido
10. Se worker parou sem emitir: hook sintetiza task_failed
```

### 14.3 Retry completo

```
1. Worker emite task_failed(retryable, reason)
2. Orchestrator em próximo ciclo:
   a. verify.py → ok
   b. Para task em failed:
      i. Consulta policy: max_attempts(tier, task_type)
      ii. Se retryable=false:
          → task_dlq(reason="non_retryable") imediato
      iii. Se retryable=true E attempts >= max:
          → task_dlq(reason="max_attempts_exceeded")
      iv. Se retryable=true E attempts < max:
          → backoff = backoff_seconds(attempts, base, cap)
          → task_scheduled_retry(next_retry_at, backoff)
          → status = scheduled
   c. Circuit breaker check:
      i. Se failures em window >= threshold:
          → circuit_breaker_tripped
          → cancela spawns novos
3. Para tasks em scheduled:
   a. Se circuit fechado E now >= next_retry_at:
      → task_retried(attempt+1)
      → status = pending
```

### 14.4 Detecção de stale

```
1. Worker foi claimed mas nunca emitiu (crash, timeout)
2. Orchestrator em ciclo posterior:
   a. Reducer detecta task running, last_event_at antigo
   b. tier_timeout = stale_seconds(task.tier)
   c. Se (now - last_event_at) > tier_timeout:
      → task_failed(synthesized_by="stale_detection", retryable=true)
3. Fluxo normal de retry continua
```

### 14.5 Escalação

```
1. Orchestrator detecta anomalia (ex: dois task_completed para mesma task)
2. Orchestrator: escalation(code="E05", evidence=[seq1, seq2])
3. Se anomalia afeta fase: phase_paused
4. Orchestrator PARA decisões sobre elementos afetados
5. Reporta ao usuário com code, evidence, ação sugerida
6. Humano investiga, toma ação:
   - Opção A: reset (rm -rf .orch/)
   - Opção B: emit human_response com decisão
   - Opção C: cancelar tasks/workflow
7. Se human_response resolve: orchestrator emite phase_resumed e retoma
```

### 14.6 Crash e recuperação

```
1. Sessão Claude Code encerra no meio do workflow
2. Estado persistido: log.jsonl + snapshots + blobs
3. Possível: última linha truncada se crash durante escrita
4. Usuário reabre sessão, invoca orchestrator
5. Orchestrator: verify.py --mode strict
   - Chain íntegro: prossegue
   - Última linha truncada: reader ignora, consistente
   - Meio corrupto: escala E09, exige recovery manual
6. Orchestrator: current_phase.py reconstrói de snapshot + eventos
7. Tasks em running serão detectadas stale no próximo ciclo
8. Retoma workflow do ponto
```

---

## 15. Concorrência e consistência

### 15.1 Modelo

**Consistência forte para o log**: toda escrita serializada via flock. Leitores veem estado monotônico.

**Consistência eventual para estado derivado**: snapshots podem estar defasados, mas `reduce_incremental()` sempre recupera estado correto.

### 15.2 Pontos de concorrência

- Workers emitindo eventos simultaneamente
- Orchestrator emitindo durante execução de workers
- Hooks disparando assíncronos

**Mecanismo**: todas as escritas via `append_event()` que adquire lock antes de:
1. Computar `seq` (lê último evento)
2. Computar `prev_hash`
3. Escrever linha completa
4. fsync para disco
5. Liberar lock

### 15.3 Atomicidade

- **Append de linha**: garantido por `O_APPEND` + escrita < PIPE_BUF (ou externalização)
- **fsync**: durabilidade em caso de crash imediato
- **Sem transações multi-linha**: cada evento é atômico; reducer lida com estados intermediários

### 15.4 Timeout de lock

10s via loop não-bloqueante. Se não liberado: `TimeoutError`, chamador pode retry.

Casos que causariam timeout: processo morto (kernel libera lock), contention extrema (> 1000 ops/s).

### 15.5 Isolamento

Workers isolados:
- Context windows separados
- Filesystem compartilhado, mas convenção: workers só modificam arquivos em sua spec
- Log é única memória compartilhada

Conflitos em arquivos (dois workers modificando mesmo arquivo) são problema de design de workflow, não da arquitetura.

---

## 16. Observabilidade

### 16.1 Fontes de dados

| Fonte | Formato | Retenção | Uso |
|---|---|---|---|
| `.orch/log.jsonl` | JSONL | Indefinida (até rotação) | Fonte primária |
| `.orch/blobs/*.json` | JSON | Mesma do log | Payloads grandes |
| `.orch/state/snapshot-*.json` | JSON | 10 últimos | Estado agregado |
| `.orch/dlq/*.json` | JSON | 30 dias | Triagem |
| `.orch/metrics/current.json` | JSON | Última run | Dashboards |
| `.orch/audit/YYYY-MM-DD.jsonl` | JSONL | Diário | Compliance (opcional) |

### 16.2 Comandos de inspeção

| Comando | Informação |
|---|---|
| `python3 .claude/skills/orch-state/scripts/summary.py` | Resumo legível |
| `python3 .claude/skills/orch-state/scripts/current_phase.py` | Fase corrente |
| `python3 .claude/skills/orch-log/scripts/read.py --tail 20` | Últimos eventos |
| `python3 .claude/skills/orch-log/scripts/verify.py` | Integridade |
| `python3 .claude/hooks/dlq_triage.py` | Triagem DLQ |
| `cat .orch/metrics/current.json` | Métricas agregadas |

### 16.3 Métricas após run

Geradas por `on_stop.py`:

- `total_events`
- `events_by_type`
- `tasks_total`, `tasks_completed`, `tasks_failed`, `tasks_dlq`
- `phases_completed`, `phase_durations`
- `escalations`
- `run_status`
- `last_seq`

### 16.4 Queries úteis

```bash
# Duração de cada fase
jq 'select(.event_type | startswith("phase_"))' .orch/log.jsonl

# Tasks de uma fase específica
jq 'select(.data.phase == "dev")' .orch/log.jsonl

# Histograma de tipos de evento
jq -r '.event_type' .orch/log.jsonl | sort | uniq -c

# Escalações
jq 'select(.event_type == "escalation")' .orch/log.jsonl
```

---

## 17. Modelo de falhas

### 17.1 Taxonomia

| Classe | Exemplo | Tratamento |
|---|---|---|
| Transiente | Rate limit, network blip | Retry com backoff |
| Worker crash | Turn limit, OOM | Hook sintetiza task_failed |
| Spec inválida | Ambígua, dep faltando | Worker emite retryable=false → DLQ |
| Estado inconsistente | Transição ilegal | Escalação E02 |
| Corrupção de log | Hash mismatch | Escalação E09, recovery manual |
| Deadlock | Sem ação possível | Escalação E06 |
| Budget excedido | Custo alto (futuro) | Escalação E08 |
| Falha em massa | Bug sistêmico | Circuit breaker dispara |

### 17.2 Condições de escalação

| Code | Condição |
|---|---|
| E01 | Evento com `event_type` desconhecido |
| E02 | Transição de estado ilegal |
| E03 | Ciclo de dependências |
| E04 | Task `critical` atingiu max_attempts |
| E05 | Dois `task_completed` para mesma (task_id, attempt) |
| E06 | Deadlock |
| E07 | Violação de invariante |
| E08 | Budget excedido (futuro) |
| E09 | Log corrompido |
| E10 | Config inválida |
| E11 | Worker não mapeado para task.type |
| E12 | Fase desconhecida no workflow |

### 17.3 Dead Letter Queue

Tasks em DLQ:
- Evento `task_dlq` no log
- Arquivo em `.orch/dlq/t_NNNN.json` com último erro
- Triagem via `dlq_triage.py` classifica em buckets:
  - `input_issue`, `worker_issue`, `permission_issue`, `code_issue`, `quota_issue`, `transient_issue`, `unknown`
- Humano decide: fix + retry manual, ignorar, cancelar dependentes

---

## 18. Segurança

### 18.1 Modelo de confiança

**Confia-se em**:
- Claude Code e sub-agents (ambiente controlado)
- Scripts Python em `.claude/` (código próprio versionado)
- Sistema operacional e filesystem local

**Não se confia em**:
- Inputs externos (validação de schema)
- Processos não-autorizados (permissões de arquivo)

### 18.2 Integridade

Hash chain SHA-256 detecta:
- Edição manual de eventos passados
- Reordenação
- Corrupção acidental

Blobs externalizados protegidos por `_blob_hash`.

**Não detecta**: reset completo intencional (comportamento esperado), ataque sofisticado reescrevendo toda a chain (computacionalmente viável mas quebra auditoria).

### 18.3 Least privilege

Cada worker declara `tools:` mínimas. Exemplos:

| Worker | Tools | Justificativa |
|---|---|---|
| `code-writer` | Read, Write, Edit, Bash, Glob, Grep | Cria/modifica código |
| `code-reviewer` | Read, Glob, Grep, Bash | Read-only; Bash só para skill |

Orchestrator tem tools mais amplas (Agent adicional) mas é único ponto que spawna.

### 18.4 Guard-rails

- `emit.py` rejeita eventos de orquestrador mesmo que prompt do worker tente
- Hook `on_subagent_stop` captura workers que terminam sem evento mesmo com prompt comprometido
- Verify chain em cada ciclo detecta corrupção cedo

### 18.5 Dados sensíveis

**Log é plaintext**. Não armazene secrets, PII, ou dados sensíveis em `data` de eventos.

**Regra**: `data` contém apenas metadados de coordenação. Conteúdo real de artefatos (código, dados) fica em arquivos do projeto, referenciados por path.

---

## 19. Configuração

Arquivo: `.orch/config.json`

```json
{
  "version": "1.0",
  "retry_policy": {
    "defaults_by_tier": {
      "critical": {"max_attempts": 5, "base_delay_s": 15, "cap_s": 600},
      "standard": {"max_attempts": 3, "base_delay_s": 30, "cap_s": 600},
      "bulk":     {"max_attempts": 1, "base_delay_s": 0,  "cap_s": 0}
    },
    "overrides_by_task_type": {}
  },
  "circuit_breaker": {
    "enabled": true,
    "window_minutes": 10,
    "failure_threshold": 50,
    "scope": "workflow",
    "cooldown_minutes": 30,
    "reset_on_success_count": 5
  },
  "payload_limits": {
    "max_inline_bytes": 3500,
    "blob_storage_path": ".orch/blobs"
  },
  "verify": {
    "startup_mode": "strict",
    "auto_recover": false
  },
  "preflight": {
    "runtime_threshold_tasks": 10,
    "timeout_seconds": 60
  },
  "phases": {
    "default_workflow": "dev-cycle",
    "workflows": {
      "dev-cycle": {
        "description": "Feature development",
        "phases": ["sdd", "dev", "review", "test"]
      },
      "bug-fix": {
        "description": "Bug fix",
        "phases": ["reproduce", "fix", "verify", "regression"]
      },
      "refactor": {
        "description": "Refactor",
        "phases": ["analyze", "migrate", "verify"]
      },
      "spike": {
        "description": "Research spike",
        "phases": ["research", "document"]
      }
    }
  }
}
```

**Defaults**: se arquivo ausente, defaults hardcoded são usados.

**Validação**: orquestrador valida schema no startup. Inválido → `escalation(E10_invalid_config)`.

---

## 20. Estrutura de arquivos

```
projeto/
├── CLAUDE.md
├── .gitignore                              # ignora .orch/
├── .claude/
│   ├── settings.json                       # configura hooks
│   ├── agents/
│   │   ├── orchestrator.md                 # sub-agent principal
│   │   ├── code-writer.md                  # worker: implementação
│   │   ├── test-runner.md                  # worker: testes
│   │   ├── code-reviewer.md                # worker: review (read-only)
│   │   ├── migration-writer.md             # worker: DB migrations
│   │   └── ... (outros workers)
│   ├── skills/
│   │   ├── orch-log/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/
│   │   │       ├── append.py
│   │   │       ├── read.py
│   │   │       └── verify.py
│   │   ├── orch-state/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/
│   │   │       ├── reduce.py
│   │   │       ├── snapshot.py
│   │   │       ├── summary.py
│   │   │       └── current_phase.py
│   │   ├── orch-report/
│   │   │   ├── SKILL.md
│   │   │   └── scripts/
│   │   │       └── emit.py
│   │   ├── phase-sdd-rules/
│   │   │   ├── SKILL.md
│   │   │   ├── exit-criteria.json
│   │   │   ├── references/
│   │   │   └── scripts/
│   │   ├── phase-dev-rules/
│   │   │   └── ... (mesma estrutura)
│   │   ├── phase-review-rules/
│   │   └── phase-test-rules/
│   ├── hooks/
│   │   ├── on_subagent_stop.py
│   │   ├── on_stop.py
│   │   └── dlq_triage.py
│   ├── scripts/
│   │   ├── preflight.py
│   │   ├── circuit_breaker.py
│   │   └── gc_orphan_blobs.py
│   └── lib/
│       ├── __init__.py
│       └── orch_core.py                    # biblioteca compartilhada
└── .orch/                                  # .gitignore isto
    ├── log.jsonl                           # event log (fonte da verdade)
    ├── log.jsonl.lock                      # lockfile POSIX
    ├── log.jsonl.corrupt.{ts}              # arquivado em recovery (opcional)
    ├── config.json                         # configuração do orquestrador
    ├── state/
    │   └── snapshot-NNNN.json              # snapshots periódicos
    ├── blobs/
    │   └── {event_id}.json                 # payloads externalizados
    ├── dlq/
    │   └── t_NNNN.json                     # tasks permafailed
    ├── audit/
    │   └── YYYY-MM-DD.jsonl                # audit trail diário
    └── metrics/
        └── current.json                    # métricas agregadas
```

---

## 21. Trade-offs e limitações

### 21.1 Trade-offs fundamentais

**Simplicidade vs escala**: escolha foi single-machine com stdlib pura. Preço: não escala horizontalmente. Benefício: zero deps, setup trivial.

**Explicitness vs convenience**: usuário invoca orchestrator manualmente. Preço: mais fricção. Benefício: previsibilidade.

**Event sourcing vs snapshot-only**: primário em eventos, snapshots como otimização. Preço: log cresce indefinidamente. Benefício: auditabilidade completa.

**Sub-agent orchestrator vs código externo**: escolhido sub-agent. Preço: cada ciclo é nova invocação, sem loop contínuo. Benefício: integração nativa, portabilidade.

**Uma fase ativa por vez**: escolhido para simplicidade. Preço: sem paralelismo entre fases. Benefício: máquina de estados tratável.

### 21.2 Limitações de escala

- **Throughput**: ~1000 eventos/s (limitado por flock)
- **Log prático**: ~100MB ou ~10k eventos sem degradação; além requer rotação
- **Workers concorrentes**: ~3-5 (limite do Claude Code)
- **Tasks por workflow**: testado até ~30; teoricamente ilimitado
- **Fases por workflow**: sem limite técnico, ~4-6 é sweet spot prático

### 21.3 Limitações funcionais

- Sem session resume automático (reinvocar manualmente)
- Sem comunicação peer-to-peer entre workers
- Sem distribuição multi-máquina
- Sem integração OTEL nativa
- Sem UI dedicada (inspeção via CLI)
- Fases paralelas não suportadas
- Troca de workflow no meio não suportada

### 21.4 Limitações de plataforma

- **Windows nativo**: não suportado (`fcntl` ausente)
- **WSL2**: suportado plenamente
- **macOS**: suportado
- **Linux**: suportado (plataforma de referência)

### 21.5 Maturidade

| Configuração | Maturidade |
|---|---|
| Sem testes automatizados | 5-6/10 |
| Com suite de testes pytest | 7-8/10 |
| Com uso real prolongado (3+ meses) | 8-9/10 |

Padrões usados (event sourcing, máquina de estados, hash chain, retry com backoff) são maduros. A combinação específica exige validação empírica em cada projeto.

---

## 22. Glossário

| Termo | Definição |
|---|---|
| **Agent** | Arquivo `.md` em `.claude/agents/` que define um sub-agent invocável no Claude Code |
| **Append-only** | Arquivo onde só se adicionam dados; nunca edita ou remove |
| **Circuit breaker** | Mecanismo que interrompe operações após N falhas em janela de tempo |
| **DLQ** | Dead Letter Queue — tasks permafailed aguardando triagem |
| **Escalation** | Pausa do orquestrador pedindo intervenção humana |
| **Event** | Registro imutável do que aconteceu; linha do log |
| **Fase** | Estágio bem-definido de um workflow com regras e critérios próprios |
| **flock** | System call POSIX para locking de arquivos entre processos |
| **Hash chain** | Sequência onde cada elemento contém hash do anterior; detecta adulteração |
| **Hook** | Script disparado automaticamente pelo Claude Code em eventos de lifecycle |
| **Jitter** | Variação aleatória aplicada a delays para evitar thundering herd |
| **Orchestrator** | Sub-agent que coordena workers lendo/escrevendo no log |
| **PIPE_BUF** | Limite POSIX de atomicidade em append (~4KB em Linux) |
| **Preflight** | Verificação de premissas do ambiente antes de execução |
| **Reducer** | Função pura que aplica sequência de eventos a estado inicial |
| **Retryable** | Flag que indica se falha permite retry (true) ou é determinística (false) |
| **Scheduled** | Estado de task aguardando expiração de backoff antes de retry |
| **Skill** | Pacote de conhecimento + scripts em `.claude/skills/<nome>/` |
| **Snapshot** | Estado agregado persistido periodicamente para performance |
| **Stale** | Task em `running` sem eventos por mais que timeout do tier |
| **Sub-agent** | Instância Claude isolada com context window próprio |
| **Task** | Unidade de trabalho coordenada pelo orquestrador |
| **Tier** | Classificação (critical/standard/bulk) que governa retry, timeout, modelo |
| **ULID** | Universally Unique Lexicographically Sortable Identifier |
| **Worker** | Sub-agent especializado que executa tasks concretas |
| **Workflow** | Sequência de fases que compõem uma execução completa |
