# Engine de Workflow

> Como o sistema de orquestração funciona internamente: event sourcing, dispatch loop, retry, circuit breaker, hooks e recovery.

---

## Event Sourcing — O log como fonte de verdade

Todo o estado do sistema é derivado de um arquivo JSONL append-only:

```
.orch/log.jsonl
```

**Nenhum componente guarda estado próprio.** A cada invocação, o orchestrator relê o log e reconstrói o estado completo (`OrchState`) via `reduce_all()`. Isso garante:

- **Crash recovery trivial:** releia o log, retome de onde parou
- **Auditabilidade completa:** cada decisão está registrada com seq number e timestamp
- **Determinismo:** mesmo log → mesmas decisões, sempre

### Estrutura de um evento

```json
{
  "seq": 42,
  "event_id": "evt_01HK7XZY8K9ABCDE01234",
  "ts": "2026-04-20T10:00:42.123Z",
  "agent": "orchestrator | worker-sdd-42 | hook-on_subagent_stop",
  "event_type": "task_completed",
  "task_id": "dev_tc_001",
  "attempt": 1,
  "data": { ... },
  "prev_hash": "<sha256 do evento anterior>",
  "hash": "<sha256 deste evento>"
}
```

A cadeia de hashes SHA-256 (`prev_hash` → `hash`) garante integridade: qualquer adulteração é detectável via `verify.py`.

### 21 event types

**Task lifecycle (8):**

| Type | Emitido por | Quando |
|------|------------|--------|
| `task_created` | orchestrator | Nova task declarada |
| `task_claimed` | orchestrator | Task atribuída a um worker |
| `task_progress` | worker | Heartbeat / milestone |
| `task_completed` | worker | Worker terminou com sucesso |
| `task_failed` | worker / hook | Worker falhou |
| `task_scheduled_retry` | orchestrator | Backoff agendado |
| `task_retried` | orchestrator | Task reenfileirada (attempt+1) |
| `task_dlq` | orchestrator | Task falhou permanentemente |

**Phase lifecycle (7):**

| Type | Emitido por | Quando |
|------|------------|--------|
| `phase_declared` | meta-orchestrator | Fases do workflow declaradas (first run) |
| `phase_entered` | meta-orchestrator | Fase torna-se ativa |
| `phase_exit_criterion_met` | phase orchestrator | Um exit criterion satisfeito |
| `phase_exit_approved` | phase orchestrator | Todos os criteria satisfeitos |
| `phase_transitioned` | phase orchestrator | Fase completada, próxima anunciada |
| `phase_paused` | orchestrator | Fase pausada (circuit breaker, escalation) |
| `phase_resumed` | orchestrator | Fase retomada após pausa |

**Management (6):**

| Type | Emitido por | Quando |
|------|------------|--------|
| `circuit_breaker_tripped` | orchestrator | Threshold de falhas excedido |
| `escalation` | orchestrator / phase orch | Intervenção humana necessária |
| `human_response` | operador | Operador resolve escalation |
| `snapshot` | hook / orchestrator | Checkpoint de estado |
| `log_recovered` | `verify_and_recover` | Log truncado, corrupção arquivada |
| `preflight_failed` | `preflight.py` | Check pré-execução falhou |

---

## OrchState — Estado derivado do log

`reduce_all()` em `orch_core.py` replays todos os eventos e retorna um `OrchState`:

```python
@dataclass
class OrchState:
    workflow_id: str | None       # UUID do workflow (do phase_declared)
    run_status: str               # "active" | "escalated"
    current_phase: str | None     # Fase ativa atual
    tasks: dict[str, TaskState]   # Todas as tasks por task_id
    phases: dict[str, PhaseState] # Estado de cada fase declarada
    escalation: dict | None       # Escalation ativa, se houver
    circuit_breaker: dict | None  # Estado do circuit breaker
    last_seq: int                 # Último seq processado
    failure_timestamps: list[str] # Timestamps de task_failed (para circuit breaker)
```

**PhaseState** (campos relevantes):
- `status`: `"pending"` | `"active"` | `"completed"`
- `entered_at`: ISO timestamp de quando a fase entrou
- `completed_at`: ISO timestamp de quando a fase completou
- `required`: bool — se false, workflow pode completar sem esta fase

**TaskState** (campos relevantes):
- `status`: `PENDING` | `SCHEDULED` | `RUNNING` | `COMPLETED` | `FAILED` | `DLQ`
- `attempts`: número de tentativas realizadas
- `artifacts`: lista de paths de artefatos produzidos
- `last_error`: último erro registrado

---

## Dispatch Loop — Como workers são spawned

Os phase orchestrators executam um **dispatch loop** com as seguintes etapas a cada iteração:

### 6.0 — Pre-loop checks

```
1. Refresh state (re-read log)
2. Check circuit breaker status
3. Detect stale tasks (running > threshold)
4. Cascade DLQ para tasks com dependências em DLQ
5. Re-enqueue scheduled tasks cujo backoff expirou
```

**Thresholds de stale detection por tier:**

| Tier | Threshold |
|------|-----------|
| `critical` | 600s |
| `standard` | 300s |
| `bulk` | 120s |

### 6.1 — Select batch

Seleciona até **2 tasks** prontas para dispatch:
- `status == PENDING` ou `SCHEDULED` com backoff expirado
- Ordenação: `priority desc, seq asc` (determinístico)
- Dependências (`deps`) devem estar todas `COMPLETED`

### 6.2 — Claim batch (serial)

Para cada task no batch:
```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --event-type task_claimed \
  --task-id {task_id} \
  --data '{"worker_id": "<id>", "evidence": [<last_seq>]}'
```

Todos os claims são serializados (flock no lock file). Sem claims, sem spawn.

### 6.3 — Spawn em paralelo

**Uma única resposta do LLM** com múltiplas chamadas `Agent()` — o Claude Code executa os workers concorrentemente:

```
Orchestrator response turn N:
  Agent(worker_A, prompt=...)   ← emitidos juntos
  Agent(worker_B, prompt=...)   ← emitidos juntos

Claude Code roda worker_A e worker_B simultaneamente.
Orchestrator retoma no turn N+1 com ambos os resultados.
```

Os workers recebem variáveis de ambiente via prompt (não herdam o shell):
```
ORCH_TASK_ID:     {task_id}
ORCH_ATTEMPT:     {attempt}
ORCH_WORKER_ID:   {worker_id}
ORCH_PROJECT_DIR: {project_dir}
SPECS_DIR:        {specs_dir}
```

### 6.4 — Verify terminal events

Após os workers retornarem, re-lê o estado.

Se algum worker ainda aparece como `RUNNING` (nenhum `task_completed` ou `task_failed` no log): worker saiu silenciosamente. O hook `on_subagent_stop.py` deve ter sintetizado um `task_failed(retryable=true)`. Se não: sintetiza manualmente.

### 6.5 — Retry decisions

Para cada task com `status == FAILED`:
- Aplica política de retry baseada em `(tier, task_type)`
- Se `retryable=true` e `attempts < max_attempts`: emite `task_scheduled_retry` com `next_retry_at`
- Se não-retryável ou limite atingido: emite `task_dlq`

**Política de retry padrão por tier:**

| Tier | Max attempts | Backoff |
|------|-------------|---------|
| `critical` | 3 | exponencial (30s, 120s, 480s) |
| `standard` | 3 | exponencial (60s, 240s, 960s) |
| `bulk` | 2 | linear (300s) |

### 6.6 — Exit criteria

Ao final de cada iteração, roda os scripts de exit criteria da fase:

```bash
python3 .claude/skills/phase-{name}-rules/scripts/check_{criterion}.py
```

Cada script retorna `{"status": "met"|"not_met"|"error", "criterion": "...", ...}`.

Se todos os criteria foram `met`: emite `phase_exit_criterion_met` × N, depois `phase_exit_approved`, depois `phase_transitioned`. Retorna `{"status": "phase_complete", ...}`.

**Safety limit:** Max 30 iterações por invocação de phase orchestrator.

---

## Circuit Breaker

Proteção contra cascata de falhas. Implementado em `orch_core.py` via `evaluate_circuit_state()`.

### Estados

| Estado | Condição | Comportamento |
|--------|---------|--------------|
| **Open** (normal) | Menos de N falhas em W segundos | Dispatch continua normalmente |
| **Tripped** | ≥ N falhas em W segundos | Dispatch bloqueado; `circuit_breaker_tripped` emitido; escalation ao usuário |

### Reset

```bash
python3 .claude/scripts/evaluate_circuit.py
```

Ou via `human_response` com `action: reset_circuit_breaker`:
```json
{"action": "reset_circuit_breaker", "operator": "user@example.com"}
```

Quando `reset_circuit_breaker` chega, `_handle_human_response` em `orch_core.py` limpa `state.circuit_breaker` e `state.failure_timestamps`.

---

## Retry Policy

```python
policy = load_retry_policy(tier, task_type)
if should_retry(task, policy):
    emit task_scheduled_retry(next_retry_at=now + backoff)
else:
    emit task_dlq(reason=..., triage_bucket=...)
```

O DLQ (`task_dlq`) é permanente — a task não volta automaticamente. Para reinspecionar e categorizar:

```bash
python3 .claude/scripts/dlq_triage.py [--task-id <id>] [--json]
```

**Buckets de triage:**

| Bucket | Causa típica |
|--------|-------------|
| `input_issue` | Spec unclear, input ausente, schema errado |
| `worker_issue` | Worker crashou, tool failure, timeout |
| `permission_issue` | Auth failure, quota excedida |
| `code_issue` | Bug na lógica do worker |
| `quota_issue` | Rate limit, token budget |
| `transient_issue` | Erro de rede, indisponibilidade temporária |
| `unknown` | Sem sinal identificável |

---

## Hooks — Robustez fora do LLM

### `on_subagent_stop.py` — Detecção de crash

**Trigger:** Claude Code chama este hook quando qualquer sub-agente para.

**O que faz:**
1. Lê o worker registry em `.orch/workers/<worker_id>.json`
2. Se não é contexto orquestrado: no-op
3. Para cada worker ativo: verifica se há evento terminal `(task_id, attempt)` no estado derivado
4. Se não há terminal: sintetiza `task_failed(retryable=true, reason="worker_exited_silently")`
5. Desregistra o worker entry

**Por que existe:** Workers são sub-agentes Claude. Se o Claude Code encerra a sessão, mata a API call, ou o worker lança uma exceção não tratada, ele para sem emitir `task_completed` ou `task_failed`. Sem esse hook, a task ficaria presa em `RUNNING` para sempre.

### `on_stop.py` — Métricas ao encerrar

**Trigger:** Claude Code chama quando a sessão encerra.

**O que faz:**
1. Chama `reduce_all()` para obter estado atual
2. Computa métricas: tasks por status, fases completadas, durações, % de completion
3. Escreve em `.orch/metrics/current.json`
4. Swallows todas as exceções (nunca bloqueia o shutdown)

---

## Human Interaction Model

O sistema usa o padrão `escalation` + `human_response` para comunicação assíncrona com o humano. **Nenhum orchestrator bloqueia aguardando input** — emite uma escalation, para, e o humano re-invoca o orchestrator após responder.

> **Gates interativos (caminho usual):** quando a escalation tem `severity: info` **e** `options` (ex.: `E99_human_confirmation_required`), o **meta-orchestrator** a apresenta via `AskUserQuestion` (regra M5, estado `escalation_active` em `orch_core.py`), grava o `human_response` da escolha e **retoma o phase orchestrator na mesma invocação** — o humano NÃO roda `append.py` manualmente. O fluxo manual abaixo aplica-se a escalations sem `options` ou de severidade warning/critical (`surface_error`). Como o meta só expõe `code` + `reason` + `options`, o `reason` da E99 carrega o resumo de decisão (domains, front-leg).

### Fluxo

```
1. Phase orchestrator detecta condição que requer human input
2. Emite escalation(code="E99", question="...", options=[...])
3. Retorna {"status": "escalated", ...} ao meta-orchestrator
4. Meta-orchestrator detecta run_status="escalated", exibe ao usuário, para
5. Usuário analisa e emite human_response:
   python3 .claude/skills/orch-log/scripts/append.py \
     --event-type human_response \
     --data '{"escalation_seq": 42, "action": "confirm_proceed", "operator": "user"}'
6. Usuário re-invoca o orchestrator
7. _handle_human_response em orch_core.py reseta state.escalation=None e run_status="active"
8. Phase orchestrator detecta a resposta e retoma
```

### Human gates por fase

| Fase | Gate | Opções |
|------|------|--------|
| `sdd` | Confirmação antes do primeiro dispatch | `confirm_proceed`, `abort` |
| `review` | Aprovação dos QA verdicts | `approve`, `return_to_dev`, `return_partial` |
| `test` | Só se testes falham | `return_to_dev`, `accept_with_failures` |

---

## Escalation Codes

Referência completa em `dist/.claude/ESCALATION_CODES.md`.

| Code | Severity | Emitido por | Condição |
|------|----------|------------|---------|
| `E04` | critical | dev, test | Task crítica em DLQ |
| `E05` | critical | sdd | spec-writer ≥3 attempts ou spec-validator ≥2 |
| `E07` | critical | dev | Planning falhou de forma não-retryável |
| `E08` | warning | todas | Tasks terminadas mas exit criteria não passaram |
| `E09` | warning | review | QA encontrou divergências de spec (`SPEC-DIVERGENCE:`) |
| `E10` | critical | meta-orch | Phase orchestrator retornou error + circuit tripped |
| `E11` | critical | sdd | spec-reviewer falhou com inputs ausentes |
| `E99_human_confirmation_required` | info | sdd | Gate antes do primeiro dispatch |
| `E99_human_approval_required` | info | review | Verdicts prontos para aprovação |
| `E99_human_test_intervention_required` | warning | test | Falhas detectadas nos testes |

---

## Guard-rail do orch-report

O skill `orch-report` (usado pelos workers via `emit.py`) tem uma **barreira de segurança não-negociável**: rejeita incondicionalmente qualquer event type que não seja `task_progress`, `task_completed`, ou `task_failed`.

Isso é um **boundary de segurança em código**, não uma instrução soft. Um worker jamais pode emitir `task_claimed`, `task_dlq`, `escalation`, `phase_entered`, etc. — mesmo que a prompt do worker solicite.

```python
# emit.py — guard-rail implementation
ALLOWED_KINDS = {"progress", "completed", "failed"}
if kind not in ALLOWED_KINDS:
    print(json.dumps({"status": "error", "reason": "forbidden_event_type"}))
    sys.exit(1)
```

---

## Exemplo de fluxo de eventos (workflow completo)

```
seq=1  phase_declared        workflow_id=abc, phases=[sdd,dev,review,test]
seq=2  phase_entered         phase=sdd, evidence_seq=1
seq=3  task_created          sdd_payment_spec-writer, tier=standard
seq=4  task_claimed          sdd_payment_spec-writer → worker-sdd-01
seq=5  task_progress         worker-sdd-01: "Writing openapi.yaml"
seq=6  task_completed        worker-sdd-01: artifacts=[specs/payment/openapi.yaml]
seq=7  task_created          sdd_payment_spec-reviewer
seq=8  task_claimed          sdd_payment_spec-reviewer → worker-sdd-02
seq=9  task_completed        worker-sdd-02: approved
...
seq=N  phase_exit_criterion_met  handoff_manifest_approved
seq=N+1 phase_exit_criterion_met  all_domains_validated
seq=N+2 phase_exit_criterion_met  error_codes_synced
seq=N+3 phase_exit_approved
seq=N+4 phase_transitioned    from=sdd, to=dev
seq=N+5 phase_entered         phase=dev, evidence_seq=N+4
seq=N+6 task_created          dev_planning
...
```
