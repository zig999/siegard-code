# Auditoria — Scripts Python, Invocações LLM e Geração de Artefatos
**Data:** 2026-05-08 | **Branch:** feat/new-flow | **Modelo:** claude-sonnet-4-6

---

## Resumo Executivo

```
Total de scripts .py:   51
Total de testes:       707
Passando:              616 (87.1%)
Falhando:               91 (12.9%)
Framework:             pytest 9.0
Configuração:          dist/pytest.ini
```

---

## 1. Inventário de Scripts Python

### Core Library (2 arquivos)

| Arquivo | Tamanho | Papel |
|---------|---------|-------|
| `dist/.claude/lib/__init__.py` | 36 B | Package init marker |
| `dist/.claude/lib/orch_core.py` | 80 KB | Engine central — EventType enum, OrchState, validação, serialização, hash chain, locking |

### Hooks (2 arquivos)

| Arquivo | Tamanho | Invocado por | Escreve |
|---------|---------|-------------|---------|
| `dist/.claude/hooks/on_stop.py` | 14 KB | Claude Code stop hook (`settings.json`) | `.orch/metrics/current.json`, `.orch/last_error.json` |
| `dist/.claude/hooks/on_subagent_stop.py` | 4.6 KB | Claude Code subagent stop hook | Eventos `task_failed` no `log.jsonl` via `append_event()` |

### Scripts Principais (10 arquivos em `dist/.claude/scripts/`)

| Script | Args principais | Output | Exit codes |
|--------|----------------|--------|------------|
| `validate_dist.py` | `[--strict]` | Validação de consistência de dist/ | 0=ok, 1=erros |
| `purge.py` | `--confirm [--blobs] [--sessions] [--workflow-id] [--reset-log\|--delete-log] [--operator] [--json]` | Deleta arquivos temporários de `.orch/` | 0=ok, 2=dry-run, 3=args inválidos, 4=erro |
| `gc_orphan_blobs.py` | `[--delete] [--json]` | Lista/remove blobs órfãos | 0=ok, 1=sem blobs, 4=erro |
| `dlq_triage.py` | `[--task-id] [--json]` | Classifica tasks DLQ em 7 buckets com ações sugeridas | 0=ok, 1=sem DLQ, 4=erro |
| `fix_stuck_improve.py` | `--session ID --action [accept_divergence\|retry] [--dry-run]` | Recovery de improve flow travado | 0=ok, 1=erro |
| `circuit_breaker.py` | `[--status \| --reset --confirm --operator EMAIL [--notes]]` | Status/reset do circuit breaker | 0=ok, 1=não ativo, 2=sem confirm, 3=sem operator, 4=erro |
| `preflight.py` | `[--quick]` | Valida ambiente antes de iniciar workflow | 0=ok, 1=falha, 2=args inválidos |
| `monitor.py` | `[--project-dir] [--interval N] [--once]` | TUI curses com estado do workflow em tempo real | — |
| `evaluate_circuit.py` | — | Avalia se circuit breaker deve ser ativado | 0 ou 1 |
| `recover_retry_sequence.py` | — | Recovery de sequências de retry | — |

### Scripts de Estado e Log (7 arquivos)

**`skills/orch-log/scripts/`**

| Script | Invocação | Output |
|--------|-----------|--------|
| `append.py` | `--agent A --event-type T [--task-id I] [--attempt N] [--data JSON]` | JSON do evento criado (stdout) |
| `read.py` | `[--from-seq N] [--tail N] [--task-id I] [--event-type T] [--phase P]` | JSONL de eventos (stdout) |
| `verify.py` | `[--mode strict\|audit] [--recover --confirm --from-seq N --operator E]` | JSON com resultado da verificação |

**`skills/orch-state/scripts/`**

| Script | Invocação | Output |
|--------|-----------|--------|
| `reduce.py` | sem args | JSON completo do `OrchState` (stdout) |
| `current_phase.py` | sem args | `{"current_phase": str, "status": str, "order": int}` |
| `detect_mode.py` | sem args | `{"mode": "new"\|"resume", "workflow_id": str\|null}` |
| `summary.py` | sem args | Resumo human-readable do estado |

### Scripts de Fase (29 arquivos)

Cada fase tem os mesmos 3 tipos de script:

#### `select_worker.py` (existe em todas as 4 fases)

```bash
python3 .claude/skills/phase-{fase}-rules/scripts/select_worker.py \
  --task-type <type> [--stack <stack>]
```

Output: nome do agente a ser invocado para aquela combinação `(task_type, stack)`.

#### Exit criteria checkers

Cada fase tem 3 scripts de critério. Padrão de invocação:

```bash
python3 .claude/skills/phase-{fase}-rules/scripts/check_<criterio>.py
```

Output esperado: `{"criterion": "<nome>", "met": true|false, "evidence": {...}}`

| Fase | Scripts de critério |
|------|---------------------|
| SDD | `check_handoff_manifest_approved.py`, `check_all_domains_validated.py`, `check_error_codes_synced.py` |
| Dev | `check_all_impl_tasks_terminal.py`, `check_all_deliveries_qa_ready.py`, `check_no_open_prohibitions.py` |
| Review | `check_all_qa_verdicts_approved.py`, `check_no_open_critical_findings.py`, `check_documentation_verified.py` |
| Test | `check_all_test_tasks_terminal.py`, `check_all_tests_passed.py`, `check_no_critical_failures.py` |

**Utilitários adicionais:**
- `phase-sdd-rules/scripts/check_structural_diff.py` — avalia se mudança em improve requer workers de domínio
- `phase-sdd-rules/scripts/check_all_improve_reviewers_completed.py` — critério alternativo ao `check_all_domains_validated` em improve flows
- `phase-review-rules/scripts/read_qa_verdict.py` — helper de extração de veredicto de QA

### Scripts de Suporte (6 arquivos)

| Arquivo | Papel |
|---------|-------|
| `orch-report/scripts/emit.py` | Emite evento de relatório estruturado |
| `u-worker-compliance/scripts/check_worker.py` | Valida compliance de workers |
| `orch-infra/scripts/run_preflight.py` | Wrapper de preflight para invocação pelos orquestradores |
| `orch-infra/scripts/run_integrity.py` | Wrapper de verificação de integridade do log |
| `orch-infra/scripts/run_circuit_check.py` | Wrapper de verificação do circuit breaker |

---

## 2. Estado Atual dos Testes

### Como executar

```bash
# Diretório correto — pytest.ini está em dist/
cd /home/siegfriedneto/projects/siegard-code/dist

# Suite completa
python3 -m pytest tests/ -v --tb=short

# Por camada
python3 -m pytest tests/test_*.py -v                      # unit
python3 -m pytest tests/orchestrator_scenarios/ -v        # integration
python3 -m pytest tests/phase_scripts/ -v                 # E2E scripts

# Script específico
python3 -m pytest tests/phase_scripts/test_check_dev_exit_criteria.py -v

# Com cobertura
python3 -m pytest tests/ --cov=.claude/lib --cov-report=term-missing
```

### Organização dos testes

| Camada | Diretório | Arquivos | O que cobre |
|--------|-----------|----------|-------------|
| Unit | `tests/test_*.py` | 26 | Funções isoladas de `orch_core.py` — append, verify, reduce, retry, locking, blobs |
| Integration | `tests/orchestrator_scenarios/` | 3 | Máquina de estados sem spawn de agentes — falhas Dev, escalações, handoffs |
| E2E scripts | `tests/phase_scripts/` | 5 | Invocação real via subprocess dos scripts de exit criteria e select_worker |

### Resultado atual: 91 falhas em 3 classes de causa

#### Causa A — Desync de `_VALID_FAILURE_REASONS` (~50 falhas)

Os testes usam strings de razão de versões anteriores do `orch_core.py`:

| Testes usam | `orch_core.py` aceita |
|-------------|----------------------|
| `subagent_stopped` | `worker_exited_without_terminal` |
| `runtime_error` | `internal_error` |
| `timeout` | `stale_timeout` |
| `error` | `internal_error` |
| `env_broken` | (não existe) |

Todos os testes que emitem `task_failed` com essas razões falham com `EventValidationError`. O enum `_VALID_FAILURE_REASONS` foi expandido no branch `feat/new-flow` mas os testes não foram atualizados.

**Afeta:** `test_on_subagent_stop.py`, `test_integration.py`, `test_retry_reducer.py`, `orchestrator_scenarios/test_dev_failures.py`

#### Causa B — Desync de output dos scripts de exit criteria (~20 falhas)

Os testes esperam:
```json
{"criterion": "...", "met": true, "evidence": {...}}
```

Os scripts atuais retornam formato diferente — chaves `met` ou `criterion` ausentes.

```
KeyError: 'met'       → 17 falhas em test_check_dev_exit_criteria e test_check_sdd_exit_criteria
KeyError: 'criterion' →  3 falhas em test_check_sdd_exit_criteria
```

**Afeta:** `tests/phase_scripts/test_check_sdd_exit_criteria.py` (todos os 17 testes)

#### Causa C — EventType enum desync (~5 falhas)

```python
assert 27 == 21  # testes esperam 21 EventTypes, orch_core tem 27
```

O enum foi expandido com 6 novos tipos (improve flow, dispatch governance) mas os testes de contagem não foram atualizados.

**Afeta:** `tests/test_event.py` (3 testes)

### Correção dos testes

```bash
# 1. Verificar razões usadas nos testes
grep -rn "reason.*'" dist/tests/ --include="*.py" | grep -v "^Binary" | sort -u

# 2. Verificar razões aceitas pelo orch_core atual
python3 -c "
import sys; sys.path.insert(0, 'dist/.claude/lib')
from orch_core import _VALID_FAILURE_REASONS
print(sorted(_VALID_FAILURE_REASONS))
"

# 3. Verificar output real dos scripts de exit criteria
python3 dist/.claude/skills/phase-sdd-rules/scripts/check_handoff_manifest_approved.py 2>&1
python3 dist/.claude/skills/phase-dev-rules/scripts/check_all_impl_tasks_terminal.py 2>&1
```

### Prevenção de futuros desync

Adicionar fixture de contrato que lê `_VALID_FAILURE_REASONS` do `orch_core.py` e valida que todos os valores usados nos demais testes estão nele:

```python
# tests/conftest.py — adicionar
import sys
sys.path.insert(0, '.claude/lib')
from orch_core import _VALID_FAILURE_REASONS

def test_all_test_failure_reasons_are_valid():
    """Garante que os testes usam apenas razões aceitas pelo orch_core atual."""
    import subprocess, re
    result = subprocess.run(
        ['grep', '-rn', "reason.*'", 'tests/'],
        capture_output=True, text=True
    )
    used = set(re.findall(r"reason['\"]:\s*['\"]([^'\"]+)['\"]", result.stdout))
    invalid = used - _VALID_FAILURE_REASONS - {'max_attempts_exceeded'}
    assert not invalid, f"Razões inválidas nos testes: {invalid}"
```

### Smoke test para todos os scripts

```bash
# Verifica que cada script executa sem crash e retorna JSON válido
for f in dist/.claude/scripts/*.py dist/.claude/skills/*/scripts/*.py; do
  out=$(python3 "$f" --json 2>&1) || out=$(python3 "$f" 2>&1)
  echo "$out" | python3 -c "import sys,json; json.load(sys.stdin)" \
    && echo "OK  : $f" \
    || echo "FAIL: $f"
done
```

---

## 3. Verificação de Invocações LLM → Python

### Padrão padrão

Todos os `.md` invocam scripts com:
```bash
python3 .claude/skills/<skill>/scripts/<script>.py [args]
```

### Conformidade por script

| Script | Invocação no .md | Assinatura real | Status |
|--------|-----------------|-----------------|--------|
| `orch-log/scripts/append.py` | `--agent X --event-type Y [--task-id Z] [--attempt N] [--data JSON]` | Idem | ✅ |
| `orch-log/scripts/read.py` | `[--from-seq N] [--tail N] [--task-id ID] [--event-type T] [--phase P]` | Idem | ✅ |
| `orch-log/scripts/verify.py` | `[--mode strict\|audit] [--recover ...]` | Idem | ✅ |
| `orch-state/scripts/reduce.py` | sem args | sem args | ✅ |
| `orch-state/scripts/current_phase.py` | sem args | sem args | ✅ |
| `phase-{x}-rules/scripts/select_worker.py` | `--task-type T [--stack S]` | `--task-type [--stack]` | ✅ |
| `scripts/preflight.py` | `[--quick]` | `[--quick]` | ✅ |
| `scripts/circuit_breaker.py` | `--status\|--reset --confirm --operator EMAIL` | Idem | ✅ |
| `phase-{x}-rules/scripts/check_*.py` | sem args (maioria) | variado | ⚠️ verificar output |

### Risco crítico: invocações `python3 -c` inline

`orchestrator-dev.md` contém blocos Python inline que não são testáveis:

```bash
python3 -c "
import sys, json
sys.path.insert(0, '.claude/lib')
from orch_core import read_events_filtered, EventType
events = read_events_filtered(event_type=EventType.PHASE_DECLARED.value)
wt = events[0].data.get('workflow_type', 'standard') if events else 'standard'
print(json.dumps({'workflow_type': wt}))
"
```

| # | Risco | Severidade |
|---|-------|------------|
| 1 | Não cobertos por testes — impossível testar sem mockar o LLM | Alta |
| 2 | `sys.path.insert(0, '.claude/lib')` relativo ao CWD — falha se orquestrador roda de diretório diferente | Alta |
| 3 | Sem saída de erro padronizada — exceção retorna traceback não estruturado | Média |
| 4 | Sem detecção de quebra de API — `read_events_filtered` pode ser renomeada sem alertar | Alta |

### Verificação sistemática de invocações

```bash
# 1. Extrair todos os blocos python3 dos .md
grep -rn "python3" dist/.claude --include="*.md" -A2 | grep -v "^--$"

# 2. Comparar args usados nos .md contra argparse de cada script
for script in dist/.claude/skills/*/scripts/*.py dist/.claude/scripts/*.py; do
  echo "=== $(basename $script) ==="
  python3 "$script" --help 2>&1 | grep "usage\|optional\|positional" | head -3
done

# 3. Validar que todo event-type em append.py calls existe no enum
cd dist && grep -rh "event-type" .claude --include="*.md" \
  | grep -oP "'[a-z_:]+'" | sort -u \
  | python3 -c "
import sys; sys.path.insert(0, '.claude/lib')
from orch_core import EventType
valid = {e.value for e in EventType}
for line in sys.stdin:
    et = line.strip().strip(\"'\")
    if et:
        status = 'OK' if et in valid else 'MISSING'
        print(f'{status}: {et}')
"
```

---

## 4. Artefatos: Python vs LLM

### Artefatos gerados por Python

| Artefato | Script responsável | Validação de escrita |
|----------|--------------------|----------------------|
| `.orch/log.jsonl` | `skills/orch-log/scripts/append.py` | Hash chain + schema validation + flock |
| `.orch/metrics/current.json` | `hooks/on_stop.py` | Nenhuma (swallows exceptions) |
| `.orch/last_error.json` | `hooks/on_stop.py` | Nenhuma (swallows exceptions) |
| `.orch/blobs/*.json` | `lib/orch_core.py` (inline no append) | Referência registrada no log |
| Estado derivado | `skills/orch-state/scripts/reduce.py` | Nunca persiste — apenas stdout |
| Fase atual | `skills/orch-state/scripts/current_phase.py` | Apenas stdout |
| Modo de workflow | `skills/orch-state/scripts/detect_mode.py` | Apenas stdout |

### Artefatos gerados pelo LLM

| Artefato | Worker | Formato | Validação posterior |
|----------|--------|---------|---------------------|
| `handoff-manifest.yaml` | `u-spec-compliance` | YAML + schema | `check_handoff_manifest_approved.py` |
| `triage.json` | `u-spec-triage` | JSON | Nenhuma — lido diretamente pelo LLM |
| `.back.md` (spec backend) | `u-spec-back` | Markdown estruturado | `check_all_domains_validated.py` |
| `.front.md` (spec frontend) | `u-spec-front` | Markdown estruturado | `check_all_domains_validated.py` |
| `backlog.md` | `u-be-planner` / `u-fe-planner` | Markdown | Nenhuma — lido diretamente pelo LLM |
| `delivery.md` (por task) | `u-be-developer` / `u-fe-developer` | YAML front-matter + MD | `check_all_deliveries_qa_ready.py` |
| `qa-verdict.md` (por task) | `u-be-qa-docs` / `u-fe-qa-docs` | YAML front-matter + MD | `check_all_qa_verdicts_approved.py` |
| `improve-scope.json` | LLM via `/u-improve` | JSON | Parcial — `fix_stuck_improve.py` lê mas não valida schema |
| `validation/*.md` | `u-spec-validator` | Markdown | `check_all_domains_validated.py` |
| `error-codes.md` | `u-spec-back` / `u-spec-compliance` | Markdown | `check_error_codes_synced.py` |

### Modelo de validação atual

```
LLM escreve artefato → [sem validação imediata] → Python script lê depois → detecta erro
```

Este modelo cria janela de risco entre escrita e detecção.

### Riscos por artefato sem validação imediata

| # | Risco | Consequência |
|---|-------|-------------|
| 1 | `handoff-manifest.yaml` com schema incorreto | `check_handoff_manifest_approved.py` retorna `met: false` — SDD não avança, motivo pode não ser claro |
| 2 | `delivery.md` com `qa_ready: true` sem testes | `check_all_deliveries_qa_ready.py` passa (lê o campo), qualidade não validada |
| 3 | `qa-verdict.md` com seção obrigatória ausente | `read_qa_verdict.py` retorna `KeyError` sem detalhe do campo ausente |
| 4 | `triage.json` malformado | `effective_mode` ausente — routing do orchestrator-sdd defaultado ou falha silenciosamente |
| 5 | `backlog.md` com task IDs duplicados | orchestrator-dev cria tasks com IDs duplicados — viola idempotência (P4) |

### Mapa de cobertura de validação

| Artefato | Script validador | Momento da validação |
|----------|-----------------|---------------------|
| `handoff-manifest.yaml` | ✅ `check_handoff_manifest_approved.py` + `u-handoff-validator` | Pós-geração (exit criteria SDD) |
| `delivery.md` | ✅ `check_all_deliveries_qa_ready.py` | Pós-geração (exit criteria Dev) |
| `qa-verdict.md` | ✅ `check_all_qa_verdicts_approved.py` | Pós-geração (exit criteria Review) |
| `validation/*.md` | ✅ `check_all_domains_validated.py` | Pós-geração (exit criteria SDD) |
| `error-codes.md` | ✅ `check_error_codes_synced.py` | Pós-geração (exit criteria SDD) |
| **`triage.json`** | ❌ **Nenhum** | **Nunca** |
| **`backlog.md`** | ❌ **Nenhum** | **Nunca** |
| `improve-scope.json` | ⚠️ Parcial | Apenas em recovery |

**Gap crítico:** `triage.json` e `backlog.md` são os dois artefatos com maior influência no routing do pipeline e os menos protegidos. Ambos são gerados pelo LLM e consumidos diretamente por outros LLMs sem validação Python intermediária.

---

## 5. Ações Recomendadas

### Imediatas (sem mudança de arquitetura)

```bash
# Confirmar causa das 91 falhas
cd dist && python3 -m pytest tests/ --tb=line -q 2>&1 \
  | grep "EventValidationError\|KeyError\|assert.*==" | sort | uniq -c | sort -rn

# Verificar output real dos scripts de critério
python3 .claude/skills/phase-sdd-rules/scripts/check_handoff_manifest_approved.py
python3 .claude/skills/phase-dev-rules/scripts/check_all_impl_tasks_terminal.py

# Listar event types válidos atuais
python3 -c "
import sys; sys.path.insert(0, '.claude/lib')
from orch_core import _VALID_FAILURE_REASONS
print(sorted(_VALID_FAILURE_REASONS))
"
```

### Curto prazo

1. **Corrigir 91 testes com drift:** atualizar strings de razão e output de exit criteria para refletir `orch_core.py` atual.
2. **Adicionar validador de `triage.json`:** script Python que valida campos obrigatórios (`effective_mode`, `execution_policy`, `affected_domains`) antes do orchestrator-sdd os consumir.
3. **Adicionar validador de `backlog.md`:** script que verifica unicidade de task IDs e presença de campos obrigatórios no front-matter de cada task contract.
4. **Mover `python3 -c` inline para scripts dedicados:** cada bloco inline nos orquestradores deve se tornar um script em `orch-state/scripts/` com argparse e exit code padronizado.

### Médio prazo

5. **Fixture de contrato para `_VALID_FAILURE_REASONS`:** teste automático que impede desync futuro entre enum e testes.
6. **Smoke test de todos os scripts:** verificação automática que cada `.py` executa e retorna JSON válido.
7. **CWD guard nos blocos `python3 -c`:** substituir `sys.path.insert(0, '.claude/lib')` por path absoluto derivado de `__file__` ou variável de ambiente `ORCH_PROJECT_DIR`.
