# new_flow — Arquitetura e Funcionamento

> Referência de funcionamento do motor de orquestração.
> Descreve cada artefato, seu comportamento, artefatos gerados e uso de variáveis de ambiente.

---

## 1. Visão geral

O new_flow é um **motor de orquestração event-sourced** para workflows multi-fase no Claude Code.

O estado do sistema **nunca é armazenado diretamente** — ele é sempre **derivado do log de eventos**. O log é append-only, imutável, e protegido por uma cadeia de hashes SHA-256. Qualquer corrupção é detectável.

```
Usuário
  │
  ▼
Orchestrator (sub-agent, Opus)
  │  lê: orch-log, orch-state
  │  decide a próxima ação
  │
  ├─── Bash() ──► scripts Python (append.py, read.py, etc.)
  │                      │
  │                      ▼
  │               .orch/log.jsonl  ◄─────────────────┐
  │                                                   │
  └─── Agent() ──► Worker (sub-agent, Sonnet/Haiku)   │
                     │  usa: orch-report/emit.py       │
                     └───────────────────────────────►┘
```

**Invariantes fundamentais:**

| # | Invariante |
|---|------------|
| P1 | O log é a única fonte de verdade. Todo estado é derivado. |
| P2 | O orquestrador é uma função pura do log — sem estado próprio entre invocações. |
| P3 | Append-only. Correções se fazem com novos eventos, nunca editando o log. |
| P4 | Idempotência por chave `(task_id, attempt, event_type)`. |
| P7 | Robustez via hooks — garantias críticas fora do LLM. |
| P12 | A fase corrente é derivada do log, nunca armazenada fora dele. |

---

## 2. Estrutura de diretórios (runtime)

Ao executar, o sistema cria e usa `.orch/` relativo ao **CWD do processo**:

```
.orch/
├── log.jsonl          ← log principal (append-only, JSONL)
├── log.jsonl.lock     ← lock file POSIX (fcntl.flock)
├── blobs/             ← payloads grandes externalizados (> 3500 bytes)
│   └── evt_XYZ.json
├── state/             ← snapshots do OrchState (Task 1.8 — deferida)
├── dlq/               ← eventos dead-letter (uso futuro)
├── audit/             ← logs de auditoria diários (uso futuro)
├── metrics/           ← métricas da run (uso futuro)
└── config.json        ← configuração do workflow (uso futuro)
```

**Todos os caminhos são relativos ao CWD.** Scripts e hooks devem ser executados com CWD apontando para a raiz do projeto.

---

## 3. Artefatos em `.claude/`

```
.claude/
├── lib/
│   └── orch_core.py          ← biblioteca-base (importada por todos os scripts)
├── skills/
│   ├── orch-log/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── append.py     ← escreve evento no log
│   │       ├── read.py       ← lê eventos com filtros
│   │       └── verify.py     ← verifica integridade da cadeia de hashes
│   ├── orch-state/
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── reduce.py         ← estado completo como JSON
│   │       ├── summary.py        ← resumo legível para humano
│   │       └── current_phase.py  ← fase corrente como JSON
│   └── orch-report/
│       ├── SKILL.md
│       └── scripts/
│           └── emit.py       ← interface worker→log (guard-railed)
└── hooks/
    └── on_subagent_stop.py   ← sintetiza task_failed em worker silencioso
```

---

## 4. `lib/orch_core.py` — Biblioteca base

**Importada por todos os scripts.** Stdlib Python 3.10+ puro, zero dependências externas.

### 4.1 Enums

| Enum | Valores | Uso |
|------|---------|-----|
| `EventType` | 21 tipos (ver §6) | Tipo de cada evento no log |
| `TaskStatus` | pending, ready, running, scheduled, completed, failed, dlq | Status derivado pelo reducer |
| `PhaseStatus` | pending, active, exit_approved, completed, paused | Status de fase derivado |
| `Tier` | critical, standard, bulk | Tier de prioridade de cada task |

**`Tier` determina:**
- `default_max_attempts`: critical=5, standard=3, bulk=1
- `default_stale_seconds`: critical=600s, standard=300s, bulk=120s
- `default_base_delay_s`: critical=15s, standard=30s, bulk=0s

### 4.2 Constantes e caminhos

```python
ORCH_DIR         = Path(".orch")              # relativo ao CWD
LOG_PATH         = ORCH_DIR / "log.jsonl"
LOCK_PATH        = ORCH_DIR / "log.jsonl.lock"
BLOBS_DIR        = ORCH_DIR / "blobs"
MAX_INLINE_PAYLOAD = 3500   # bytes — acima disso o payload vai para blobs/
LOCK_TIMEOUT_S   = 10.0     # segundos para tentar adquirir o lock
```

### 4.3 `LogLock` — exclusão mútua

Context manager que usa `fcntl.flock` (POSIX) para garantir que apenas um processo grava no log por vez.

```python
with LogLock():
    # seguro para gravar
```

- Polling não-bloqueante com timeout de `LOCK_TIMEOUT_S`
- Levanta `LockTimeoutError` se não conseguir o lock
- Libera automaticamente ao sair do bloco (inclusive em exceção)

### 4.4 `append_event()` — escrita no log

```python
event = append_event(
    agent="orchestrator",
    event_type="task_created",
    task_id="t_001",        # opcional
    attempt=1,              # default 1
    data={"phase": "dev", "tier": "standard", "type": "impl", "spec": "...", "deps": []},
)
```

**Sequência interna:**
1. Valida `event_type` contra o enum de 21 tipos
2. Valida campos obrigatórios do payload (`_REQUIRED_DATA_FIELDS`)
3. Adquire `LogLock`
4. Lê o último evento para obter `seq` e `prev_hash`
5. Se payload > 3500 bytes → externaliza para `blobs/evt_XYZ.json`, armazena referência
6. Computa hash SHA-256 do evento (excluindo o próprio campo `hash`)
7. Serializa como JSON compacto e faz `write + fsync` no log
8. Retorna o `Event` criado

**Artefato gerado:** uma linha JSON no `log.jsonl` com estrutura:
```json
{
  "seq": 5,
  "event_id": "evt_ABC123...",
  "ts": "2026-04-21T10:00:00.000Z",
  "agent": "orchestrator",
  "event_type": "task_created",
  "task_id": "t_001",
  "attempt": 1,
  "data": { ... },
  "prev_hash": "abc123...",
  "hash": "def456..."
}
```

### 4.5 `read_events()` / `read_events_filtered()` — leitura

```python
# todos os eventos
for event in read_events(from_seq=0):
    ...

# com filtros (AND lógico)
events = read_events_filtered(
    from_seq=0,
    task_id="t_001",
    event_type="task_created",
    phase="dev",
    tail=10,        # últimos N
)
```

- Tolera última linha truncada (não levanta erro)
- Levanta `CorruptedLogError` em JSON inválido no meio do log
- Filtro `phase` resolve blobs automaticamente antes de checar

### 4.6 `verify_chain()` — integridade

```python
result = verify_chain(mode="strict")  # ou "audit"
# result.ok, result.events_verified, result.first_error_seq, result.error_details
```

| Modo | Comportamento |
|------|--------------|
| `strict` | Para no primeiro erro. Usado no startup do orquestrador. |
| `audit` | Coleta todos os erros sem modificar o log. Para investigação. |

### 4.7 Blobs — externalização de payloads grandes

Quando `len(canonical_json(data)) > 3500`:

- Payload salvo em `.orch/blobs/evt_{event_id}.json`
- No log, `data` vira: `{"_blob_ref": "blobs/evt_XYZ.json", "_size": N, "_blob_hash": "sha256..."}`
- `load_blob_data(event)` resolve a referência e verifica o hash
- `is_blob_ref(data)` detecta se um evento usa referência de blob

**Portabilidade:** `_blob_ref` é relativo a `ORCH_DIR`, não ao CWD absoluto.

### 4.8 Reducer — derivação de estado

```python
state = reduce_all()   # reconstrói OrchState completo do início do log
```

`reduce_all()` itera todos os eventos e aplica `apply_event(state, event)` para cada um.

**`OrchState`** (estado agregado):

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `workflow_id` | str\|None | ID do workflow (de `phase_declared`) |
| `run_status` | str | `active`, `escalated` |
| `current_phase` | str\|None | Fase ativa no momento |
| `tasks` | dict[str, TaskState] | Todas as tasks pelo ID |
| `phases` | dict[str, PhaseState] | Todas as fases declaradas |
| `escalation` | dict\|None | Payload de escalation se presente |
| `circuit_breaker` | dict\|None | Estado do circuit breaker |
| `last_seq` | int | Último seq processado |

**`TaskState`** — campos principais:

| Campo | Descrição |
|-------|-----------|
| `task_id` | ID da task |
| `phase` | Fase à qual pertence |
| `status` | pending → ready → running → completed/failed/dlq |
| `tier` | critical/standard/bulk |
| `attempts` | Tentativas já realizadas |
| `max_attempts` | Limite (derivado do tier) |
| `worker_id` | Worker que está executando (se running) |
| `artifacts` | Lista de artefatos produzidos (se completed) |

**Transição de status de task:**

```
task_created  →  pending
               ↓ (fase ativa + deps completas)
             ready
               ↓ task_claimed
             running
               ↓ task_completed     ↓ task_failed(retryable=false)
           completed                      dlq
                       ↓ task_failed(retryable=true)
                      failed
                       ↓ task_scheduled_retry
                    scheduled
                       ↓ task_retried
                      running (attempt+1)
```

---

## 5. Skills CLI

Todos os scripts CLI:
- São executados via `Bash()` pelo orquestrador
- Importam `orch_core` pelo caminho relativo ao arquivo (`parents[3]/lib`)
- Operam com CWD = raiz do projeto (onde `.orch/` está)
- Saída: JSON em stdout (exceto `summary.py`)
- Erros: JSON com `{"status":"error","reason":"...","detail":"..."}` + exit 1

### 5.1 `orch-log/scripts/append.py`

**Quem usa:** orquestrador (para eventos de fase, task, gerenciamento).

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent <id> \
  --event-type <tipo> \
  [--task-id <id>] \
  [--attempt <n>] \
  [--data '<json>']
```

**Saída (exit 0):** JSON do evento criado.

**Validações:** tipo no enum de 21, campos obrigatórios do payload, JSON válido.

### 5.2 `orch-log/scripts/read.py`

**Quem usa:** orquestrador (para inspecionar o log antes de decidir).

```bash
python3 .claude/skills/orch-log/scripts/read.py \
  [--from-seq N] [--tail N] \
  [--task-id <id>] [--event-type <tipo>] [--phase <fase>]
```

**Saída (exit 0):** uma linha JSON por evento (sem envelope — stream puro).
Filtros aplicados em AND. Log vazio → saída vazia (exit 0).

### 5.3 `orch-log/scripts/verify.py`

**Quem usa:** orquestrador no startup (modo strict).

```bash
python3 .claude/skills/orch-log/scripts/verify.py --mode strict|audit
```

**Saída (exit 0/1):**
```json
{"ok": true, "message": "...", "mode": "strict", "events_verified": 42}
```

| Modo | exit em erro |
|------|-------------|
| strict | 1 (para no primeiro erro) |
| audit | sempre 0 (coleta tudo, nunca modifica) |

### 5.4 `orch-state/scripts/reduce.py`

**Quem usa:** orquestrador (para obter estado completo antes de decidir).

```bash
python3 .claude/skills/orch-state/scripts/reduce.py
```

**Saída:** JSON completo do `OrchState`. Log vazio → state vazio com todos os campos em null/0.

### 5.5 `orch-state/scripts/summary.py`

**Quem usa:** operador humano, debugging.

```bash
python3 .claude/skills/orch-state/scripts/summary.py
```

**Saída:** texto formatado (não JSON). Inclui contagens por status, breakdown por fase, lista de fases com marcador da fase ativa.

### 5.6 `orch-state/scripts/current_phase.py`

**Quem usa:** orquestrador (verificação rápida de fase sem reduzir o estado completo).

```bash
python3 .claude/skills/orch-state/scripts/current_phase.py
```

**Saída:**
```json
{"current_phase": "dev", "status": "active", "order": 1}
// ou, se nenhuma fase foi entrada:
{"current_phase": null, "status": null}
```

### 5.7 `orch-report/scripts/emit.py` — Guard-rail do worker

**Quem usa:** workers (única interface permitida para escrever no log).

```bash
ORCH_WORKER_ID=<id> python3 .claude/skills/orch-report/scripts/emit.py \
  --kind progress|completed|failed \
  --task-id <id> \
  [--attempt <n>] \
  [--data '<json>']
```

**Guard-rail (não contornável):**

| `--kind` | Event type emitido |
|----------|--------------------|
| `progress` | `task_progress` |
| `completed` | `task_completed` |
| `failed` | `task_failed` |

Qualquer outro valor em `--kind` é rejeitado pelo `argparse` antes de qualquer I/O — não há como passar um tipo de orquestrador via este script.

**`ORCH_WORKER_ID` (env var obrigatória):** define o campo `agent` do evento. O worker não pode declarar sua própria identidade — ela é injetada pelo orquestrador que o spawnou.

---

## 6. Variáveis de ambiente

| Variável | Quem seta | Quem lê | Descrição |
|----------|-----------|---------|-----------|
| `ORCH_WORKER_ID` | Orquestrador (antes de spawnar o worker) | `emit.py`, `on_subagent_stop.py` | Identidade do worker. Obrigatória para `emit.py`. |
| `ORCH_TASK_ID` | Orquestrador (antes de spawnar o worker) | `on_subagent_stop.py` | ID da task que o worker está executando. |
| `ORCH_ATTEMPT` | Orquestrador (antes de spawnar o worker) | `on_subagent_stop.py` | Número da tentativa corrente (inteiro). |

**Padrão de uso pelo orquestrador ao spawnar um worker:**

```bash
export ORCH_WORKER_ID="worker-$(uuidgen)"
export ORCH_TASK_ID="t_001"
export ORCH_ATTEMPT="1"
# então usa Agent() para invocar o worker
```

O hook `on_subagent_stop.py` lê essas vars ao ser disparado pelo Claude Code após o worker parar.

---

## 7. Hook `on_subagent_stop.py`

**Disparado por:** Claude Code (`SubagentStop` hook, configurado em `settings.json`).

**Propósito:** garantir que todo worker orquestrado produza exatamente um evento terminal, mesmo que o worker tenha crashado, atingido timeout, ou excedido o context window.

**Lógica:**

```
1. Lê stdin (payload JSON do Claude Code — ignorado)
2. Lê ORCH_TASK_ID, ORCH_ATTEMPT, ORCH_WORKER_ID
3. Se qualquer uma ausente → exit 0 (não é contexto orquestrado)
4. Se já existe task_completed ou task_failed para (task_id, attempt) → exit 0
5. Caso contrário:
   - Busca a fase da task via task_created no log
   - Emite task_failed(retryable=true, reason="worker_stopped_without_terminal_event")
   - exit 0 (hook nunca deve falhar)
```

**Artefato gerado:** `task_failed` no log com campo `synthesized_by` identificando o worker.

---

## 8. `settings.json` — configuração de hooks

```json
{
  "hooks": {
    "SubagentStop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python3 .claude/hooks/on_subagent_stop.py"}]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "python3 .claude/hooks/on_stop.py"}]
    }]
  }
}
```

`on_stop.py` (a implementar na Fase 3): persiste métricas finais ao encerrar a sessão.

---

## 9. Tipos de eventos — 21 tipos

### Task lifecycle (8)

| Tipo | Campos obrigatórios | Quem emite | Descrição |
|------|---------------------|------------|-----------|
| `task_created` | phase, tier, type, spec, deps | Orquestrador | Declara uma nova task |
| `task_claimed` | phase, worker_type, worker_id | Orquestrador | Atribui a task a um worker |
| `task_progress` | phase, note | Worker (via emit.py) | Progresso intermediário |
| `task_completed` | phase, artifacts, summary | Worker (via emit.py) | Conclusão bem-sucedida |
| `task_failed` | phase, reason, retryable | Worker (via emit.py) ou hook | Falha (retryable ou não) |
| `task_scheduled_retry` | phase, next_retry_at, backoff_seconds, previous_failure_seq | Orquestrador | Agenda nova tentativa |
| `task_retried` | phase, previous_attempt, scheduled_retry_seq | Orquestrador | Inicia nova tentativa |
| `task_dlq` | phase, reason, last_error | Orquestrador | Esgotou tentativas → DLQ |

### Phase lifecycle (7)

| Tipo | Campos obrigatórios | Quem emite | Descrição |
|------|---------------------|------------|-----------|
| `phase_declared` | workflow_id, phases | Orquestrador | Declara as fases do workflow |
| `phase_entered` | phase, order | Orquestrador | Ativa uma fase |
| `phase_exit_criterion_met` | phase, criterion | Orquestrador | Registra critério de saída atingido |
| `phase_exit_approved` | phase, criteria_met, next_phase | Orquestrador | Aprova saída da fase |
| `phase_transitioned` | from_phase, to_phase, evidence_seq | Orquestrador | Transição entre fases |
| `phase_paused` | phase, reason | Orquestrador | Pausa a fase ativa |
| `phase_resumed` | phase | Orquestrador | Retoma fase pausada |

### Management and operations (6)

| Tipo | Campos obrigatórios | Quem emite | Descrição |
|------|---------------------|------------|-----------|
| `circuit_breaker_tripped` | — | Orquestrador | Circuit breaker ativado |
| `escalation` | code, severity, reason, evidence | Orquestrador | Escalation para humano |
| `human_response` | — | — | Resposta do operador |
| `snapshot` | — | orch-state/snapshot.py | Estado persistido (Task 1.8 deferida) |
| `log_recovered` | — | Operador | Recuperação manual do log |
| `preflight_failed` | — | Orquestrador | Falha na checagem pré-execução |

---

## 10. Fluxo completo — exemplo de ciclo

```
1. Usuário invoca o orquestrador

2. Orquestrador:
   a. verify_chain(mode="strict")       → integridade do log
   b. current_phase.py                  → qual fase está ativa?
   c. reduce.py                         → estado completo (tasks, fases)
   d. Decide ação baseado no estado

3. Orquestrador emite eventos via append.py:
   → phase_declared (se primeiro ciclo)
   → phase_entered
   → task_created × N

4. Para cada task ready:
   a. Orquestrador emite task_claimed via append.py
   b. Seta env vars: ORCH_WORKER_ID, ORCH_TASK_ID, ORCH_ATTEMPT
   c. Invoca worker via Agent()

5. Worker executa:
   a. Emite task_progress via emit.py (opcional, durante execução)
   b. Ao terminar:
      → task_completed  (sucesso)
      → task_failed     (falha)

6. Se worker para sem emitir terminal:
   → on_subagent_stop.py detecta (ORCH_* vars presentes, sem terminal)
   → Sintetiza task_failed(retryable=true)

7. Ao retornar, orquestrador repete o ciclo (volta ao passo 2)
   → Processa novos eventos, decide próximas ações
   → Retry, DLQ, transição de fase, escalation, etc.
```

---

## 11. Exceções públicas do orch_core

| Exceção | Quando ocorre |
|---------|---------------|
| `UnknownEventType` | `event_type` não está no enum de 21 tipos |
| `EventValidationError` | Payload falta campos obrigatórios |
| `LockTimeoutError` | Não conseguiu o lock em 10s |
| `CorruptedLogError` | JSON inválido no meio do log |
| `IllegalTransition` | Evento implica transição de estado inválida |
| `BlobIntegrityError` | Hash do blob não bate (tamper detectado) |
| `BlobNotFoundError` | Arquivo de blob referenciado não existe |
| `ConfigError` | `config.json` inválido ou ausente |

---

## 12. O que ainda não foi implementado (Fase 3+)

| Componente | Descrição |
|------------|-----------|
| `agents/orchestrator.md` | Definição do sub-agent orquestrador |
| `agents/workers/` | Workers genéricos (code-writer, test-runner, etc.) |
| `hooks/on_stop.py` | Persiste métricas ao encerrar sessão |
| `scripts/preflight.py` | Verificação pré-execução |
| `scripts/circuit_breaker.py` | Avaliação do circuit breaker |
| `scripts/dlq_triage.py` | Triagem de tasks em DLQ |
| `scripts/gc_orphan_blobs.py` | Coleta de blobs órfãos |
| Snapshots (Task 1.8) | Otimização do reducer com snapshots intermediários |
| Phase rules | Skills `phase-{nome}-rules` com lógica de negócio por fase |
