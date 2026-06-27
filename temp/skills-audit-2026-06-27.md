# Auditoria de Skills — Siegard Code v2

**Data:** 2026-06-27
**Escopo:** 39 skills em `dist/.claude/skills/` + grafo de referências contra `agents/`, `commands/`, `scripts/`, `tests/`, `hooks/`.
**Critério:** padrão *enterprise, high-grade*. Cada achado cita evidência primária verificada.
**Método:** grafo de referências por `grep` (refs fora do próprio diretório da skill) + verificação direta dos achados de alta severidade.

---

## A. Skills órfãs / não utilizadas (refs=0)

| Skill | invocable | Alcançável? | Veredito |
|---|---|---|---|
| **u-bug-investigator** | `false` | ❌ Por nenhum caminho | **Dead code + frontmatter contraditório** |
| **u-worker-compliance** | `false` | ❌ runtime (só citada em 1 teste de parse YAML) | **Gate de compliance não cabeado** |
| **u-context-enricher** | `true` | ⚠️ só via Skill direto pelo usuário | Utilitário avulso, desconectado do fluxo |
| **u-be-review** | `true` | ⚠️ só via Skill direto | Anuncia comando `/u-be-review` inexistente |
| **u-fe-review** | `true` | ⚠️ só via Skill direto | Sobrepõe `/u-fe-validate` (que está quebrado) |
| **phase-_example** | `false` | ➖ scaffold intencional | **Aceitável por design** (template de extensão) |

### Detalhe dos casos graves

- **`u-bug-investigator`** — `user-invocable: false` (`SKILL.md:4`) **e** zero referências em todo o repo (commands/agents/skills/tests/docs). É inalcançável. A descrição é escrita para auto-disparo — *"Trigger this skill whenever a user is puzzled... When in doubt — use this skill"* (`SKILL.md:3`), o que `user-invocable: false` proíbe. O caminho de bug foi conscientemente unificado em `u-improve` (*"There is no separate bug pathway"*), deixando esta skill como resíduo. Ainda há aspas soltas envolvendo a `description`.

- **`u-worker-compliance`** — valida compliance de protocolo W01–W06 dos workers e diz *"run ... as a review-phase gate"* (`SKILL.md:3`), mas **nada a executa**: `phase-review-rules` não a referencia, e a única menção em todo o repo é em `tests/test_layer_hard_minimal_yaml.py` (fixture de parsing, não um gate). Um validador de compliance que ninguém roda dá falsa sensação de garantia.

---

## B. Duplicações e sobreposições

| # | Skills | Veredito | Evidência |
|---|---|---|---|
| B1 | `u-fe-review` × comando `/u-fe-validate` | **Redundância** — `/u-fe-validate` é subconjunto de `u-fe-review` | Ambos consomem `u-fe-standards §2/§3`; `u-fe-review` adiciona §4 anti-patterns + §5 a11y + `--fix` |
| B2 | `u-fe-review §1–§3` × `u-fe-standards §2.2/§3` | **Risco de drift** | `u-fe-review` inlina thresholds que já vivem em `u-fe-standards` (só declara "não redefinir" para §4) |
| B3 | `u-context-enricher` × `u-spec-triage`/`u-ui-brief`/`u-improve` | **Sobreposição conceitual, mecânica baixa** | Todas "estruturam pedido vago"; só `u-context-enricher` não emite artefato tipado do pipeline → utilitário distinto, não redundante |
| B4 | `u-fe-review` × `u-ui-design` (audit) | **Aceitável** | Registry visual único em `u-ui-design/anti-patterns.md`; ambos referenciam, não duplicam |
| B5 | `u-be-review` × `u-be-qa-docs` | **Limpo** | `u-be-review` referencia `u-be-qa-docs` como fonte (CR-TST), não reimplementa |

> Os quartetos `u-{be,fe}-{development,standards,templates,qa-docs}` **não** são duplicação — são matriz deliberada com fonte única (`u-*-standards`), corretamente referenciada (ex.: `u-be-qa-docs:31` aponta para `standards/SKILL.md`). Esse é o padrão correto que o resto deveria seguir.

---

## C. Defeitos que ferem o princípio enterprise

| # | Severidade | Defeito | Evidência |
|---|---|---|---|
| C1 | 🔴 ALTA | **Comando `/u-fe-validate` referencia skill inexistente** | `commands/u-fe-validate.md:59` lê `skills/u-fe-validate/SKILL.md` → `ls`: **No such file**. Comando publicado que não executa como escrito |
| C2 | 🔴 ALTA | **Contrato `delivery` divergente em 4 lugares** | Schema canônica exige `task_id` (`delivery.schema.yaml:14`) e `phases.md` idem; mas `u-be-templates/delivery.md:10` e `u-fe-templates/delivery.md:10` emitem `task: TC-XX` + `status:` (não existem na schema). Dois `SKILL.md` reivindicam "single source of truth" sobre o mesmo envelope. Viola *contracts over interpretation* |
| C3 | 🔴 ALTA | **u-bug-investigator inalcançável + frontmatter auto-contraditório** | ver seção A |
| C4 | 🟠 MÉDIA | **u-worker-compliance: gate de compliance não enforçado** | ver seção A |
| C5 | 🟠 MÉDIA | **u-be-review anuncia comando inexistente** | `SKILL.md:5` `invocation: /u-be-review ...`; não há `commands/u-be-review.md`. Assimetria FE/BE |
| C6 | 🟠 MÉDIA | **qa-report não emite `findings[].root_cause`** que a schema marca como obrigatório | `qa-verdict.schema.yaml` define `findings[].root_cause{confidence,evidence}`; `u-{be,fe}-templates/qa-report.md` usam bloco de texto livre `### BUG-XX` |
| C7 | 🟡 BAIXA | **u-context-enricher: refs penduradas + nota de install contraditória** | `SKILL.md:336` cita `evals/` inexistente; `:14` manda instalar em `~/.claude/skills/...`, conflitando com o modelo manual-copy de `dist/` |
| C8 | 🟡 BAIXA | **Descrições rasas em skills de spec** | `u-spec-writing`/`u-spec-review`/`u-spec-validation`/`u-spec-back-writing`/`u-reverse-spec*` têm `description` no estilo *"Specification writing skill - OpenAPI..."* — não declaram *quem consome*, contrariando o Frontmatter standard do `CLAUDE.md` |

### Calibração importante (C2)

O gate determinístico `check_all_deliveries_qa_ready.py` faz apenas regex de `qa_ready: true` (`:55`) — portanto a divergência `task` vs `task_id` **não quebra a execução em runtime**. O defeito é de **consistência de contrato**: a engine documenta `task_id` na schema canônica e em `phases.md`, mas os templates que os workers copiam usam `task`. Para um framework AI-FIRST que prega *contracts over interpretation* e fonte única, duas definições divergentes do mesmo envelope é defeito real.

---

## Recomendações priorizadas

### P0 — corrigir antes de publicar como enterprise

1. **C1**: restaurar `u-fe-validate/SKILL.md` **ou** reapontar o comando para `u-fe-review` (provável intenção). Decisão de design B1: manter UM ponto de entrada por stack — recomendado o comando delegar ao skill `u-fe-review` e aposentar a referência morta.
2. **C2**: colapsar `delivery` em fonte única (`u-shared-templates/delivery.schema.yaml`), padronizar a chave (`task_id`) e gerar os templates BE/FE a partir dela. Remover o claim duplo de "single source of truth".
3. **C3**: decidir `u-bug-investigator` — promover a `user-invocable: true` como diagnóstico standalone (e wirar um `/u-bug-report`), **ou** removê-la. Em qualquer caso, eliminar a contradição da frontmatter.

### P1

4. **C4**: cabear `u-worker-compliance` (`check_worker.py`) num teste de `tests/` e/ou no gate da fase review — ou removê-la.
5. **C5**: criar `/u-be-review` (simetria com FE) ou remover a linha `invocation:` que mente.
6. **C6**: alinhar `qa-report.md` ao `findings[].root_cause` da schema.

### P2 (polimento)

7. **B2**: remover thresholds inline de `u-fe-review`.
8. **C7**: corrigir refs penduradas e nota de install de `u-context-enricher`.
9. **C8**: enriquecer descrições rasas (declarar consumidor).
10. Decidir destino de `u-context-enricher` (integrar ao fluxo ou rotular explicitamente como utilitário avulso).

---

## Resumo executivo

Das 39 skills:
- **2 são dead code real**: `u-bug-investigator`, `u-worker-compliance`.
- **3 são utilitários alcançáveis mas desconectados**: `u-context-enricher`, `u-be-review`, `u-fe-review`.
- **1 órfã é intencional**: `phase-_example` (scaffold de extensão).

Há **1 comando quebrado** (`/u-fe-validate`) e **1 contrato crítico divergente** (`delivery`) — os dois que mais ferem o posicionamento enterprise. A matriz `u-*-standards/templates` está sã e é o modelo a replicar.

---

## Anexo — grafo de referências (refs fora do próprio diretório)

```
orch-cleanup            1     u-fe-development        5
orch-infra              5     u-fe-qa-docs            6
orch-log               12     u-fe-review             0  ← órfã (invocable)
orch-report            24     u-fe-standards          8
orch-state              9     u-fe-templates          5
phase-_example          0     u-handoff-validator     3
phase-dev-rules         2     u-improve              13
phase-review-rules      1     u-planning              2
phase-sdd-rules         2     u-reverse-spec-analysis 3
phase-test-rules        1     u-reverse-spec          6
u-be-development        3     u-shared-templates     12
u-be-qa-docs            8     u-spec-back-writing     1
u-be-review             0  ←  u-spec-globals         11
u-be-standards          4     u-spec-review           3
u-be-templates          4     u-spec-templates       10
u-bug-investigator      0  ←  u-spec-triage           8
u-context-enricher      0  ←  u-spec-validation       1
u-doc-cleanup           1     u-spec-writing          5
                              u-ui-brief              1
u-worker-compliance     0  ←  u-ui-design             8
```
