# new_flow — Arquitetura Detalhada

> Referência completa com diagramas de fluxo e estados.
> Fonte de verdade para entender como cada componente funciona, interage e falha.

---

## 1. Visão geral do sistema

O new_flow é um **motor de orquestração event-sourced** para workflows multi-fase no Claude Code. Toda comunicação entre componentes passa pelo log de eventos — nenhum componente armazena estado próprio entre invocações.

```mermaid
graph TD
    U([Usuário]) --> O

    subgraph CC["Claude Code Session"]
        O["Orchestrator\nsub-agent (Opus)"]

        O -->|"Bash(python3 append.py)"| AL["orch-log\nappend.py"]
        O -->|"Bash(python3 read.py)"| RL["orch-log\nread.py"]
        O -->|"Bash(python3 verify.py)"| VL["orch-log\nverify.py"]
        O -->|"Bash(python3 reduce.py)"| RS["orch-state\nreduce.py"]
        O -->|"Bash(python3 current_phase.py)"| CP["orch-state\ncurrent_phase.py"]
        O -->|"Agent()"| W1["Worker A\n(Sonnet)"]
        O -->|"Agent()"| W2["Worker B\n(Haiku)"]

        W1 -->|"Bash(python3 emit.py)"| EM["orch-report\nemit.py"]
        W2 -->|"Bash(python3 emit.py)"| EM

        AL --> LOG[(".orch/log.jsonl")]
        RL --> LOG
        VL --> LOG
        RS --> LOG
        CP --> LOG
        EM --> LOG

        HOOK["on_subagent_stop.py\n(SubagentStop hook)"] -->|sintetiza task_failed| LOG
    end

    subgraph LIB["Biblioteca compartilhada"]
        CORE["orch_core.py\n(importada por todos os scripts)"]
    end

    AL & RL & VL & RS & CP & EM & HOOK --> CORE
```

---

## 2. Princípio event-sourced

O log é **append-only** e **imutável**. O estado nunca é gravado diretamente — ele é sempre **reconstruído** pela aplicação sequencial dos eventos.

```mermaid
flowchart LR
    subgraph LOG["log.jsonl (append-only)"]
        E1["seq=1\nphase_declared"]
        E2["seq=2\nphase_entered"]
        E3["seq=3\ntask_created"]
        E4["seq=4\ntask_claimed"]
        E5["seq=5\ntask_completed"]
        E1 --> E2 --> E3 --> E4 --> E5
    end

    LOG -->|"reduce_all()"| STATE["OrchState\n(derivado, efêmero)"]

    STATE --> TK["tasks:\n  t_001: completed\n  t_002: ready"]
    STATE --> PH["phases:\n  dev: active"]
    STATE --> WF["workflow_id: wf_1\ncurrent_phase: dev"]
```

**Cadeia de hashes SHA-256:**

```mermaid
flowchart LR
    G(["prev_hash\n= 'GENESIS'"])

    G --> H1["Event seq=1\nprev_hash = GENESIS\nhash = SHA256(evento)"]
    H1 -->|hash| H2["Event seq=2\nprev_hash = hash(E1)\nhash = SHA256(evento)"]
    H2 -->|hash| H3["Event seq=3\nprev_hash = hash(E2)\nhash = SHA256(evento)"]

    style G fill:#f5f5f5,stroke:#999
```

Qualquer adulteração em um evento quebra a cadeia a partir daquele ponto. `verify_chain()` detecta isso em `O(n)`.

---

## 3. Estrutura de arquivos em runtime

```mermaid
graph TD
    ROOT["projeto/  (CWD)"]
    ROOT --> DC[".claude/"]
    ROOT --> OR[".orch/"]

    DC --> LIB[" lib/orch_core.py"]
    DC --> SK["skills/"]
    DC --> HK["hooks/on_subagent_stop.py"]
    DC --> ST["settings.json"]

    SK --> OL["orch-log/\nappend.py · read.py · verify.py"]
    SK --> OS["orch-state/\nreduce.py · summary.py · current_phase.py"]
    SK --> OR2["orch-report/\nemit.py"]

    OR --> LOG[" log.jsonl"]
    OR --> LCK["log.jsonl.lock"]
    OR --> BL["blobs/\nevt_XYZ.json  (payloads > 3500b)"]
    OR --> STA["state/  (snapshots — deferido)"]
    OR --> DLQ["dlq/  (dead-letter)"]
    OR --> MET["metrics/"]
    OR --> AUD["audit/"]
```

---

## 4. `append_event()` — fluxo interno

```mermaid
flowchart TD
    A([append_event chamado]) --> B{event_type\nem enum?}
    B -->|Não| ERR1([UnknownEventType])
    B -->|Sim| C{campos\nobrigatórios\npresentes?}
    C -->|Não| ERR2([EventValidationError])
    C -->|Sim| D[ensure_dirs]
    D --> E[Adquire LogLock\nfcntl.flock com timeout 10s]
    E -->|timeout| ERR3([LockTimeoutError])
    E -->|ok| F[last_event\nseq e prev_hash]
    F --> G{payload\n> 3500 bytes?}
    G -->|Sim| H[externalize_blob\n→ blobs/evt_XYZ.json\ndata = _blob_ref + _blob_hash]
    G -->|Não| I[data inline]
    H --> J
    I --> J[Cria Event\nseq · ts · agent · hash=SHA256]
    J --> K[json.dumps + write + fsync]
    K --> L[Libera lock]
    L --> M([Retorna Event])
```

---

## 5. Máquina de estados — Task

```mermaid
stateDiagram-v2
    [*] --> pending : task_created

    pending --> ready : fase ativa\n+ deps completas\n(_try_promote_to_ready)

    ready --> running : task_claimed\n(orquestrador)

    running --> completed : task_completed\n(worker via emit.py)

    running --> failed : task_failed\n(worker ou hook)
    running --> dlq : task_dlq\n(retryable=false)

    failed --> scheduled : task_scheduled_retry\n(orquestrador)
    failed --> dlq : task_dlq\n(esgotou tentativas)

    scheduled --> pending : task_retried\n(nova attempt)
    pending --> ready : _try_promote_to_ready

    completed --> [*]
    dlq --> [*]

    note right of running
        Tick de stale detection:
        se sem evento há > stale_seconds
        → task_failed(synthesized)
    end note

    note right of failed
        retryable=true → pode retry
        retryable=false → vai direto ao DLQ
    end note
```

**Promoção automática `pending → ready`** ocorre em dois momentos:
- Quando `task_created` é processado e a fase já está ativa + deps completas
- Quando `phase_entered` é processado (promove todas as tasks pending elegíveis)
- Quando `task_completed` é processado (promove tasks que dependiam desta)

---

## 6. Máquina de estados — Phase

```mermaid
stateDiagram-v2
    [*] --> pending : phase_declared

    pending --> active : phase_entered\n(apenas 1 fase ativa por vez)

    active --> exit_approved : phase_exit_approved\n(critérios validados)
    active --> paused : phase_paused

    paused --> active : phase_resumed

    exit_approved --> completed : phase_transitioned\n(from_phase=esta)

    completed --> [*]

    note right of active
        Ao entrar:
        _promote_pending_tasks()
        re-avalia todas as tasks pending
    end note

    note right of exit_approved
        next_phase indica
        qual fase entrar
        em seguida
    end note
```

---

## 7. Ciclo do orquestrador

```mermaid
flowchart TD
    START([Orquestrador invocado]) --> VER

    VER["verify.py --mode strict\nIntegridade do log"] -->|ok=false| ESC([escalation\nE09_corrupted_log])
    VER -->|ok=true| PH

    PH["current_phase.py\nQual fase está ativa?"] --> RED

    RED["reduce.py\nEstado completo (OrchState)"] --> DEC

    DEC{Decisão\nbased on state}

    DEC -->|"Nenhuma fase declarada"| DECL["append.py\nphase_declared\n+ phase_entered"]
    DEC -->|"Tasks ready disponíveis\n(abaixo do limite paralelo)"| CLAIM

    CLAIM["append.py\ntask_claimed\n(agent=orchestrator)"] --> ENV

    ENV["Seta env vars:\nORCH_WORKER_ID\nORCH_TASK_ID\nORCH_ATTEMPT"] --> SPAWN

    SPAWN["Agent()\nSpawna worker"] --> WAIT

    WAIT["Worker executa\n(emit.py → log)"] --> HOOK

    HOOK{on_subagent_stop\ncheck}
    HOOK -->|"terminal emitido\n(normal)"| NEXT
    HOOK -->|"sem terminal\n(crash/timeout)"| SYN["Sintetiza\ntask_failed(retryable=true)"]
    SYN --> NEXT

    NEXT{Estado pós-worker}
    NEXT -->|"tasks completed,\ncritérios de saída atendidos"| EXIT["phase_exit_criterion_met\n+ phase_exit_approved\n+ phase_transitioned"]
    NEXT -->|"task failed,\nretryable, dentro do limite"| RETRY["task_scheduled_retry\n→ task_retried"]
    NEXT -->|"task failed,\nesgotou tentativas"| DLQ["task_dlq"]
    NEXT -->|"mais tasks pending/ready"| DEC

    EXIT --> NEXTPHASE{Próxima fase?}
    NEXTPHASE -->|"Sim"| PH2["phase_entered\n(próxima fase)"]
    NEXTPHASE -->|"Não"| FIM([Workflow concluído])
    PH2 --> DEC

    DEC -->|"circuit breaker tripped"| CB([circuit_breaker_tripped\npausa workflow])
    DEC -->|"intervenção humana\nnecessária"| ESC2([escalation])
```

---

## 8. Fluxo worker — sequência completa

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant L as log.jsonl
    participant E as emit.py
    participant W as Worker
    participant H as on_subagent_stop.py

    O->>L: append task_claimed<br/>(agent=orchestrator, worker_id=w_42)
    Note over O: ORCH_WORKER_ID=w_42<br/>ORCH_TASK_ID=t_001<br/>ORCH_ATTEMPT=1

    O->>W: Agent() — spawna worker

    activate W
    W->>E: emit.py --kind progress<br/>--task-id t_001<br/>--data {note:"processando..."}
    E->>L: append task_progress<br/>(agent=w_42)

    alt Sucesso
        W->>E: emit.py --kind completed<br/>--data {artifacts:[...],summary:"..."}
        E->>L: append task_completed<br/>(agent=w_42)
        deactivate W
        H->>L: _has_terminal → True → no-op
    else Falha explícita
        W->>E: emit.py --kind failed<br/>--data {reason:"...",retryable:true}
        E->>L: append task_failed<br/>(agent=w_42)
        deactivate W
        H->>L: _has_terminal → True → no-op
    else Crash / timeout / context overflow
        deactivate W
        Note over H: SubagentStop hook dispara
        H->>L: read_events_filtered(task_id=t_001)
        H->>L: _has_terminal → False
        H->>L: append task_failed<br/>(agent=w_42,<br/>reason="worker_stopped_without_terminal_event",<br/>retryable=true,synthesized_by=w_42)
    end

    O->>L: reduce.py → novo estado
    O->>O: Decide próxima ação
```

---

## 9. Guard-rail do `emit.py`

```mermaid
flowchart TD
    W([Worker chama emit.py]) --> ENV{ORCH_WORKER_ID\nno ambiente?}
    ENV -->|"Não"| ERR1(["exit 1\nmissing_env"])
    ENV -->|"Sim"| KIND{"--kind válido?\nprogress|completed|failed"}
    KIND -->|"Não (argparse rejeita)"| ERR2(["exit 1\nargparse error\nantes de qualquer I/O"])
    KIND -->|"Sim"| JSON{data é\nJSON válido?}
    JSON -->|"Não"| ERR3(["exit 1\ninvalid_json"])
    JSON -->|"Sim"| MAP["Mapeia kind → event_type\nprogress  → task_progress\ncompleted → task_completed\nfailed    → task_failed"]
    MAP --> APPEND["append_event(\n  agent=ORCH_WORKER_ID,\n  event_type=mapeado,\n  ...)\n"]
    APPEND -->|"ok"| OUT(["exit 0\nJSON do evento"])
    APPEND -->|"EventValidationError"| ERR4(["exit 1\nvalidation_error"])

    style ERR2 fill:#ffcccc,stroke:#cc0000
    note1["Nenhum tipo de orquestrador\npode ser emitido via este script.\nA rejeição é estrutural (argparse choices),\nnão lógica — não há código a contornar."]
```

---

## 10. Hook `on_subagent_stop.py`

```mermaid
flowchart TD
    TRIGGER([Claude Code: SubagentStop]) --> READ["Lê stdin (ignora)"]
    READ --> ENV{ORCH_TASK_ID\nORCH_ATTEMPT\nORCH_WORKER_ID\ntodas presentes?}

    ENV -->|"Não (qualquer ausente)"| NOOP1(["exit 0\nnão é contexto orquestrado"])

    ENV -->|"Sim"| TERM{Existe evento\ntask_completed ou task_failed\npara (task_id, attempt)?}

    TERM -->|"Sim"| NOOP2(["exit 0\nterminal já emitido"])

    TERM -->|"Não"| PHASE["Busca phase\nde task_created no log"]
    PHASE --> SYN["append_event(\n  agent=ORCH_WORKER_ID,\n  event_type=task_failed,\n  task_id=ORCH_TASK_ID,\n  attempt=ORCH_ATTEMPT,\n  data={\n    phase: ...,\n    reason: 'worker_stopped_without_terminal_event',\n    retryable: True,\n    synthesized_by: ORCH_WORKER_ID\n  }\n)"]
    SYN --> DONE(["exit 0\n(hook nunca retorna != 0)"])
```

---

## 11. Verificação do log

```mermaid
flowchart TD
    V([verify_chain chamado]) --> EMPTY{Log\nvazio?}
    EMPTY -->|"Sim"| OK1(["ok=True\nevents_verified=0"])
    EMPTY -->|"Não"| ITER["Itera eventos\nprev_hash='GENESIS'"]

    ITER --> EACH{Para cada evento}
    EACH --> CK1{prev_hash\nbate?}
    CK1 -->|"Não"| ERR["error: chain_broken\nseq, expected vs actual"]
    CK1 -->|"Sim"| CK2{compute_hash()\nbate com hash\narmazenado?}
    CK2 -->|"Não"| ERR2["error: hash_mismatch\nseq, expected vs actual"]
    CK2 -->|"Sim"| NEXT["prev_hash = evento.hash\ncount++"]
    NEXT --> EACH

    ERR --> MODE{mode?}
    ERR2 --> MODE
    MODE -->|"strict"| STOP(["ok=False\nfirst_error_seq=N\nstop"])
    MODE -->|"audit"| CONT["Acumula erro\ncontinua iterando"]
    CONT --> EACH

    EACH -->|"fim do log"| DONE
    DONE --> RESULT{Houve erros?}
    RESULT -->|"Não"| OK2(["ok=True\nevents_verified=N"])
    RESULT -->|"Sim (apenas audit)"| FAIL(["ok=False\nerror_details=[...]"])
```

---

## 12. Externalização de blobs

```mermaid
flowchart LR
    subgraph APPEND["append_event()"]
        SIZE{len payload\n> 3500 bytes?}
    end

    SIZE -->|"Não"| INLINE["data inline\nno log.jsonl"]

    SIZE -->|"Sim"| EXT["externalize_blob()\nescreve em\n.orch/blobs/evt_XYZ.json\nsha256 do conteúdo"]

    EXT --> REF["data no log:\n{\n  _blob_ref: 'blobs/evt_XYZ.json',\n  _size: N,\n  _blob_hash: 'sha256...'\n}"]

    INLINE --> LOG[("log.jsonl")]
    REF --> LOG

    LOG -->|"read_events_filtered\ncom phase filter"| RESOLVE["is_blob_ref?\n→ load_blob_data()\n  verifica hash\n  retorna payload real"]
```

**Portabilidade:** `_blob_ref` é sempre relativo a `ORCH_DIR`, não ao path absoluto. O projeto pode ser movido sem quebrar as referências.

---

## 13. Variáveis de ambiente

```mermaid
flowchart LR
    O[Orchestrator] -->|"seta antes de Agent()"| ENV

    subgraph ENV["Env vars injetadas no worker"]
        WID["ORCH_WORKER_ID\nexemplo: worker-abc123"]
        TID["ORCH_TASK_ID\nexemplo: t_001"]
        ATT["ORCH_ATTEMPT\nexemplo: 1"]
    end

    ENV --> EM["emit.py\nusa ORCH_WORKER_ID\ncomo agent do evento"]
    ENV --> HK["on_subagent_stop.py\nusa as 3 vars para\nidentificar o contexto"]

    WID -.->|"worker não pode\nsobrescrever"| EM
```

| Variável | Quem seta | Quem lê | Se ausente |
|----------|-----------|---------|------------|
| `ORCH_WORKER_ID` | Orquestrador | `emit.py`, `on_subagent_stop.py` | `emit.py` → exit 1; hook → no-op |
| `ORCH_TASK_ID` | Orquestrador | `on_subagent_stop.py` | hook → no-op |
| `ORCH_ATTEMPT` | Orquestrador | `on_subagent_stop.py` | hook → no-op |

---

## 14. Mapa de campos obrigatórios por evento

### Task lifecycle

| Evento | Campos obrigatórios |
|--------|-------------------|
| `task_created` | `phase`, `tier`, `type`, `spec`, `deps` |
| `task_claimed` | `phase`, `worker_type`, `worker_id` |
| `task_progress` | `phase`, `note` |
| `task_completed` | `phase`, `artifacts`, `summary` |
| `task_failed` | `phase`, `reason`, `retryable` |
| `task_scheduled_retry` | `phase`, `next_retry_at`, `backoff_seconds`, `previous_failure_seq` |
| `task_retried` | `phase`, `previous_attempt`, `scheduled_retry_seq` |
| `task_dlq` | `phase`, `reason`, `last_error` |

### Phase lifecycle

| Evento | Campos obrigatórios |
|--------|-------------------|
| `phase_declared` | `workflow_id`, `phases` |
| `phase_entered` | `phase`, `order` |
| `phase_exit_criterion_met` | `phase`, `criterion` |
| `phase_exit_approved` | `phase`, `criteria_met`, `next_phase` |
| `phase_transitioned` | `from_phase`, `to_phase`, `evidence_seq` |
| `phase_paused` | `phase`, `reason` |
| `phase_resumed` | `phase`, `paused_seq` |

### Management

| Evento | Campos obrigatórios |
|--------|-------------------|
| `escalation` | `code`, `severity`, `reason`, `evidence` |
| `circuit_breaker_tripped`, `human_response`, `snapshot`, `log_recovered`, `preflight_failed` | — |

---

## 15. Retry e tiers

```mermaid
flowchart TD
    FAIL["task_failed\nretryable=true"] --> CHECK{attempts\n< max_attempts?}

    CHECK -->|"Não (esgotou)"| DLQ["task_dlq\nreason='max_attempts_exceeded'"]
    CHECK -->|"Sim"| BACK["backoff_seconds\ncritical: base=15s, exp\nstandard: base=30s, exp\nbulk: 0s (sem retry)"]

    BACK --> SCHED["task_scheduled_retry\nnext_retry_at, backoff_seconds,\nprevious_failure_seq"]

    SCHED -->|"tempo esgotado"| RETRY["task_retried\n(attempt+1)"]
    RETRY --> CLAIM["task_claimed\n(novo worker)"]
    CLAIM --> RUN["running..."]

    subgraph TIERS["Tier — max_attempts"]
        TC["critical: 5 tentativas\nstale: 600s"]
        TS["standard: 3 tentativas\nstale: 300s"]
        TB["bulk: 1 tentativa\nstale: 120s"]
    end
```

---

## 16. Reduce — fluxo interno do reducer

```mermaid
flowchart TD
    A(["reduce_all()"]) --> B["state = OrchState()"]
    B --> C["for event in read_events()"]

    C --> D["apply_event(state, event)"]

    D --> E{event_type\nem _HANDLERS?}
    E -->|"Sim"| F["Desempacota blob se necessário\n(try/finally restore)"]
    F --> G["handler(state, event)"]
    G --> H["state.last_seq = event.seq"]
    E -->|"Não (ex: task_progress)"| H

    H --> C
    C -->|"fim do log"| I(["Retorna OrchState"])

    subgraph HANDLERS["_HANDLERS registrados"]
        direction LR
        H1["phase_declared → workflow_id + phases{}"]
        H2["phase_entered → phases[n].status=ACTIVE\n+ _promote_pending_tasks()"]
        H3["task_created → tasks[id]=TaskState\n+ _try_promote_to_ready()"]
        H4["task_claimed → status=RUNNING"]
        H5["task_completed → status=COMPLETED\n+ _promote_pending_tasks()"]
        H6["task_failed → status=FAILED"]
        H7["task_scheduled_retry → status=SCHEDULED"]
        H8["task_retried → status=PENDING\n+ _try_promote_to_ready()"]
        H9["task_dlq → status=DLQ"]
        H10["escalation → run_status='escalated'"]
        H11["circuit_breaker_tripped → circuit_breaker{}"]
        H12["phase_* handlers → PhaseState mutations"]
    end
```

---

## 17. Exceções e tratamento

```mermaid
flowchart LR
    subgraph ERROS["Hierarquia de exceções"]
        OE["OrchError (base)"]
        OE --> LTE["LockTimeoutError\nfcntl timeout"]
        OE --> EVE["EventValidationError\ncampos obrigatórios faltando"]
        OE --> CLE["CorruptedLogError\nJSON inválido no log"]
        OE --> ITE["IllegalTransition\ntransição de estado inválida"]
        OE --> UKE["UnknownEventType\nnão está no enum"]
        OE --> BIE["BlobIntegrityError\nhash do blob diverge"]
        OE --> BNE["BlobNotFoundError\narquivo de blob ausente"]
        OE --> CFE["ConfigError\nconfig.json inválido"]
    end
```

| Exceção | Onde tratada | Comportamento |
|---------|-------------|---------------|
| `LockTimeoutError` | Scripts CLI | exit 1 + JSON de erro |
| `EventValidationError` | `append.py`, `emit.py` | exit 1 + JSON de erro |
| `CorruptedLogError` | `verify.py`, `read.py`, `reduce.py` | exit 1 + JSON de erro; em `strict` pára no primeiro |
| `IllegalTransition` | Logs do orchestrator | escalation E-code |
| `UnknownEventType` | `append.py`, `emit.py` | exit 1 + JSON de erro |
| `BlobIntegrityError` | `read_events_filtered` | propaga como `CorruptedLogError` |
| Qualquer exceção em hook | `on_subagent_stop.py` | silenciada — hook nunca falha |

---

## 18. O que falta implementar (Fase 3+)

```mermaid
graph LR
    subgraph DONE["✅ Implementado (Fases 1+2)"]
        C1["orch_core.py"]
        C2["orch-log skills"]
        C3["orch-state skills"]
        C4["orch-report/emit.py"]
        C5["on_subagent_stop.py"]
    end

    subgraph NEXT["🔜 Fase 3 — Orchestrator + Workers"]
        N1["agents/orchestrator.md\n(sub-agent definition)"]
        N2["agents/workers/\ncode-writer, test-runner,\ncode-reviewer, migration-writer"]
        N3["hooks/on_stop.py\n(métricas finais)"]
    end

    subgraph F4["📋 Fase 4 — Robustez"]
        F1["scripts/preflight.py"]
        F2["scripts/circuit_breaker.py"]
        F3["scripts/dlq_triage.py"]
        F4b["scripts/gc_orphan_blobs.py"]
    end

    subgraph F5["📋 Fase 5 — Phase rules"]
        P1["skills/phase-sdd-rules/"]
        P2["skills/phase-dev-rules/"]
        P3["skills/phase-review-rules/"]
        P4["skills/phase-test-rules/"]
    end

    subgraph DEF["⏩ Deferido"]
        D1["Task 1.8: snapshots\n(orch-state/snapshot.py)"]
    end

    DONE --> NEXT --> F4 --> F5
    DEF -.->|"após Fase 3\ncom dados reais"| NEXT
```
