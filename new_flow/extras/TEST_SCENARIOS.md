# Test Scenarios — Orquestrador Multi-Fase

> Cenários de teste em formato Given/When/Then.
> Uso: critério objetivo de "done" para implementação; base para transformar em testes pytest automatizados.
> Cobertura: ~30 cenários que exercitam fluxos críticos sem depender de LLM.

---

## Como usar este documento

Cada cenário descreve um caso concreto que o sistema deve suportar. Três aplicações:

1. **Critério de aceite**: para cada módulo implementado, verifique que os cenários relevantes passam
2. **Base para testes automatizados**: cada cenário vira 1-3 testes pytest
3. **Documentação executável**: novos contribuidores leem cenários para entender comportamento esperado

**Formato padrão** de cada cenário:

```
Dado <estado inicial>
Quando <ação ocorre>
Então <resultado esperado>
E <resultado adicional>
```

Cenários com prefixo `[CRIT]` são críticos (bloqueadores de piloto). `[HAPPY]` são caminhos felizes. `[EDGE]` são edge cases.

---

## Sumário

1. [Event log: append e leitura](#1-event-log-append-e-leitura)
2. [Hash chain e integridade](#2-hash-chain-e-integridade)
3. [Reducer e máquina de estados de task](#3-reducer-e-máquina-de-estados-de-task)
4. [Retry e circuit breaker](#4-retry-e-circuit-breaker)
5. [Fases e transições](#5-fases-e-transições)
6. [Blobs e payloads grandes](#6-blobs-e-payloads-grandes)
7. [Hooks e robustez](#7-hooks-e-robustez)
8. [Concorrência](#8-concorrência)
9. [Recovery e crash](#9-recovery-e-crash)
10. [Escalação e intervenção humana](#10-escalação-e-intervenção-humana)

---

## 1. Event log: append e leitura

### [HAPPY] 1.1 Primeiro evento no log vazio

**Dado** um `.orch/` vazio (sem log.jsonl)
**Quando** chamo `append_event(agent="orchestrator", event_type="phase_declared", data={...})`
**Então** o arquivo `.orch/log.jsonl` é criado
**E** contém exatamente uma linha
**E** o evento tem `seq == 1`
**E** o evento tem `prev_hash == "GENESIS"`
**E** o evento tem `hash` calculado corretamente
**E** o evento tem `event_id` no formato `evt_[A-Z0-9]{26}`
**E** o evento tem `ts` no formato ISO 8601 UTC com ms

### [HAPPY] 1.2 Seq é monotônico em escritas sequenciais

**Dado** um log com evento `seq=5`
**Quando** chamo `append_event` 3 vezes consecutivas
**Então** os eventos resultantes têm `seq = 6, 7, 8`
**E** cada evento tem `prev_hash` igual ao `hash` do anterior
**E** todos os `event_id` são únicos

### [HAPPY] 1.3 Leitura retorna eventos em ordem de seq

**Dado** um log com 10 eventos nas seqs 1-10
**Quando** chamo `list(read_events())`
**Então** recebo 10 eventos
**E** o primeiro tem `seq=1`, o último `seq=10`
**E** os `event_id` estão em ordem de inserção

### [HAPPY] 1.4 Filtro from_seq funciona

**Dado** um log com 10 eventos
**Quando** chamo `list(read_events(from_seq=5))`
**Então** recebo 6 eventos (seqs 5-10)
**E** o primeiro tem `seq=5`

### [EDGE] 1.5 Log vazio retorna iterator vazio

**Dado** um `.orch/log.jsonl` inexistente
**Quando** chamo `list(read_events())`
**Então** recebo lista vazia (sem exception)
**E** `last_event()` retorna `None`

### [EDGE] 1.6 Última linha truncada é tolerada

**Dado** um log com 3 eventos válidos
**E** a última linha foi truncada a meio caminho (simulando crash durante write)
**Quando** chamo `list(read_events())`
**Então** recebo 3 eventos (os válidos)
**E** nenhuma exception é levantada
**E** `last_event()` retorna o terceiro evento

### [CRIT] 1.7 Corrupção no meio do log levanta exception

**Dado** um log com 5 eventos
**E** a linha 3 foi substituída por JSON inválido
**Quando** chamo `list(read_events())`
**Então** `CorruptedLogError` é levantada
**E** a mensagem indica `seq=3` como ponto de corrupção

### [CRIT] 1.8 Event_type desconhecido é rejeitado em append

**Dado** um log vazio
**Quando** chamo `append_event(event_type="invalid_type", ...)`
**Então** `ValueError` ou `EventValidationError` é levantada
**E** nada é escrito no log (arquivo continua vazio ou inalterado)

### [CRIT] 1.9 Campo `phase` obrigatório em task_created

**Dado** um log vazio
**Quando** chamo `append_event(event_type="task_created", data={"tier": "standard", ...})` (sem `phase`)
**Então** `EventValidationError` é levantada com mensagem mencionando `phase`
**E** nada é escrito no log

---

## 2. Hash chain e integridade

### [HAPPY] 2.1 verify_chain passa em log íntegro

**Dado** um log com 10 eventos válidos criados via `append_event`
**Quando** chamo `verify_chain(mode="strict")`
**Então** resultado tem `ok=True`
**E** `events_verified == 10`
**E** `first_error_seq is None`

### [CRIT] 2.2 verify_chain detecta adulteração de data

**Dado** um log com 5 eventos criados via `append_event`
**E** edito manualmente o `data` do evento `seq=3` (preservando o `hash`)
**Quando** chamo `verify_chain(mode="strict")`
**Então** resultado tem `ok=False`
**E** `first_error_seq == 3`
**E** mensagem menciona "hash mismatch"

### [CRIT] 2.3 verify_chain detecta reordenação

**Dado** um log com 5 eventos
**E** troco as linhas 2 e 3 de lugar (mantendo `hash` original de cada)
**Quando** chamo `verify_chain(mode="strict")`
**Então** resultado tem `ok=False`
**E** `first_error_seq == 2` (prev_hash não bate)

### [EDGE] 2.4 verify_chain modo audit reporta todos os erros

**Dado** um log com 2 pontos de corrupção (seq 3 e seq 7)
**Quando** chamo `verify_chain(mode="audit")`
**Então** resultado tem `ok=False`
**E** `error_details` contém 2 entradas
**E** log não foi modificado

### [CRIT] 2.5 canonical_json é determinístico

**Dado** um evento E1 com `data = {"b": 2, "a": 1}`
**E** um evento E2 (mesmos campos) com `data = {"a": 1, "b": 2}`
**Quando** chamo `canonical_json` em ambos
**Então** as strings resultantes são idênticas
**E** `compute_hash` produz mesmo hash

### [CRIT] 2.6 Hash exclui o próprio campo hash

**Dado** um Event com `hash = "original"`
**Quando** chamo `event.compute_hash()`
**E** modifico `event.hash = "different"` e recalculo
**Então** ambas as invocações produzem mesmo hash
**E** a canonicalização não inclui `"hash"` como chave

---

## 3. Reducer e máquina de estados de task

### [HAPPY] 3.1 task_created põe task em pending

**Dado** um log vazio
**Quando** aplico evento `task_created(t_001, deps=[])`
**Então** `state.tasks["t_001"].status == "pending"`
**E** `state.tasks["t_001"].attempts == 0`

### [HAPPY] 3.2 Task sem deps em fase ativa vira ready

**Dado** estado com `current_phase = "dev"` (active)
**E** evento `task_created(t_001, phase="dev", deps=[])`
**Quando** reducer aplica
**Então** `state.tasks["t_001"].status == "ready"`

### [HAPPY] 3.3 Task com deps aguarda completar deps

**Dado** estado com `current_phase = "dev"` (active)
**E** evento `task_created(t_001, phase="dev", deps=[])`
**E** evento `task_created(t_002, phase="dev", deps=["t_001"])`
**Quando** reducer aplica
**Então** `t_001.status == "ready"`
**E** `t_002.status == "pending"`

### [HAPPY] 3.4 Task promove para ready após dep completa

**Dado** estado com `t_001` em `ready` e `t_002` em `pending` (deps=[t_001])
**Quando** aplico `task_claimed(t_001)` e `task_completed(t_001)`
**Então** `t_001.status == "completed"`
**E** `t_002.status == "ready"`

### [HAPPY] 3.5 task_claimed move ready para running

**Dado** `t_001` em status `ready`
**Quando** aplico `task_claimed(t_001, attempt=1)`
**Então** `t_001.status == "running"`
**E** `t_001.worker_id` está setado
**E** `t_001.claimed_at` está setado

### [CRIT] 3.6 Transição ilegal pending → running levanta

**Dado** `t_001` em status `pending`
**Quando** aplico `task_claimed(t_001)` (pulou ready)
**Então** `IllegalTransition` é levantada
**E** estado não é modificado

### [CRIT] 3.7 Transição ilegal completed → qualquer coisa levanta

**Dado** `t_001` em status `completed`
**Quando** aplico `task_claimed(t_001)` ou `task_failed(t_001)` ou qualquer outro
**Então** `IllegalTransition` é levantada

### [HAPPY] 3.8 task_failed com retryable=true vai para failed

**Dado** `t_001` em `running`, attempts=1, max_attempts=3
**Quando** aplico `task_failed(t_001, retryable=true, reason="...")`
**Então** `t_001.status == "failed"`
**E** `t_001.last_failure_retryable == True`

### [HAPPY] 3.9 task_failed com retryable=false vai direto pra DLQ via task_dlq

**Dado** `t_001` em `running`, attempts=1, max_attempts=3
**Quando** aplico `task_failed(t_001, retryable=false)`
**E** aplico `task_dlq(t_001, reason="non_retryable")`
**Então** `t_001.status == "dlq"`
**E** `t_001.attempts == 1` (não consumiu tentativa adicional)

### [HAPPY] 3.10 task_scheduled_retry move failed para scheduled

**Dado** `t_001` em status `failed` (retryable=true, attempts < max)
**Quando** aplico `task_scheduled_retry(t_001, next_retry_at=..., backoff_seconds=45)`
**Então** `t_001.status == "scheduled"`
**E** `t_001.next_retry_at` está setado

### [HAPPY] 3.11 task_retried move scheduled para pending/ready

**Dado** `t_001` em `scheduled`, attempts=1
**E** fase da task está ativa
**Quando** aplico `task_retried(t_001, attempt=2)`
**Então** `t_001.status == "ready"` (se sem deps) ou `"pending"` (se com deps)
**E** `t_001.attempts == 2`
**E** `t_001.next_retry_at is None`

### [EDGE] 3.12 task_dlq em attempts=max_attempts

**Dado** `t_001` em `failed`, attempts=3, max_attempts=3, retryable=true
**Quando** aplico `task_dlq(t_001, reason="max_attempts_exceeded")`
**Então** `t_001.status == "dlq"`

### [HAPPY] 3.13 Reducer é puro (mesmo log produz mesmo estado)

**Dado** um log com 20 eventos
**Quando** chamo `reduce_all()` duas vezes
**Então** os dois estados são iguais (`state1.to_dict() == state2.to_dict()`)

### [CRIT] 3.14 Duas task_completed para mesma (task, attempt) gera escalação

**Dado** um reducer processando eventos em ordem
**Quando** encontra duas `task_completed` para `(t_001, attempt=1)`
**Então** `IllegalTransition` ou `escalation` é sinalizada
**E** `state.escalation` contém code E05 (se implementado por escalation em vez de raise)

---

## 4. Retry e circuit breaker

### [HAPPY] 4.1 Backoff é exponencial com jitter

**Dado** `base_delay_s=30, cap_s=600`
**Quando** chamo `backoff_seconds(attempts=N)` para N=1,2,3,4
**Então** valores ficam em:
  - N=1: [24, 36] (30 × [0.8, 1.2])
  - N=2: [48, 72]
  - N=3: [96, 144]
  - N=4: [192, 288]
**E** nunca excedem `cap_s × 1.2 = 720`

### [HAPPY] 4.2 Backoff capped em cap_s × jitter

**Dado** `base_delay_s=30, cap_s=60`
**Quando** chamo `backoff_seconds(attempts=10)` (normalmente daria 30 × 512)
**Então** valor fica em [48, 72] (60 × [0.8, 1.2])

### [HAPPY] 4.3 Retry policy por tier tem defaults

**Dado** config default
**Quando** carrego policy para tier="critical"
**Então** `max_attempts == 5, base_delay_s == 15`
**E** para tier="standard": `max_attempts == 3, base_delay_s == 30`
**E** para tier="bulk": `max_attempts == 1, base_delay_s == 0`

### [HAPPY] 4.4 Override por task_type precede tier

**Dado** config com tier standard (max=3) e override para e2e-test (max=5)
**Quando** carrego policy para task_type="e2e-test", tier="standard"
**Então** `max_attempts == 5` (override venceu)

### [HAPPY] 4.5 should_retry=False para retryable=false

**Dado** task em `failed`, `last_failure_retryable=False`
**Quando** chamo `should_retry(task, policy)`
**Então** retorna `False`

### [HAPPY] 4.6 should_retry=False quando attempts >= max

**Dado** task em `failed`, attempts=3, max_attempts=3, retryable=true
**Quando** chamo `should_retry(task, policy)`
**Então** retorna `False`

### [CRIT] 4.7 Circuit breaker dispara em 50 falhas em 10min

**Dado** config com `failure_threshold=50, window_minutes=10`
**E** 49 `task_failed` emitidos em janela de 5min
**Quando** 50o `task_failed` é emitido
**Então** próxima execução do reducer detecta threshold
**E** emite `circuit_breaker_tripped`
**E** `state.circuit_breaker.status == "tripped"`

### [HAPPY] 4.8 Circuit breaker não dispara com falhas fora da janela

**Dado** 30 falhas em minuto 0
**E** 30 falhas em minuto 15 (fora da janela de 10min)
**Quando** janela atual é avaliada
**Então** breaker não dispara (só 30 na janela atual)

### [EDGE] 4.9 Reset manual emite evento apropriado

**Dado** circuit breaker tripped
**Quando** operador executa reset
**Então** novo evento é emitido (escalation resolvido via human_response ou reset específico)
**E** spawns podem prosseguir novamente

---

## 5. Fases e transições

### [HAPPY] 5.1 phase_declared inicializa fases em pending

**Dado** log vazio
**Quando** aplico `phase_declared(workflow_id, phases=[{sdd,1,true}, {dev,2,true}])`
**Então** `state.phases["sdd"].status == "pending"` e `order == 1`
**E** `state.phases["dev"].status == "pending"` e `order == 2`

### [HAPPY] 5.2 phase_entered move pending para active

**Dado** `state.phases["sdd"].status == "pending"`
**Quando** aplico `phase_entered(phase="sdd")`
**Então** `state.phases["sdd"].status == "active"`
**E** `state.current_phase == "sdd"`

### [CRIT] 5.3 Apenas uma fase active por vez

**Dado** fase "sdd" em active
**Quando** tento aplicar `phase_entered(phase="dev")` sem transitioned
**Então** `IllegalTransition` é levantada

### [HAPPY] 5.4 phase_exit_approved move active para exit_approved

**Dado** fase "sdd" em active
**Quando** aplico `phase_exit_approved(phase="sdd", next_phase="dev")`
**Então** `state.phases["sdd"].status == "exit_approved"`
**E** `state.phases["sdd"].criteria_met` está populado

### [HAPPY] 5.5 phase_transitioned fecha anterior e abre próxima

**Dado** fase "sdd" em exit_approved
**Quando** aplico `phase_transitioned(from="sdd", to="dev")`
**E** aplico `phase_entered(phase="dev")`
**Então** `state.phases["sdd"].status == "completed"`
**E** `state.phases["dev"].status == "active"`
**E** `state.current_phase == "dev"`

### [CRIT] 5.6 Task da fase pending não é promovida a ready

**Dado** fase "dev" em pending (ainda não ativa)
**E** task `t_001, phase="dev", deps=[]`
**Quando** reducer processa
**Então** `t_001.status == "pending"` (não promoveu para ready)

### [HAPPY] 5.7 Task da fase pending fica ready após fase ativar

**Dado** task `t_001, phase="dev", deps=[]` em `pending` (fase dev ainda pending)
**Quando** aplico `phase_transitioned(sdd → dev)` e `phase_entered(dev)`
**Então** `t_001.status == "ready"`

### [HAPPY] 5.8 Dependência cross-phase: dep na fase SDD, task na fase Dev

**Dado** fase sdd active
**E** task `t_spec (phase=sdd)` e `t_impl (phase=dev, deps=[t_spec])`
**Quando** `t_spec` completa e depois fase transiciona sdd → dev
**Então** após transition, `t_impl.status == "ready"`

### [CRIT] 5.9 current_phase é derivado do log

**Dado** um log com eventos de fase
**Quando** reinício o processo e chamo `reduce_all()`
**Então** `state.current_phase` é o mesmo que antes do restart
**E** é derivado somente do log, sem estado externo

### [HAPPY] 5.10 phase_exit_criterion_met audita critérios individuais

**Dado** fase "sdd" em active
**Quando** aplico `phase_exit_criterion_met(phase="sdd", criterion="all_tasks_decomposed")`
**E** depois `phase_exit_criterion_met(phase="sdd", criterion="specs_validated")`
**Então** `state.phases["sdd"].criteria_met` contém ambos os IDs

### [HAPPY] 5.11 phase_paused e phase_resumed funcionam

**Dado** fase "dev" em active
**Quando** aplico `phase_paused(phase="dev", reason="escalation")`
**Então** `state.phases["dev"].status == "paused"`
**Quando** depois aplico `phase_resumed(phase="dev")`
**Então** `state.phases["dev"].status == "active"`

---

## 6. Blobs e payloads grandes

### [HAPPY] 6.1 Payload pequeno é inline

**Dado** evento com `data` serializado em 200 bytes
**Quando** chamo `append_event`
**Então** evento no log tem `data` inline completo
**E** nenhum arquivo é criado em `.orch/blobs/`

### [CRIT] 6.2 Payload grande é externalizado

**Dado** evento com `data` serializado em 10000 bytes
**Quando** chamo `append_event`
**Então** evento no log tem `data = {"_blob_ref": ..., "_size": ..., "_blob_hash": ...}`
**E** arquivo `.orch/blobs/{event_id}.json` é criado
**E** conteúdo do blob tem hash SHA-256 igual a `_blob_hash`

### [CRIT] 6.3 load_blob_data verifica integridade

**Dado** evento externalizado com `_blob_hash = "abc..."`
**E** blob em disco foi adulterado (hash atual != abc...)
**Quando** chamo `load_blob_data(event)`
**Então** `BlobIntegrityError` é levantada
**E** mensagem identifica o arquivo corrompido

### [HAPPY] 6.4 load_blob_data retorna data inline quando não é blob

**Dado** evento com `data = {"key": "value"}` (inline)
**Quando** chamo `load_blob_data(event)`
**Então** retorna `{"key": "value"}`
**E** nenhum arquivo é lido

### [EDGE] 6.5 Blob missing levanta FileNotFoundError

**Dado** evento externalizado referenciando `.orch/blobs/evt_X.json`
**E** arquivo não existe (foi deletado)
**Quando** chamo `load_blob_data(event)`
**Então** `FileNotFoundError` ou `BlobNotFoundError` é levantada

### [HAPPY] 6.6 reduce_incremental carrega blobs quando necessário

**Dado** log com mix de eventos inline e externalizados
**Quando** chamo `reduce_incremental()`
**Então** estado final é correto (data externalizado foi carregado)
**E** tasks com artifacts grandes têm dados completos

### [HAPPY] 6.7 is_blob_ref detecta corretamente

**Dado** `data1 = {"_blob_ref": "...", "_size": 100, "_blob_hash": "..."}`
**E** `data2 = {"key": "value"}`
**Quando** chamo `is_blob_ref` em ambos
**Então** retorna `True` para `data1`, `False` para `data2`

---

## 7. Hooks e robustez

### [CRIT] 7.1 Hook on_subagent_stop sintetiza failed quando worker silencia

**Dado** evento `task_claimed(t_001, worker_id=X, attempt=1)`
**E** nenhum evento terminal (`task_completed` ou `task_failed`) foi emitido
**E** env vars `ORCH_TASK_ID=t_001, ORCH_ATTEMPT=1, ORCH_WORKER_ID=X` setadas
**Quando** hook executa
**Então** emite `task_failed(t_001, attempt=1, retryable=true, synthesized_by="worker_stopped_without_terminal_event")`

### [HAPPY] 7.2 Hook é no-op se env vars ausentes

**Dado** hook executa sem env vars ORCH_* setadas
**Quando** hook processa stdin
**Então** nenhum evento é emitido
**E** exit code é 0

### [HAPPY] 7.3 Hook é no-op se worker emitiu terminal

**Dado** evento `task_claimed(t_001, attempt=1)`
**E** evento `task_completed(t_001, attempt=1)` já emitido
**E** env vars ORCH_* setadas para essa task/attempt
**Quando** hook executa
**Então** nenhum evento é emitido (não duplica terminal)

### [CRIT] 7.4 Stale detection sintetiza failed

**Dado** task em `running` há mais tempo que `tier.stale_seconds`
**E** nenhum novo evento desde o `task_claimed`
**Quando** orchestrator processa ciclo
**Então** emite `task_failed(synthesized_by="stale_detection", retryable=true)`

### [EDGE] 7.5 emit.py rejeita eventos de orquestrador

**Dado** script emit.py sendo chamado pelo worker
**Quando** worker tenta emitir `event_type="task_claimed"` ou `task_dlq` ou `escalation`
**Então** emit.py retorna exit code != 0
**E** stderr indica "event_type not permitted for workers"
**E** nenhum evento é escrito

### [HAPPY] 7.6 emit.py aceita eventos worker-emittable

**Dado** worker chamando emit.py
**Quando** emite `task_progress`, `task_completed` ou `task_failed`
**Então** evento é escrito normalmente
**E** exit code é 0

---

## 8. Concorrência

### [CRIT] 8.1 40 writes paralelos preservam seq monotônico

**Dado** 4 processos que chamam `append_event` em loop (10 vezes cada)
**Quando** todos executam simultaneamente
**Então** log final tem 40 eventos
**E** seqs são exatamente 1..40 sem duplicatas ou gaps
**E** prev_hash de cada evento aponta corretamente para anterior

### [CRIT] 8.2 Integridade preservada sob concorrência

**Dado** 40 writes concorrentes concluíram
**Quando** chamo `verify_chain(mode="strict")`
**Então** resultado é `ok=True`
**E** hash chain é íntegro

### [EDGE] 8.3 Lock timeout gera exception apropriada

**Dado** processo A segura lock por 15 segundos (LOCK_TIMEOUT_S=10)
**Quando** processo B chama `append_event`
**Então** processo B levanta `TimeoutError` (ou `LockTimeoutError`)
**E** log não é modificado por B

### [HAPPY] 8.4 Lock libera em exception

**Dado** processo segura lock
**E** exception ocorre durante append
**Quando** contexto do lock termina
**Então** lock é liberado
**E** próxima chamada a `append_event` em outro processo tem sucesso

### [EDGE] 8.5 Event_id é único mesmo em escritas paralelas

**Dado** 100 writes paralelos
**Quando** todos concluem
**Então** todos os `event_id` são únicos
**E** todos seguem o padrão `evt_[A-Z0-9]{26}`

---

## 9. Recovery e crash

### [CRIT] 9.1 verify_and_recover requer confirm=True

**Dado** log corrompido em seq=5
**Quando** chamo `verify_and_recover(from_seq=5, operator="x", confirm=False)`
**Então** `ValueError` é levantada (confirm obrigatório)
**E** log não é modificado

### [CRIT] 9.2 Recovery preserva parte corrompida em arquivo

**Dado** log com 10 eventos, corrupção em seq=7
**Quando** chamo `verify_and_recover(from_seq=7, operator="...", confirm=True)`
**Então** `.orch/log.jsonl` tem apenas eventos 1-6 + `log_recovered`
**E** `.orch/log.jsonl.corrupt.{ts}` contém os eventos 7-10 (originais)
**E** novo evento `log_recovered` é emitido com operator, seq_truncated_from=7

### [HAPPY] 9.3 Startup com log truncado na última linha recupera

**Dado** log com 5 eventos, última linha truncada
**Quando** orchestrator reinicia e chama `verify_chain(strict)`
**Então** verify retorna ok=True (reader ignora truncatura)
**E** orchestrator continua normalmente com seq=5 como último

### [CRIT] 9.4 Startup com corrupção no meio escala

**Dado** log com 10 eventos, corrupção em seq=5
**Quando** orchestrator reinicia e chama `verify_chain(strict)`
**Então** retorna ok=False
**E** orchestrator NÃO continua ciclo normal
**E** emite escalation code=E09 (ou aborta se não consegue emitir no log corrompido)

### [HAPPY] 9.5 Reducer reconstrói estado de snapshot + eventos posteriores

**Dado** snapshot em seq=100 + 20 eventos subsequentes no log
**Quando** chamo `reduce_incremental()`
**Então** estado final é igual ao que seria produzido por `reduce_all()`
**E** snapshot foi usado (eventos 1-100 não foram reprocessados)

### [HAPPY] 9.6 reduce_incremental cai para reduce_all sem snapshot

**Dado** log com 50 eventos e nenhum snapshot
**Quando** chamo `reduce_incremental()`
**Então** retorna estado correto (via reduce_all)
**E** não levanta exception

---

## 10. Escalação e intervenção humana

### [HAPPY] 10.1 escalation pausa fase afetada

**Dado** fase "dev" em active com tasks em execução
**Quando** emito `escalation(code=E04, evidence=[...])`
**Então** `state.run_status == "escalated"`
**E** `state.escalation` contém code, evidence

### [HAPPY] 10.2 human_response com action=resume_phase retoma

**Dado** fase "dev" pausada por escalation seq=50
**Quando** emito `human_response(escalation_seq=50, action="resume_phase", operator="x")`
**E** depois emito `phase_resumed(phase="dev", paused_seq=..., human_response_seq=...)`
**Então** `state.phases["dev"].status == "active"`
**E** `state.run_status == "active"`

### [CRIT] 10.3 Dependency cycle detectado gera escalation E03

**Dado** task `t_001, deps=[t_002]` e `t_002, deps=[t_001]` (ciclo)
**Quando** reducer processa
**Então** deadlock detection identifica ciclo
**E** `escalation(code=E03_dependency_cycle, evidence=[...])` é emitido

### [CRIT] 10.4 Deadlock sem ação legal gera escalation E06

**Dado** todas as tasks em pending (sem ready nem running)
**E** nenhuma dep pode ser satisfeita (todas dependem de tasks não-existentes ou em DLQ)
**Quando** orchestrator processa ciclo
**Então** detecta deadlock
**E** emite `escalation(code=E06_deadlock)`

### [HAPPY] 10.5 Critical task em DLQ gera escalation E04

**Dado** task `t_001, tier="critical"` em DLQ
**Quando** reducer processa ou orchestrator inspeciona
**Então** `escalation(code=E04_critical_task_dlq, evidence=[...])` é emitido
**E** fase afetada é pausada

### [HAPPY] 10.6 human_response cancel_task move task para cancelled

**Dado** task `t_001` em DLQ, escalation ativa
**Quando** operator emite `human_response(action="cancel_task", affected_task_ids=["t_001"])`
**Então** `t_001.status` vira `cancelled` (terminal)
**E** outras tasks dependentes são reavaliadas

---

## 11. Workflow end-to-end (simulação sem LLM)

### [CRIT] 11.1 Workflow 3-tasks single-phase completa

**Dado** orchestrator inicializado, workflow default single-phase
**Quando** simulo eventos manualmente:
1. `phase_declared`, `phase_entered(default)`
2. Cria t_001 (sem deps)
3. `task_claimed(t_001)` → `task_completed(t_001)`
4. Cria t_002 (deps=[t_001])
5. `task_claimed(t_002)` → `task_completed(t_002)`
6. Cria t_003 (deps=[t_001, t_002])
7. `task_claimed(t_003)` → `task_completed(t_003)`
8. `phase_exit_approved` → `phase_transitioned`

**Então** estado final tem:
- 3 tasks em `completed`
- `state.current_phase` corresponde (pode ser null se final)
- `run_status == "active"` ou completed equivalente

### [CRIT] 11.2 Workflow multi-fase SDD → Dev completa

**Dado** workflow com 2 fases: sdd e dev
**Quando** simulo eventos completos para ambas as fases
**Então** final:
- Fase sdd em `completed`
- Fase dev em `completed`
- Todas as tasks em `completed`
- `phase_transitioned(sdd → dev)` e depois `phase_transitioned(dev → null)` no log

### [HAPPY] 11.3 Retry em workflow recupera task transiente

**Dado** workflow com task t_001 que vai falhar uma vez e depois suceder
**Quando** simulo:
1. task_claimed, task_failed(retryable=true, attempts=1)
2. task_scheduled_retry
3. task_retried(attempts=2), task_claimed, task_completed

**Então** task final em `completed`, `attempts=2`

### [CRIT] 11.4 Cascade DLQ afeta dependentes

**Dado** t_001 (deps=[]) e t_002 (deps=[t_001])
**Quando** t_001 vai para DLQ
**Então** orchestrator detecta: t_002 não pode progredir
**E** emite `task_dlq(t_002, reason="cascade_from_dep", dep_task_id="t_001")`
**E** ambos ficam em `dlq`

---

## 12. Configuração

### [HAPPY] 12.1 Config ausente usa defaults

**Dado** `.orch/config.json` não existe
**Quando** chamo `load_config()`
**Então** retorna config completo com defaults
**E** `retry_policy.defaults_by_tier.standard.max_attempts == 3`

### [HAPPY] 12.2 Config parcial é mesclado com defaults

**Dado** `.orch/config.json` contendo apenas `{"retry_policy": {"defaults_by_tier": {"standard": {"max_attempts": 5}}}}`
**Quando** chamo `load_config()`
**Então** `retry_policy.defaults_by_tier.standard.max_attempts == 5`
**E** outros campos (cap_s, etc.) têm valores default

### [CRIT] 12.3 Config inválido levanta ConfigError

**Dado** `.orch/config.json` com JSON malformado
**Quando** chamo `load_config()`
**Então** `ConfigError` é levantada
**E** mensagem identifica o arquivo

### [EDGE] 12.4 Workflow customizado é carregado

**Dado** config com workflow "bug-fix": ["reproduce", "fix", "verify"]
**Quando** orchestrator inicia com `workflow_type="bug-fix"`
**Então** emite `phase_declared` com essas 3 fases

---

## Como transformar cenários em testes pytest

Para cada cenário acima, estrutura sugerida:

```python
# tests/test_scenarios.py
def test_scenario_1_1_first_event_in_empty_log(temp_orch_dir):
    """[HAPPY] 1.1 Primeiro evento no log vazio"""
    # Given
    assert not (temp_orch_dir / "log.jsonl").exists()

    # When
    event = append_event(
        agent="orchestrator",
        event_type="phase_declared",
        data={"workflow_id": "wf_test", "phases": []}
    )

    # Then
    assert (temp_orch_dir / "log.jsonl").exists()
    assert event.seq == 1
    assert event.prev_hash == "GENESIS"
    assert event.hash == event.compute_hash()
    assert event.event_id.startswith("evt_")


def test_scenario_3_6_illegal_transition_pending_to_running(temp_orch_dir):
    """[CRIT] 3.6 Transição ilegal pending → running levanta"""
    state = OrchState()
    state.tasks["t_001"] = TaskState(
        task_id="t_001",
        phase="dev",
        status=TaskStatus.PENDING.value,
        deps=[],
        tier="standard",
        task_type="impl",
        spec="..."
    )

    event = _build_event("task_claimed", task_id="t_001", ...)

    with pytest.raises(IllegalTransition):
        apply_event(state, event)
```

Cenários `[CRIT]` devem todos passar antes de piloto. `[HAPPY]` e `[EDGE]` podem ser priorizados conforme disponibilidade.

---

## Coverage alvo

| Categoria | Cenários | Cobertura mínima |
|---|---|---|
| [CRIT] | ~25 | 100% antes de piloto |
| [HAPPY] | ~35 | 90% antes de piloto |
| [EDGE] | ~15 | 70% antes de piloto |
| **Total** | **~75** | **~90%** |

Este documento lista ~70 cenários nomeados. Com variações (diferentes valores de input), suite pytest chega a ~150-200 casos de teste. Roda em < 30 segundos com paralelização.

---

## Checklist para implementador

Ao terminar implementação de cada módulo, verifique que os cenários relevantes passam:

- [ ] `orch_core.py` event schema → seção 1
- [ ] `verify.py` → seção 2
- [ ] Reducer → seção 3
- [ ] `backoff_seconds`, circuit breaker → seção 4
- [ ] Phase state machine → seção 5
- [ ] `externalize_blob`, `load_blob_data` → seção 6
- [ ] Hooks → seção 7
- [ ] `LogLock` e concorrência → seção 8
- [ ] `verify_and_recover`, `reduce_incremental` → seção 9
- [ ] Escalações e human response → seção 10
- [ ] Fluxos E2E → seção 11
- [ ] `load_config` → seção 12
