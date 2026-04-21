# Implementation Plan — Orquestrador Multi-Fase

> Decomposição da arquitetura em ~45 tasks implementáveis em sessões de Claude Code.
> Cada task: 1-4 horas, escopo claro, critério objetivo de done.
> Ordem respeita dependências técnicas — não pular etapas.

---

## Como usar este plano

Para cada task você executa o seguinte ciclo:

1. **Abrir sessão Claude Code** (nova janela, contexto limpo)
2. **Fornecer contexto enxuto**: `architecture.md` resumido + specs relevantes + task description
3. **Executar a task**: Claude Code implementa e testa
4. **Validar**: rodar testes, revisar código, mergear
5. **Atualizar estado**: marcar task como done, seguir para próxima

**Regra de ouro**: nunca comece uma task sem ter terminado TODAS as suas dependências. Ordem importa.

---

## Sumário das fases

| Fase | Tasks | Esforço | Entregável |
|---|---|---|---|
| 0 | Setup | 2 | Projeto inicializado, skeleton |
| 1 | Fundação | 8 | orch_core.py funcional |
| 2 | Skills básicas | 6 | CLI scripts funcionais |
| 3 | Orquestrador single-phase | 7 | Workflow single-phase completo |
| 4 | Robustez | 6 | Retry, circuit breaker, preflight |
| 5 | Fases | 7 | Workflow multi-fase completo |
| 6 | Workers de produção | 5 | 4 workers canônicos prontos |
| 7 | Hardening | 4 | Testes finais, docs, rollout |
| **Total** | **45** | **~6-8 semanas-pessoa** | **Sistema pronto para piloto** |

---

## Dependências entre fases

```
Fase 0 (setup)
    ↓
Fase 1 (fundação — orch_core.py)
    ↓
Fase 2 (skills básicas)  ──┬──> Fase 3 (orquestrador single-phase)
                           │          ↓
                           └──> Fase 4 (robustez) ──┐
                                                    ↓
                                      Fase 5 (fases multi)
                                              ↓
                                      Fase 6 (workers)
                                              ↓
                                      Fase 7 (hardening)
```

**Paralelizável**: Fases 4, 5 parcialmente paralelas após Fase 3. Fase 6 pode começar após Fase 5 ter 2-3 primeiras tasks.

---

## FASE 0: Setup (2 tasks)

### Task 0.1: Inicializar estrutura do projeto

**Objetivo**: criar esqueleto de diretórios e arquivos base.

**Contexto necessário**:
- `architecture.md` §20 (estrutura de arquivos)

**Deliverables**:
```
projeto/
├── CLAUDE.md                  # instruções básicas para Claude Code
├── .gitignore                 # ignora .orch/, __pycache__, etc.
├── README.md                  # readme inicial
├── pytest.ini                 # config pytest
├── .claude/
│   ├── settings.json          # configura permissões
│   ├── agents/                # (vazio por enquanto)
│   ├── skills/                # (vazio por enquanto)
│   ├── hooks/                 # (vazio por enquanto)
│   ├── scripts/               # (vazio por enquanto)
│   └── lib/
│       └── __init__.py        # package marker
└── tests/
    ├── __init__.py
    └── conftest.py            # fixtures pytest compartilhadas
```

**Critérios de aceite**:
- [ ] Estrutura criada conforme architecture §20
- [ ] `pytest` roda (mesmo sem testes) retornando "no tests ran"
- [ ] `CLAUDE.md` tem pelo menos: descrição do projeto, stack, onde docs ficam
- [ ] `.gitignore` inclui `.orch/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`

**Esforço**: 1h
**Prioridade**: Crítica (bloqueia todo o resto)
**Depende de**: nenhuma

---

### Task 0.2: Configurar ambiente Python e ferramentas de qualidade

**Objetivo**: garantir que desenvolvimento tem ferramentas adequadas.

**Contexto necessário**: decisão do time sobre tools.

**Deliverables**:
- `requirements-dev.txt` ou `pyproject.toml` com: `pytest`, `pytest-cov`, `mypy` (opcional), `ruff` (opcional)
- `.github/workflows/test.yml` (se CI for GitHub Actions)
- Documentação em README de como rodar testes

**Critérios de aceite**:
- [ ] `pip install -r requirements-dev.txt` funciona em Python 3.10+
- [ ] `pytest --cov=.claude/lib` executa (mesmo sem código)
- [ ] Linting opcional configurado (ruff ou similar)
- [ ] README descreve setup em ≤ 10 linhas

**Esforço**: 1h
**Prioridade**: Alta (não bloqueia código, mas bloqueia CI)
**Depende de**: 0.1

---

## FASE 1: Fundação — `orch_core.py` (8 tasks)

Ordem rigorosa: cada task estabelece base para a seguinte.

### Task 1.1: Implementar Event dataclass e enums

**Objetivo**: a menor unidade do sistema, testada isoladamente.

**Contexto necessário**:
- `specs/orch_core_api.md` §2.1 (Event), §3 (Enums)
- `specs/event-schema.md` §1 (envelope)
- `TEST_SCENARIOS.md` seção 1.1, 2.5, 2.6

**Deliverables**:
- `.claude/lib/orch_core.py` com:
  - `Event` dataclass completo
  - `EventType`, `TaskStatus`, `PhaseStatus`, `Tier` enums
  - `event.to_dict()`, `Event.from_dict()`, `canonical_json()`, `compute_hash()`
  - helpers `new_event_id()`, `now_iso()`, `sha256_hex()`, `canonical_json()`
- `tests/test_event.py` cobrindo cenários 1.1, 2.5, 2.6

**Critérios de aceite**:
- [ ] `Event.to_dict()` e `Event.from_dict()` são inversos (round-trip igual)
- [ ] `canonical_json` é determinística (mesmo evento → mesma string)
- [ ] `compute_hash` não inclui o próprio campo `hash`
- [ ] Hash é estável entre chamadas (mesmo evento → mesmo hash)
- [ ] `EventType.is_worker_emittable` retorna True apenas para 3 tipos (progress/completed/failed)
- [ ] `Tier.default_max_attempts` retorna 5/3/1 para critical/standard/bulk
- [ ] Todos os testes passam, cobertura > 95%

**Esforço**: 3h
**Prioridade**: Crítica (bloqueia Fase 1 inteira)
**Depende de**: 0.1

---

### Task 1.2: Implementar constantes, paths, LogLock e ensure_dirs

**Objetivo**: I/O primitivo com lock POSIX.

**Contexto necessário**:
- `specs/orch_core_api.md` §1 (constantes), §10 (LogLock)
- `TEST_SCENARIOS.md` seção 8.3, 8.4

**Deliverables**:
- Em `orch_core.py`:
  - Constantes: `ORCH_DIR`, `LOG_PATH`, `LOCK_PATH`, `STATE_DIR`, etc.
  - `MAX_INLINE_PAYLOAD`, `LOCK_TIMEOUT_S`, `SNAPSHOT_EVERY_N_EVENTS`
  - `ensure_dirs()`
  - `LogLock` context manager com timeout
- `tests/test_locking.py` com cenários 8.3, 8.4

**Critérios de aceite**:
- [ ] `ensure_dirs()` é idempotente (rodar 2x não falha)
- [ ] `LogLock` adquire e libera corretamente em happy path
- [ ] `LogLock` libera em exception (usa `__exit__`)
- [ ] Timeout de 10s é respeitado, `TimeoutError` ou `LockTimeoutError` levantada
- [ ] Paths são configuráveis via variáveis de módulo (monkeypatch funciona)

**Esforço**: 2h
**Prioridade**: Crítica (bloqueia append_event)
**Depende de**: 1.1

---

### Task 1.3: Implementar append_event com hash chain

**Objetivo**: o coração do sistema — append atômico com integridade.

**Contexto necessário**:
- `specs/orch_core_api.md` §4.1 (append_event)
- `specs/event-schema.md` §1 (envelope), §2-4 (todos tipos)
- `TEST_SCENARIOS.md` seção 1 completa, 2.1-2.3

**Deliverables**:
- Em `orch_core.py`:
  - `append_event(agent, event_type, task_id, attempt, data) → Event`
  - Validação básica de event_type
  - Locking, leitura de último evento, computação de seq e prev_hash
  - Hash computation, append + fsync
  - Exceções: `EventValidationError`, `LockTimeoutError`, `OrchError`, `UnknownEventType`
- `tests/test_append.py` cobrindo cenários 1.1-1.4, 1.8, 1.9

**Critérios de aceite**:
- [ ] Primeiro evento tem `seq=1`, `prev_hash="GENESIS"`
- [ ] Events sequenciais têm seq monotônico e prev_hash encadeado
- [ ] event_type desconhecido levanta `UnknownEventType`
- [ ] Linha escrita é serialização correta (JSON válido, termina em `\n`)
- [ ] Arquivo usa mode `ab` (append binary), `fsync` após write
- [ ] Lock liberado mesmo em exception no meio
- [ ] Event_id único entre chamadas (sem colisão em 100 chamadas rápidas)

**Esforço**: 4h
**Prioridade**: Crítica
**Depende de**: 1.1, 1.2

---

### Task 1.4: Implementar read_events, last_event, read_events_filtered

**Objetivo**: leitura com tolerância a corrupção da última linha.

**Contexto necessário**:
- `specs/orch_core_api.md` §4.2, §4.3, §4.4
- `TEST_SCENARIOS.md` seção 1.3-1.7

**Deliverables**:
- Em `orch_core.py`:
  - `read_events(from_seq=0) -> Iterator[Event]`
  - `last_event() -> Event | None`
  - `read_events_filtered(from_seq, task_id, event_type, phase, tail)`
  - `CorruptedLogError`
- `tests/test_read.py` cobrindo cenários 1.3-1.7

**Critérios de aceite**:
- [ ] `read_events()` em log vazio retorna iterator vazio
- [ ] `last_event()` em log vazio retorna `None`
- [ ] `from_seq` filtra corretamente
- [ ] Última linha truncada (JSON incompleto) é ignorada sem exception
- [ ] JSON inválido no **meio** do log levanta `CorruptedLogError`
- [ ] `read_events_filtered` aplica AND entre filtros
- [ ] `tail=N` retorna últimos N após filtros

**Esforço**: 2-3h
**Prioridade**: Crítica
**Depende de**: 1.3

---

### Task 1.5: Implementar verify_chain (modos strict e audit)

**Objetivo**: detecção de corrupção.

**Contexto necessário**:
- `specs/orch_core_api.md` §5.1
- `TEST_SCENARIOS.md` seção 2 completa

**Deliverables**:
- Em `orch_core.py`:
  - `verify_chain(mode="strict") -> VerifyResult`
  - `VerifyResult` dataclass
  - Apenas modos `strict` e `audit` nesta task (recover em task separada)
- `tests/test_verify.py` cobrindo cenários 2.1-2.4

**Critérios de aceite**:
- [ ] Log vazio retorna `ok=True`
- [ ] Log íntegro de N eventos: `ok=True`, `events_verified=N`
- [ ] Adulteração de `data` gera `ok=False`, `first_error_seq` correto
- [ ] Reordenação de eventos detecta prev_hash quebrado
- [ ] Modo `audit` reporta todos os erros sem parar no primeiro
- [ ] Nenhum modo modifica o log

**Esforço**: 2-3h
**Prioridade**: Crítica
**Depende de**: 1.3, 1.4

---

### Task 1.6: Implementar externalize_blob e load_blob_data

**Objetivo**: suporte a payloads grandes com integridade.

**Contexto necessário**:
- `specs/orch_core_api.md` §6
- `specs/event-schema.md` §5.1
- `TEST_SCENARIOS.md` seção 6 completa

**Deliverables**:
- Em `orch_core.py`:
  - `externalize_blob(data, event_id) -> tuple[str, str]`
  - `load_blob_data(event) -> dict`
  - `is_blob_ref(data) -> bool`
  - `BlobIntegrityError`, `BlobNotFoundError`
- Modificar `append_event` para usar externalização quando payload > MAX_INLINE_PAYLOAD
- `tests/test_blobs.py` cobrindo cenários 6.1-6.7

**Critérios de aceite**:
- [ ] Payload < 3500 bytes: inline, nenhum blob criado
- [ ] Payload > 3500 bytes: blob criado, evento tem `_blob_ref, _size, _blob_hash`
- [ ] `load_blob_data` em blob adulterado levanta `BlobIntegrityError`
- [ ] `load_blob_data` em evento inline retorna data diretamente (sem I/O)
- [ ] Blob ausente levanta `BlobNotFoundError` (ou `FileNotFoundError`)
- [ ] `is_blob_ref` retorna True somente se todas as 3 chaves presentes

**Esforço**: 3h
**Prioridade**: Crítica (previne corrupção em eventos grandes)
**Depende de**: 1.3

---

### Task 1.7: Implementar reducer (apply_event + transições)

**Objetivo**: a máquina de estados em Python.

**Contexto necessário**:
- `specs/orch_core_api.md` §7 (reducer), §2.2-2.4 (TaskState, PhaseState, OrchState)
- `architecture.md` §8 (máquinas de estado)
- `TEST_SCENARIOS.md` seção 3 completa + seção 5 (fases)

**Deliverables**:
- Em `orch_core.py`:
  - `TaskState`, `PhaseState`, `OrchState` dataclasses
  - `apply_event(state, event) -> OrchState`
  - Handler por event_type (dispatcher interno)
  - Lógica de promoção pending→ready baseada em deps e fase ativa
  - `IllegalTransition` exception
  - `reduce_all() -> OrchState`
- `tests/test_reducer.py` cobrindo seção 3 e partes da seção 5

**Critérios de aceite**:
- [ ] `task_created` → task em `pending` (ou `ready` se deps=[] e fase ativa)
- [ ] Todas as 8 transições válidas de task funcionam
- [ ] Transições ilegais (pending→running direto, completed→qualquer) levantam `IllegalTransition`
- [ ] `retryable=false` + `task_dlq` → status dlq
- [ ] `retryable=true, attempts<max` + `task_scheduled_retry` → status scheduled
- [ ] `task_retried` → volta a pending ou ready conforme deps e fase
- [ ] Reducer é determinístico: mesmo log → mesmo estado (rodar 2x compara igual)

**Esforço**: 4h
**Prioridade**: Crítica
**Depende de**: 1.1, 1.4

---

### Task 1.8: Implementar snapshots e reduce_incremental

**Objetivo**: otimização para logs grandes.

**Contexto necessário**:
- `specs/orch_core_api.md` §7.3, §8

**Deliverables**:
- Em `orch_core.py`:
  - `save_snapshot(state) -> Path`
  - `latest_snapshot() -> tuple[OrchState, int]`
  - `reduce_incremental() -> OrchState`
  - `should_snapshot(state) -> bool`
- `tests/test_snapshots.py`

**Critérios de aceite**:
- [ ] `save_snapshot` cria arquivo `snapshot-NNNNNNNN.json` (8 digits zero-padded)
- [ ] `latest_snapshot` retorna snapshot mais recente por seq
- [ ] Sem snapshots: `latest_snapshot()` retorna `(OrchState(), 0)`
- [ ] `reduce_incremental` usa snapshot + eventos posteriores, produz mesmo resultado que `reduce_all`
- [ ] `should_snapshot` retorna True a cada 100 eventos

**Esforço**: 2h
**Prioridade**: Alta (otimização, não crítica)
**Depende de**: 1.7

---

## FASE 2: Skills básicas (6 tasks)

Scripts CLI que workers e orquestrador usam.

### Task 2.1: Skill orch-log com append.py

**Objetivo**: CLI para orquestrador emitir eventos.

**Contexto necessário**:
- `architecture.md` §9.4.1
- Task 1.3 (append_event Python API)

**Deliverables**:
- `.claude/skills/orch-log/SKILL.md`
- `.claude/skills/orch-log/scripts/append.py`:
  - CLI com argparse: `--agent`, `--event-type`, `--task-id`, `--attempt`, `--data` (JSON string)
  - Chama `orch_core.append_event()`
  - Output: JSON do evento criado em stdout
  - Exit code: 0 sucesso, 1 erro
- `tests/test_append_cli.py`: invoca via subprocess

**Critérios de aceite**:
- [ ] `python3 append.py --agent orchestrator --event-type task_created --task-id t_001 --data '{"phase":"dev","tier":"standard","type":"impl","spec":"...","deps":[]}'` funciona
- [ ] Exit code != 0 para event_type inválido, JSON inválido
- [ ] SKILL.md documenta uso e parâmetros
- [ ] `allowed-tools: Bash(python3 *), Read`

**Esforço**: 2h
**Prioridade**: Crítica
**Depende de**: 1.3

---

### Task 2.2: Skill orch-log com read.py e verify.py

**Objetivo**: CLI de leitura e verificação.

**Contexto necessário**:
- Tasks 1.4, 1.5

**Deliverables**:
- `.claude/skills/orch-log/scripts/read.py`:
  - CLI: `--from-seq`, `--tail N`, `--task-id`, `--event-type`, `--phase`
  - Output: uma linha JSON por evento
- `.claude/skills/orch-log/scripts/verify.py`:
  - CLI: `--mode strict|audit`
  - Output: JSON com resultado; exit code reflete ok
- Testes subprocess para ambos

**Critérios de aceite**:
- [ ] `read.py` sem args lista todos os eventos
- [ ] `read.py --tail 5` retorna últimos 5
- [ ] Múltiplos filtros são aplicados em AND
- [ ] `verify.py --mode strict` retorna exit 0 em log íntegro, != 0 em corrupção
- [ ] `verify.py --mode audit` sempre retorna exit 0 (reporta sem modificar)

**Esforço**: 2h
**Prioridade**: Crítica
**Depende de**: 1.4, 1.5

---

### Task 2.3: Skill orch-state com reduce.py, summary.py, current_phase.py

**Objetivo**: CLI para inspecionar estado.

**Contexto necessário**:
- Tasks 1.7, 1.8

**Deliverables**:
- `.claude/skills/orch-state/SKILL.md`
- `scripts/reduce.py`: imprime JSON do OrchState completo
- `scripts/summary.py`: resumo legível (contagens por status, fase, etc.)
- `scripts/current_phase.py`: imprime `{"current_phase": ..., "status": ...}`
- Testes subprocess

**Critérios de aceite**:
- [ ] `reduce.py` em log vazio imprime state vazio
- [ ] `reduce.py` após workflow imprime state consistente com eventos
- [ ] `summary.py` é human-readable (não JSON puro)
- [ ] `current_phase.py` retorna null em log sem phase_entered
- [ ] `current_phase.py` retorna fase corrente correta com eventos de fase

**Esforço**: 2h
**Prioridade**: Crítica (orquestrador usa current_phase.py)
**Depende de**: 1.7, 1.8, 2.1

---

### Task 2.4: Skill orch-state com snapshot.py

**Objetivo**: CLI para persistir snapshot.

**Contexto necessário**: Task 1.8

**Deliverables**:
- `scripts/snapshot.py`:
  - Computa state, salva snapshot, emite evento `snapshot`
  - CLI: `--force` para ignorar should_snapshot
- Teste subprocess

**Critérios de aceite**:
- [ ] Snapshot é salvo em disco
- [ ] Evento `snapshot` é emitido no log
- [ ] `--force` ignora threshold de 100 eventos
- [ ] Sem `--force`, só snapshota se ultrapassou threshold

**Esforço**: 1h
**Prioridade**: Alta
**Depende de**: 1.8, 2.1

---

### Task 2.5: Skill orch-report com emit.py (restrito)

**Objetivo**: CLI para workers emitirem eventos (com guard-rail).

**Contexto necessário**:
- `architecture.md` §9.4.3
- `TEST_SCENARIOS.md` 7.5, 7.6

**Deliverables**:
- `.claude/skills/orch-report/SKILL.md`
- `scripts/emit.py`:
  - CLI: `--kind progress|completed|failed`, `--task-id`, `--attempt`, outros campos
  - Mapeia kind para event_type e rejeita qualquer outro
  - Força `agent = $ORCH_WORKER_ID` (env var)
- Teste subprocess para cada kind válido + rejeição de kinds inválidos

**Critérios de aceite**:
- [ ] `emit.py --kind progress` emite `task_progress`
- [ ] `emit.py --kind completed --artifacts file1.py` emite `task_completed`
- [ ] `emit.py --kind failed --retryable false --reason x` emite `task_failed`
- [ ] Kind desconhecido (ex: `claimed`, `dlq`) retorna exit != 0 com erro claro
- [ ] Agent é setado a partir de `ORCH_WORKER_ID` env var, falha se ausente

**Esforço**: 2h
**Prioridade**: Crítica (segurança — guard-rail)
**Depende de**: 2.1

---

### Task 2.6: Hook on_subagent_stop.py

**Objetivo**: detectar workers silenciosos.

**Contexto necessário**:
- `architecture.md` §9.5.1
- `TEST_SCENARIOS.md` seção 7.1-7.3

**Deliverables**:
- `.claude/hooks/on_subagent_stop.py`
- Atualização de `.claude/settings.json` para registrar hook
- `tests/test_hooks.py` cobrindo cenários 7.1-7.3

**Critérios de aceite**:
- [ ] Sem env vars ORCH_*: hook é no-op, exit 0
- [ ] Com env vars + task sem terminal: sintetiza `task_failed` com `synthesized_by`
- [ ] Com env vars + task com terminal: hook é no-op (não duplica)
- [ ] Hook lê stdin (Claude Code passa JSON); tolerante a stdin vazio/inválido

**Esforço**: 2h
**Prioridade**: Crítica (robustez fundamental)
**Depende de**: 2.5

---

## FASE 3: Orquestrador single-phase (7 tasks)

Sistema funcionando em modo simples (sem fases) antes de adicionar complexidade.

### Task 3.1: Criar orchestrator.md mínimo (single-phase)

**Objetivo**: sub-agent orquestrador funcional para workflow simples.

**Contexto necessário**:
- `architecture.md` §9.1
- Prompt template inicial

**Deliverables**:
- `.claude/agents/orchestrator.md`:
  - Frontmatter: name, description, tools, model=opus, skills
  - Prompt com ciclo de operação básico:
    1. Verify chain
    2. Reduce state
    3. Decide próxima ação
    4. Emit events
    5. Report
  - **Ainda não tem fases** — tudo roda como "default phase"
- Teste manual: invocar orchestrator e verificar comportamento

**Critérios de aceite**:
- [ ] Orchestrator responde quando invocado
- [ ] Lê log, não quebra se vazio
- [ ] Produz relatório estruturado
- [ ] Não tenta ainda spawnar workers reais (comportamento inicial)

**Esforço**: 3h
**Prioridade**: Crítica
**Depende de**: 2.1, 2.2, 2.3

---

### Task 3.2: Criar worker mínimo "test-worker" (dummy)

**Objetivo**: worker mais simples possível para validar end-to-end.

**Deliverables**:
- `.claude/agents/test-worker.md`:
  - Frontmatter mínimo
  - Carrega skill orch-report
  - Prompt: "emita progress, crie arquivo de teste, emita completed"
- Teste manual: orchestrator spawna test-worker, verifica eventos no log

**Critérios de aceite**:
- [ ] Worker é invocável pela Agent tool
- [ ] Worker emite `task_progress` ao começar
- [ ] Worker cria arquivo simples (teste)
- [ ] Worker emite `task_completed` com artifacts
- [ ] Hook on_subagent_stop valida que terminal foi emitido

**Esforço**: 2h
**Prioridade**: Crítica
**Depende de**: 2.5, 2.6

---

### Task 3.3: Orchestrator spawna worker e processa resultado

**Objetivo**: ciclo completo task → worker → completed.

**Contexto necessário**:
- architecture.md §14.2 (fluxo execução de task)

**Deliverables**:
- Atualizar `orchestrator.md`:
  - Lógica de seleção de task ready
  - Emit `task_claimed` antes de spawnar
  - Invocar Agent tool com env vars ORCH_*
  - Processar terminal event no próximo ciclo
- Teste E2E: criar task, verificar que orchestrator claim + worker completa

**Critérios de aceite**:
- [ ] Task em `ready` é detectada e claimed
- [ ] Worker recebe env vars corretas
- [ ] Após worker completar, task em `completed`
- [ ] Workflow de 1 task vai de pending → completed sem intervenção

**Esforço**: 4h
**Prioridade**: Crítica
**Depende de**: 3.1, 3.2

---

### Task 3.4: Suporte a múltiplas tasks e deps

**Objetivo**: orquestrador respeita grafo de deps.

**Deliverables**:
- Atualizar orchestrator.md com:
  - Promoção pending → ready após dep completar
  - Spawn concorrente de múltiplas tasks ready (respeitando limite)
- Teste E2E: 3 tasks com deps, verifica execução em ordem correta

**Critérios de aceite**:
- [ ] Task com deps só fica ready após todas completarem
- [ ] Múltiplas ready são spawadas em paralelo (até limite de 2-3 concurrent)
- [ ] Workflow de 3 tasks com deps completa E2E

**Esforço**: 3h
**Prioridade**: Crítica
**Depende de**: 3.3

---

### Task 3.5: Detecção de stale tasks

**Objetivo**: orquestrador sintetiza failed para tasks paradas.

**Contexto necessário**:
- `TEST_SCENARIOS.md` 7.4
- `architecture.md` §14.4

**Deliverables**:
- Função auxiliar em `orch_core.py`: `stale_tasks(state, now_iso)`
- Lógica no orchestrator.md: a cada ciclo, checa stale e emite `task_failed(synthesized_by="stale_detection")`
- Teste: simular task claimed há mais de stale_seconds sem terminal

**Critérios de aceite**:
- [ ] Task em running há mais que `tier.stale_seconds` é detectada
- [ ] Orchestrator emite task_failed com synthesized_by e retryable=true
- [ ] Task com eventos progress recentes NÃO é considerada stale

**Esforço**: 2h
**Prioridade**: Crítica
**Depende de**: 3.4

---

### Task 3.6: DLQ cascade para tasks com dep falhada

**Objetivo**: tasks com deps em DLQ também vão para DLQ.

**Contexto necessário**: `TEST_SCENARIOS.md` 11.4

**Deliverables**:
- Lógica no orchestrator.md:
  - Detectar tasks com dep em DLQ
  - Emit `task_dlq(reason="cascade_from_dep", dep_task_id=...)` para dependentes
- Teste: workflow onde t_001 vai para DLQ, verificar cascade para t_002

**Critérios de aceite**:
- [ ] Quando dep vai para DLQ, dependente também é marcada DLQ (não fica pending para sempre)
- [ ] Cadeia de 3+ tasks em cascade funciona
- [ ] Cascade só ocorre para deps em DLQ, não em failed transient

**Esforço**: 2h
**Prioridade**: Alta
**Depende de**: 3.5

---

### Task 3.7: Snapshot periódico e relatório final

**Objetivo**: orquestrador fecha ciclo com snapshot e resumo.

**Deliverables**:
- Orchestrator.md: snapshot a cada 100 eventos (usa should_snapshot)
- Hook `on_stop.py` para agregar métricas ao fim da sessão
- Output final estruturado

**Critérios de aceite**:
- [ ] Snapshot é emitido automaticamente a cada 100 eventos
- [ ] `on_stop.py` gera `.orch/metrics/current.json`
- [ ] Metrics incluem contagens por status, total events, escalations

**Esforço**: 2h
**Prioridade**: Alta
**Depende de**: 3.4, 2.4

---

## FASE 4: Robustez (6 tasks)

Retry, circuit breaker, preflight. Pode ser parcialmente paralelo com Fase 5.

### Task 4.1: Implementar backoff_seconds e load_retry_policy

**Contexto necessário**: `specs/orch_core_api.md` §9, `TEST_SCENARIOS.md` §4

**Deliverables**:
- Em `orch_core.py`:
  - `backoff_seconds(attempts, base, cap)` com jitter
  - `load_retry_policy(tier, task_type)` com override
  - `should_retry(task, policy)`
  - `RetryPolicy` dataclass
- Configuração default + `load_config()`
- `tests/test_retry.py`

**Critérios de aceite**:
- [ ] Backoff é exponencial com jitter ±20%
- [ ] Capped em cap_s × 1.2
- [ ] Policy por tier funciona
- [ ] Override por task_type tem precedência
- [ ] `should_retry=false` para retryable=false
- [ ] `should_retry=false` para attempts >= max

**Esforço**: 2h
**Prioridade**: Crítica (sem isso, falhas viram loop)
**Depende de**: 1.7

---

### Task 4.2: Implementar task_scheduled_retry e task_retried no orquestrador

**Deliverables**:
- Lógica no orchestrator.md:
  - Ao ver `task_failed(retryable=true, attempts<max)`: emit `task_scheduled_retry`
  - Ao ver `task_failed(retryable=false)` ou attempts>=max: emit `task_dlq`
  - Scheduled tasks: verificar `next_retry_at`, emitir `task_retried` quando expira
- Reducer: lidar com novos eventos
- Testes: cenários 3.10, 3.11, 4.5, 4.6

**Critérios de aceite**:
- [ ] Falha retryable com attempts < max gera task_scheduled_retry
- [ ] Falha retryable com attempts >= max gera task_dlq
- [ ] Falha não-retryable gera task_dlq imediato
- [ ] Task em scheduled vira pending após backoff expirar
- [ ] Novo attempt começa com número correto (anterior+1)

**Esforço**: 3h
**Prioridade**: Crítica
**Depende de**: 4.1, 3.3

---

### Task 4.3: Implementar circuit breaker

**Contexto**: `TEST_SCENARIOS.md` 4.7-4.9

**Deliverables**:
- Em `orch_core.py`:
  - `evaluate_circuit_state(events, config)` — retorna status e counts
- Orchestrator.md:
  - A cada ciclo, avalia circuit
  - Se threshold atingido: emit `circuit_breaker_tripped`
  - Para spawns quando tripped
- Script `.claude/scripts/circuit_breaker.py` para reset manual
- Testes

**Critérios de aceite**:
- [ ] 50 falhas em 10min disparam circuit
- [ ] 30 falhas em 20min NÃO disparam (fora da janela)
- [ ] Quando tripped, novos spawns são bloqueados
- [ ] Script de reset funciona com `--confirm`

**Esforço**: 3h
**Prioridade**: Alta
**Depende de**: 4.2

---

### Task 4.4: Implementar verify_and_recover

**Contexto**: `specs/orch_core_api.md` §5.2, `TEST_SCENARIOS.md` 9.1-9.4

**Deliverables**:
- Em `orch_core.py`: `verify_and_recover(from_seq, operator, confirm)`
- Atualizar `verify.py` CLI com `--recover --confirm --from-seq --operator`
- Emite evento `log_recovered`
- Move parte removida para `.corrupt.{ts}`
- Testes

**Critérios de aceite**:
- [ ] `confirm=False` levanta ValueError (nunca automático)
- [ ] Parte corrompida salva em `.orch/log.jsonl.corrupt.{ts}`
- [ ] Evento `log_recovered` é emitido com detalhes
- [ ] Após recovery, verify passa em strict

**Esforço**: 3h
**Prioridade**: Alta
**Depende de**: 1.5

---

### Task 4.5: Implementar preflight.py

**Contexto**: `architecture.md` §13

**Deliverables**:
- `.claude/scripts/preflight.py`:
  - Checks locais: python_version, flock_works, filesystem_writable, claude_code_version
  - Checks remotos: invocar Claude Code em projeto temp para testar hooks, env vars, skills
  - Saída JSON estruturada
  - Flag `--quick` para pular checks remotos
- Documentação de execução

**Critérios de aceite**:
- [ ] `--quick` roda em < 5s
- [ ] Full preflight roda em < 60s
- [ ] Cada check retorna `CheckResult(ok, reason)`
- [ ] Saída JSON válida para consumo por CI
- [ ] Simulação de falha de cada check é detectada

**Esforço**: 4h (é a task mais complexa da Fase 4)
**Prioridade**: Alta
**Depende de**: 3.1

---

### Task 4.6: DLQ triage e escalações básicas

**Contexto**: `TEST_SCENARIOS.md` §10

**Deliverables**:
- `.claude/hooks/dlq_triage.py`: classifica tasks em DLQ em buckets
- Orchestrator.md com lógica de escalação:
  - E03 (dependency cycle): usar topological sort para detectar
  - E04 (critical task DLQ)
  - E06 (deadlock)
- Testes de cada cenário

**Critérios de aceite**:
- [ ] dlq_triage classifica em 7 buckets (input_issue, worker_issue, etc.)
- [ ] Ciclo de deps gera escalation E03
- [ ] Task critical em DLQ gera E04 e pausa fase
- [ ] Deadlock (sem ready, sem running, sem scheduled) gera E06

**Esforço**: 3h
**Prioridade**: Alta
**Depende de**: 4.2

---

## FASE 5: Fases (7 tasks)

Adicionar suporte multi-fase ao sistema que já funciona single-phase.

### Task 5.1: Expandir schema para eventos de fase

**Contexto**: `specs/event-schema.md` §3, `specs/orch_core_api.md` §2.3, §3

**Deliverables**:
- Em `orch_core.py`:
  - `PhaseState` dataclass completa
  - `OrchState.current_phase`, `OrchState.phases: dict`
  - `PhaseStatus` enum
  - Adicionar 7 novos event types ao EventType enum
  - Validators para cada novo evento
- Atualizar `append_event` para aceitar novos tipos
- Testes do schema

**Critérios de aceite**:
- [ ] 7 novos event types aceitos por append_event
- [ ] Validação rejeita payloads inválidos (ex: phase_declared sem `phases` array)
- [ ] PhaseState.to_dict/from_dict funcionam

**Esforço**: 2h
**Prioridade**: Crítica
**Depende de**: 1.3, 1.7

---

### Task 5.2: Reducer para eventos de fase

**Contexto**: `TEST_SCENARIOS.md` §5

**Deliverables**:
- Em `apply_event`, handlers para:
  - `phase_declared` → phases em pending
  - `phase_entered` → fase em active, current_phase setado
  - `phase_exit_criterion_met` → adiciona criterion
  - `phase_exit_approved` → fase em exit_approved
  - `phase_transitioned` → fase anterior completed, current_phase=to_phase (ou null)
  - `phase_paused`, `phase_resumed`
- Invariante: uma fase active/exit_approved por vez
- Atualização de promoção pending→ready: considerar fase ativa
- Testes: todos os cenários da seção 5

**Critérios de aceite**:
- [ ] Todas as 7 transições de fase funcionam
- [ ] `phase_entered` com outra fase active levanta IllegalTransition
- [ ] Task em fase pending NÃO é promovida a ready
- [ ] Task em fase active COM deps completas é promovida
- [ ] current_phase é derivado corretamente

**Esforço**: 4h
**Prioridade**: Crítica
**Depende de**: 5.1

---

### Task 5.3: Estrutura padrão de skill phase-{nome}-rules

**Objetivo**: estabelecer convenção + primeiro exemplo.

**Contexto**: `architecture.md` §9.4.4

**Deliverables**:
- Template documentado em `.claude/skills/phase-_example/`:
  - SKILL.md skeleton
  - exit-criteria.json skeleton
  - references/ (vazio)
  - scripts/ com 1 checker de exemplo
- **Primeira fase real**: criar `phase-dev-rules/` (mais análogo ao que já funciona single-phase)
  - SKILL.md
  - exit-criteria.json com critérios (ex: `all_impl_tasks_terminal`)
  - scripts/select_worker.py
  - scripts/check_all_impl_tasks_terminal.py

**Critérios de aceite**:
- [ ] Template tem estrutura completa com comentários explicativos
- [ ] phase-dev-rules/ é funcional (checkers retornam JSON válido)
- [ ] Documentação clara para criar nova fase

**Esforço**: 3h
**Prioridade**: Crítica
**Depende de**: 5.2

---

### Task 5.4: Atualizar orchestrator.md para multi-fase

**Contexto**: `architecture.md` §9 do v4.2 (ciclo de operação v4.2)

**Deliverables**:
- Rewrite substancial do prompt de orchestrator.md:
  - Ciclo: verify → current_phase → load phase skill → decide → emit → transition
  - Lógica de carregamento dinâmico de skill por fase
  - Lógica de avaliação de exit criteria
  - Lógica de transição (emit phase_exit_approved, depois phase_transitioned)
- Compatibilidade: se nenhum phase_declared existir, opera em modo single-phase (default)

**Critérios de aceite**:
- [ ] Orchestrator detecta workflow em config e emit phase_declared
- [ ] Carrega skill phase-{corrente}-rules dinamicamente
- [ ] Avalia checkers de exit criteria, emit phase_exit_criterion_met
- [ ] Quando todos critérios met, emit phase_exit_approved
- [ ] No ciclo seguinte, emit phase_transitioned e phase_entered
- [ ] Workflows single-phase (sem phase_declared) continuam funcionando

**Esforço**: 4h (complexo, mas o pulo principal da v4.2)
**Prioridade**: Crítica
**Depende de**: 5.2, 5.3

---

### Task 5.5: Criar phase-sdd-rules skill

**Deliverables**:
- `.claude/skills/phase-sdd-rules/`:
  - SKILL.md
  - exit-criteria.json com: all_tasks_decomposed, specs_validated, deps_acyclic
  - scripts/decompose.py (simplificado — aceita spec string, retorna lista de tasks)
  - scripts/check_all_tasks_decomposed.py
  - scripts/check_specs_validated.py
  - scripts/check_deps_acyclic.py (usa topological sort)
- references/task-templates.md

**Critérios de aceite**:
- [ ] Checkers retornam JSON `{"criterion": ..., "met": bool, "evidence": ...}`
- [ ] check_deps_acyclic detecta ciclo em grafo
- [ ] decompose.py produz pelo menos tasks para dev e test

**Esforço**: 3h
**Prioridade**: Alta
**Depende de**: 5.3

---

### Task 5.6: Criar phase-review-rules e phase-test-rules skills

**Deliverables**:
- `phase-review-rules/`:
  - exit-criteria.json: all_reviews_completed, no_open_critical_findings
  - scripts de check
- `phase-test-rules/`:
  - exit-criteria.json: all_tests_passing, coverage_target_met (opcional)
  - scripts de check

**Critérios de aceite**:
- [ ] Ambas as skills têm estrutura padrão
- [ ] Checkers funcionam com logs de teste
- [ ] Documentação clara em SKILL.md

**Esforço**: 3h (as duas juntas)
**Prioridade**: Alta
**Depende de**: 5.3

---

### Task 5.7: E2E workflow SDD → Dev → Review → Test

**Objetivo**: validar que multi-fase funciona end-to-end.

**Deliverables**:
- Teste E2E (pode ser pytest com eventos simulados, sem LLM):
  - Cenário 11.2 do TEST_SCENARIOS.md completo
- Smoke test manual com Claude Code: workflow pequeno 4 fases

**Critérios de aceite**:
- [ ] Teste E2E simulado passa
- [ ] Smoke test manual: workflow de 2-3 tasks por fase completa
- [ ] Todas as 4 fases transicionam corretamente
- [ ] Log final tem todos os eventos esperados

**Esforço**: 3h
**Prioridade**: Crítica (gate para Fase 6)
**Depende de**: 5.4, 5.5, 5.6

---

## FASE 6: Workers de produção (5 tasks)

Até aqui, só tínhamos test-worker dummy. Agora, workers reais.

### Task 6.1: Worker code-writer

**Deliverables**:
- `.claude/agents/code-writer.md`:
  - Frontmatter: tools (Read, Write, Edit, Bash, Glob, Grep), model=sonnet
  - Carrega orch-report
  - Prompt: implementa task conforme spec, segue style do projeto, emit completed com artifacts
- Teste manual: spec "criar função X", verificar arquivo criado e evento emitido

**Critérios de aceite**:
- [ ] Worker cria arquivo(s) conforme spec
- [ ] Emit task_progress em pontos importantes
- [ ] Emit task_completed com artifacts sendo paths (não conteúdo)
- [ ] Falhas são tratadas com retryable apropriado

**Esforço**: 3h
**Prioridade**: Crítica
**Depende de**: 5.7

---

### Task 6.2: Worker test-runner

**Deliverables**:
- `.claude/agents/test-runner.md`:
  - Similar ao code-writer, mas especializado em criar/rodar testes
  - Pode escrever testes + executar pytest + retornar sucesso/falha
- Teste manual

**Critérios de aceite**:
- [ ] Worker escreve testes para arquivos listados na spec
- [ ] Executa `pytest` e interpreta output
- [ ] Emit completed com artifacts (testes criados) e metrics (testes passando)
- [ ] Se testes falham, emit failed com retryable=true

**Esforço**: 3h
**Prioridade**: Crítica
**Depende de**: 6.1

---

### Task 6.3: Worker code-reviewer (read-only)

**Deliverables**:
- `.claude/agents/code-reviewer.md`:
  - Tools restritos: Read, Glob, Grep, Bash (só para skill)
  - Model=haiku
  - Prompt: review de arquivos, retorna findings
- Teste manual

**Critérios de aceite**:
- [ ] Worker NÃO pode escrever/editar (tools restritas)
- [ ] Emit completed com findings em `data.summary`
- [ ] Se findings críticos, emit completed com critical_findings para orchestrator decidir

**Esforço**: 2h
**Prioridade**: Alta
**Depende de**: 6.1

---

### Task 6.4: Worker migration-writer (especializado)

**Deliverables**:
- `.claude/agents/migration-writer.md`:
  - Similar a code-writer mas focado em migrations DB
  - Segue convenção de nomenclatura do projeto (ex: `migrations/NNN_descricao.sql`)
- Teste manual

**Critérios de aceite**:
- [ ] Worker cria migration seguindo convenção
- [ ] Artifact path é correto
- [ ] Valida sintaxe SQL antes de emit completed

**Esforço**: 2h
**Prioridade**: Média (depende se projeto usa DB)
**Depende de**: 6.1

---

### Task 6.5: Documentação de workers + template

**Objetivo**: consolidar padrão para adicionar novos workers.

**Deliverables**:
- Documentação em `.claude/agents/README.md`:
  - Como criar novo worker
  - Template base
  - Exemplo de routing em phase-*-rules
- Template em `.claude/agents/_template.md`

**Critérios de aceite**:
- [ ] Documentação cobre os 4 workers existentes como exemplo
- [ ] Template tem placeholders claros
- [ ] Alguém novo consegue adicionar worker em < 30min seguindo a doc

**Esforço**: 1h
**Prioridade**: Alta
**Depende de**: 6.1, 6.2, 6.3

---

## FASE 7: Hardening (4 tasks)

Polish final e rollout.

### Task 7.1: Suite completa de testes automatizados

**Objetivo**: elevar coverage para > 85%.

**Deliverables**:
- Completar todos os cenários [CRIT] de `TEST_SCENARIOS.md`
- Cobertura mínima: orch_core.py > 90%, scripts > 80%
- CI rodando todos os testes em < 60s

**Critérios de aceite**:
- [ ] Todos os [CRIT] do TEST_SCENARIOS.md passam
- [ ] 90% dos [HAPPY] passam
- [ ] Teste de concorrência (40 writes paralelos) passa
- [ ] CI configurado em GitHub Actions (ou equivalente)

**Esforço**: 6-8h (muitos testes para escrever)
**Prioridade**: Crítica (gate para piloto)
**Depende de**: tudo anterior

---

### Task 7.2: Documentação operacional (runbook)

**Deliverables**:
- `docs/RUNBOOK.md`:
  - Procedimentos para incidentes comuns (log corrompido, task travada, circuit tripped)
  - Comandos de inspeção e debug
  - Fluxos de recovery passo-a-passo
  - Quem chamar em que situação
- `docs/TROUBLESHOOTING.md`:
  - FAQ de problemas comuns
  - Soluções conhecidas

**Critérios de aceite**:
- [ ] Runbook cobre 8-10 incidentes comuns
- [ ] Cada procedimento é testado (pelo menos leitura com revisão do time)
- [ ] Troubleshooting tem 15+ entradas

**Esforço**: 4h
**Prioridade**: Alta
**Depende de**: 7.1

---

### Task 7.3: Smoke tests de produção

**Objetivo**: validar em cenário realista antes de usar em projeto real.

**Deliverables**:
- Cenário 1: workflow dev-cycle pequeno (feature simples, 3-5 tasks)
- Cenário 2: workflow bug-fix simples
- Cenário 3: cenário de falha recuperável (worker falha uma vez, retry sucede)
- Cenário 4: cenário de stale (worker silencia, hook detecta)
- Cenário 5: workflow interrompido e retomado

**Critérios de aceite**:
- [ ] Todos os 5 cenários completam E2E
- [ ] Logs são auditáveis (conseguir reconstruir o que aconteceu)
- [ ] Métricas capturadas
- [ ] Nenhuma surpresa não documentada

**Esforço**: 4h
**Prioridade**: Crítica (último gate)
**Depende de**: 7.1

---

### Task 7.4: Preparar rollout e training

**Deliverables**:
- Training doc para o time (como usar o sistema)
- Checklist de rollout (em qual projeto começar, métricas a monitorar)
- Pilot plan: projeto alvo, escopo inicial, critérios de sucesso
- Kick-off meeting preparado

**Critérios de aceite**:
- [ ] Documento de training tem exemplos concretos
- [ ] Rollout checklist é objetivo
- [ ] Pilot plan tem fase de avaliação (2-4 semanas) + critérios go/no-go

**Esforço**: 3h
**Prioridade**: Alta
**Depende de**: 7.3

---

## Estratégia de execução

### Sessões de Claude Code por task

Cada task deve ser uma sessão nova do Claude Code. Estrutura sugerida de prompt:

```
# Task X.Y: <nome>

## Contexto do projeto
<incluir BRIEFING.md se existir, ou 100 linhas de contexto>

## Documentos de referência
- architecture.md seções <específicas>
- specs/<arquivo>.md
- TEST_SCENARIOS.md seção <relevante>

## O que esta sessão deve entregar
<copy from this plan>

## Critérios de aceite
<copy from this plan>

## Restrições
- Stdlib pura (sem deps externas)
- Type hints completos
- Testes pytest para cada função pública
- Docstrings estilo Google

## Comece pela leitura dos docs, depois implemente, depois teste.
```

### Estimativas são otimistas

Os esforços indicados (1-4h por task) assumem:
- Você entende a arquitetura
- Documentos são lidos antes da sessão
- Escopo é respeitado (não expandir)

Adicione 30-50% de buffer para:
- Primeiras 5 tasks (curva de aprendizado)
- Tasks com "Crítica" (mais revisão)
- Debug inesperado

**Estimativa realista total**: 8-10 semanas-pessoa (vs. 6-8 otimista).

### Quando parar e revisar

Depois de cada Fase (0-7), **pare e revise antes de seguir**:

- Todos os critérios da fase foram atendidos?
- Testes estão verdes?
- Algum débito técnico acumulou? (tome nota para Fase 7)
- A arquitetura ainda bate com o que você está construindo?

### Se uma task demora 2x o estimado

**Sinais de problema**:
- Task sendo expandida no meio ("já que estou aqui...")
- Claude Code confuso com o contexto
- Você não consegue explicar o critério de aceite em uma frase

**Ação**: pare, reavalie o escopo, possivelmente divida em subtasks. Não force.

---

## Métricas de progresso

Para acompanhar, sugiro planilha simples com:

| Task | Status | Sessões | Horas reais | Testes passing | Notas |
|---|---|---|---|---|---|
| 0.1 | done | 1 | 1.5 | n/a | ... |
| 0.2 | done | 1 | 1 | n/a | ... |
| 1.1 | in_progress | 2 | 4 | 12/15 | ... |

**Red flags**:
- Task em "in_progress" por mais de 3 sessões → dividir
- Testes passing não chega a 100% antes de marcar done → não marcar
- Horas reais > 2x estimado → parar e reavaliar

---

## Gates de qualidade por fase

**Gate de Fase 1 (fundação)**:
- [ ] Todos os testes unit de orch_core.py passam
- [ ] Coverage > 90% em orch_core.py
- [ ] Sem warnings do type checker (se usando mypy)
- [ ] Hash chain valida em teste de 1000 eventos

**Gate de Fase 2 (skills básicas)**:
- [ ] Todos os scripts CLI funcionam via subprocess em testes
- [ ] emit.py rejeita corretamente eventos não-permitidos para workers
- [ ] Hooks funcionam isoladamente

**Gate de Fase 3 (single-phase)**:
- [ ] Workflow de 3 tasks com deps completa E2E sem intervenção
- [ ] Stale detection funciona
- [ ] DLQ cascade funciona

**Gate de Fase 4 (robustez)**:
- [ ] Worker perma-falhando vai para DLQ em exatamente max_attempts+1 tentativas
- [ ] Circuit breaker dispara em cenário de falha em massa
- [ ] Recovery manual funciona em log corrompido

**Gate de Fase 5 (fases)**:
- [ ] Workflow multi-fase completa E2E (cenário 11.2)
- [ ] Tasks cross-phase com deps funcionam
- [ ] Transições emitem eventos corretos

**Gate de Fase 6 (workers)**:
- [ ] Cada worker executa task real end-to-end
- [ ] Workers seguem convenções (artifacts = paths, retryable correto)

**Gate de Fase 7 (hardening)**:
- [ ] Cobertura > 85% em todo o sistema
- [ ] Preflight passa em ambiente alvo
- [ ] 5 smoke tests passam
- [ ] Runbook revisado por 2+ pessoas

---

## Checklist final antes de piloto

Antes de usar em projeto real:

- [ ] Todas as 45 tasks em status "done"
- [ ] Todos os gates de fase atendidos
- [ ] Preflight.py roda em ambiente alvo sem falhas
- [ ] Runbook está pronto
- [ ] Training do time foi feito
- [ ] Pilot plan tem escopo restrito e critérios go/no-go
- [ ] Plano de rollback está documentado
- [ ] Alguém foi designado como "owner" em caso de problema

Se algum item está marcado mas com ressalvas, **não comece o piloto**. O custo de piloto falho é muito maior que o custo de mais 1 semana de hardening.

---

## Apêndice: Mapa task → documento

Para consulta rápida de qual doc usar em cada task:

| Task | Docs primários |
|---|---|
| 0.1-0.2 | architecture §20 |
| 1.1 | orch_core_api §2.1, §3; event-schema §1; TEST_SCENARIOS §1, §2.5-2.6 |
| 1.2 | orch_core_api §1, §10; TEST_SCENARIOS §8.3-8.4 |
| 1.3 | orch_core_api §4.1; event-schema §1, §2-4; TEST_SCENARIOS §1 |
| 1.4 | orch_core_api §4.2-4.4; TEST_SCENARIOS §1.3-1.7 |
| 1.5 | orch_core_api §5.1; TEST_SCENARIOS §2 |
| 1.6 | orch_core_api §6; event-schema §5.1; TEST_SCENARIOS §6 |
| 1.7 | orch_core_api §7, §2.2-2.4; architecture §8; TEST_SCENARIOS §3, §5 |
| 1.8 | orch_core_api §7.3, §8 |
| 2.1-2.5 | architecture §9.4; tasks 1.x como base |
| 2.6 | architecture §9.5.1; TEST_SCENARIOS §7 |
| 3.x | architecture §9.1, §14 |
| 4.1-4.2 | orch_core_api §9; TEST_SCENARIOS §4; architecture §10 |
| 4.3 | architecture §10.3; TEST_SCENARIOS §4.7-4.9 |
| 4.4 | orch_core_api §5.2; TEST_SCENARIOS §9 |
| 4.5 | architecture §13 |
| 4.6 | architecture §17; TEST_SCENARIOS §10 |
| 5.1-5.2 | event-schema §3; orch_core_api §2.3; TEST_SCENARIOS §5 |
| 5.3 | architecture §9.4.4 |
| 5.4 | architecture §9 (v4.2 orchestrator.md) |
| 5.5-5.6 | architecture §6 |
| 5.7 | TEST_SCENARIOS §11.2 |
| 6.x | architecture §9.2 |
| 7.x | todos os docs (revisão final) |
