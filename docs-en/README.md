# Siegard — System Documentation

> Documentação do motor de orquestração entregue em `dist/.claude/`.
> Referencie os arquivos-fonte em `dist/.claude/` para detalhes de implementação.

---

## What this system is

O siegard é uma **engine de orquestração event-sourced para workflows multi-fase no Claude Code**. Funciona como um Temporal ou Airflow nativo para sub-agentes Claude: coordena execução paralela de workers, mantém estado auditável via log append-only, garante retry automático, detecção de crash e recovery.

O sistema é **agnóstico de domínio na infraestrutura** — a lógica de negócio (SDD, Dev, QA, Test) fica em skills de fase plugáveis. O núcleo nunca muda; o comportamento muda pelos skills.

---

## Documentação

| Documento | Conteúdo |
|-----------|---------|
| [flow.md](flow.md) | **Resumo: fases, rotas e gates.** Como o siegard funciona e como o workflow é gerido. Comece por aqui. |
| [agents.md](agents.md) | Todos os agentes: meta-orchestrator, phase orchestrators, workers |
| [workflow.md](workflow.md) | Engine de workflow: event sourcing, fases, dispatch loop, circuit breaker |
| [specs.md](specs.md) | Como specs são gerenciadas: pipeline SDD, validações, artefatos |
| [artifacts.md](artifacts.md) | Catálogo completo de artefatos criados pelo sistema |

---

## Estrutura do dist

```
dist/.claude/
├── agents/
│   ├── orchestrator.md              # Meta-orchestrator (Tier 1)
│   ├── orchestrator-sdd.md          # Phase orchestrator — Spec & Design
│   ├── orchestrator-dev.md          # Phase orchestrator — Implementation
│   ├── orchestrator-review.md       # Phase orchestrator — QA & Approval
│   ├── orchestrator-test.md         # Phase orchestrator — Testing
│   ├── spec/                        # Spec phase workers
│   ├── dev/                         # Dev phase workers
│   └── reverse-spec/                # Reverse engineering workers
├── skills/
│   ├── orch-log/                    # append, read, verify (log interface)
│   ├── orch-state/                  # reduce, snapshot, current_phase (state)
│   ├── orch-report/                 # emit (worker→log, guard-railed)
│   ├── orch-infra/                  # preflight, integrity, circuit check
│   ├── phase-sdd-rules/             # SDD worker routing + exit criteria
│   ├── phase-dev-rules/             # Dev worker routing + exit criteria
│   ├── phase-review-rules/          # Review worker routing + exit criteria
│   ├── phase-test-rules/            # Test worker routing + exit criteria
│   ├── u-spec-*/                    # Spec domain skills
│   ├── u-be-*/                      # Backend domain skills
│   ├── u-fe-*/                      # Frontend domain skills
│   ├── u-shared-templates/          # Schemas e templates compartilhados
│   └── u-spec-templates/            # Templates de spec (.spec.md, .back.md, etc.)
├── commands/
│   ├── u-spec.md                    # Entry point: inicia/retoma SDD phase
│   ├── u-dev.md                     # Entry point: inicia Dev phase
│   ├── u-orchestrator.md            # Entry point: retoma/avança qualquer workflow
│   ├── u-improve.md                 # Entry point: melhoria incremental
│   ├── u-reverse-spec.md            # Entry point: reverse engineering
│   ├── u-fe-validate.md             # Utilitário: validação avulsa de frontend
│   ├── u-cleanup.md                 # Utilitário: GC/purge de runtime .orch
│   └── u-doc-cleanup.md             # Utilitário: remoção de ruído em docs
├── hooks/
│   ├── on_subagent_stop.py          # Sintetiza task_failed para workers que morrem silenciosamente
│   └── on_stop.py                   # Persiste métricas ao encerrar sessão
├── scripts/
│   ├── dlq_triage.py                # Categoriza tarefas em DLQ por tipo de falha
│   └── evaluate_circuit.py          # Avalia estado do circuit breaker
├── lib/
│   └── orch_core.py                 # Biblioteca compartilhada: toda lógica de estado
└── ESCALATION_CODES.md              # Referência de todos os códigos de escalação
```

---

## Arquitetura em dois tiers

```
Usuário
  │
  ▼
[orchestrator]          ← Tier 1: Meta-Orchestrator
  │ spawna
  ▼
[orchestrator-sdd]      ← Tier 2: Phase Orchestrators
[orchestrator-dev]
[orchestrator-review]
[orchestrator-test]
  │ spawnam
  ▼
[workers]               ← Executores concretos
  │ emitem via orch-report
  ▼
[log.jsonl]             ← Fonte única de verdade
```

**Regra de ouro:** todo estado é derivado do log. Nenhum componente guarda estado próprio. Crash e recovery são triviais — releia o log.

---

## Fases do workflow padrão

| Fase | Order | Objetivo | Human gate? |
|------|-------|---------|-------------|
| `sdd` | 1 | Escrever e validar todas as specs técnicas | Sim — confirmação antes do primeiro dispatch |
| `dev` | 2 | Implementar os task contracts do backlog | Não — totalmente autônomo |
| `review` | 3 | QA das entregas; aprovação humana antes de avançar | Sim — aprovação obrigatória |
| `test` | 4 | Executar testes; escalate se falhas | Condicional — só se testes falham |

---

## Invariantes arquiteturais (nunca violar)

| # | Invariante |
|---|------------|
| P1 | Log é a verdade. Todo estado é derivado. |
| P2 | Orchestrator é função pura do log. Mesmo log → mesmas decisões. |
| P3 | Append-only. Correções via novos eventos. Nunca edita eventos. |
| P4 | Idempotência por `(task_id, attempt, event_type)`. Duplicatas rejeitadas. |
| P5 | Ordenação determinística. Ties resolvidos por `(priority desc, seq asc)`. |
| P6 | Least privilege. Workers têm apenas `orch-report`. |
| P7 | Robustez via hooks. Garantias críticas fora do LLM. |
| P8 | Evidência obrigatória. Toda decisão cita os seqs que a justificam. |
| P9 | Uma fase por task. Cada task tem exatamente um campo `phase`. |
| P10 | Transições auditáveis. `phase_transitioned` é sempre um evento. |
| P11 | Exit criteria em código testável, não em prompts. |
| P12 | Current phase derivada do log. Nunca armazenada fora dele. |
