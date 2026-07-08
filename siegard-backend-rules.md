# REGRAS SIEGARD — ESPECIFICAÇÃO E DESENVOLVIMENTO DE BACKEND

> Documento único e autossuficiente. Cada regra é objetiva e verificável. Onde houver `CLAUDE.md` no projeto-alvo, as convenções dele têm precedência sobre os defaults aqui declarados.

---

## PARTE A — ESPECIFICAÇÃO DE BACKEND

### A1. Modelagem de dados
- **A1.1** Toda entidade declara explicitamente a estratégia de chave primária (`uuid`, `auto-increment` ou composta).
- **A1.2** Toda FK declara explicitamente a regra `on-delete` (`CASCADE`, `SET NULL` ou `RESTRICT`).
- **A1.3** Todo campo não-PK usado em cláusula `WHERE` tem justificativa de índice documentada.
- **A1.4** Valores de enum são listados explicitamente — proibido `"etc."` ou lista aberta.
- **A1.5** Cada coluna declara se é `nullable` ou `required`.
- **A1.6** Se entidades podem ser desativadas, a estratégia de soft-delete é declarada.
- **A1.7** Com soft-delete, o endpoint usa `PATCH` ou `POST` — nunca `DELETE`.
- **A1.8** Com hard-delete, o endpoint `DELETE` é justificado em uma Business Rule (irreversível por design).

### A2. Regras de negócio (Business Rules)
- **A2.1** Cada BR referencia o Use Case que a origina (`UC-NN`).
- **A2.2** Cada BR especifica a camada de validação: `API gateway` | `service` | `repository`.
- **A2.3** Cada violação de BR tem código de erro registrado no catálogo global de erros.
- **A2.4** Cada BR documenta seus edge cases (comportamento nos valores de fronteira).
- **A2.5** Quando duas BRs podem se contradizer, a resolução de conflito é documentada.
- **A2.6** Se um conceito de domínio admite múltiplas implementações que podem crescer (ex.: método de pagamento, canal de notificação, formato de exportação), a estratégia de extensão é declarada: `polymorphism` | `strategy pattern` | `closed enum + factory`. Se for fechado (não crescerá), declarar explicitamente. **Nunca deixar implícito.**

### A3. Máquina de estados
- **A3.1** Todos os estados são enumerados — sem estado "outro" implícito.
- **A3.2** Todas as transições válidas mapeadas no formato `From → Trigger → To`.
- **A3.3** Condições de guarda explícitas para cada transição.
- **A3.4** Estados terminais identificados.
- **A3.5** Comportamento em transição inválida documentado (rejeitar em silêncio ou lançar erro).

### A4. Payload de eventos
- **A4.1** Domínio produtor identificado.
- **A4.2** Domínios consumidores listados.
- **A4.3** Campos do schema do payload tipados (JSON Schema ou equivalente TypeScript).
- **A4.4** Semântica de entrega declarada (`at-least-once` ou `exactly-once`).
- **A4.5** Estratégia de versionamento do evento declarada (se persistido ou compartilhado entre serviços).

### A5. Quality gate da especificação
- **A5.1** Uma `.back.md` só é liberada para o Validator quando todos os itens aplicáveis das seções A1–A4 estiverem preenchidos.
- **A5.2** Seção não aplicável ao domínio pode ser omitida com nota explícita: `N/A — no domain events`.

---

## PARTE B — DESENVOLVIMENTO DE BACKEND

### B1. Precedência de configuração
- **B1.1** Antes de criar qualquer arquivo, extrair do `CLAUDE.md`: estrutura de pastas, convenções de nomes, framework de testes, logger configurado, padrão de erro custom, variáveis de ambiente já definidas, ORM/ODM, `validation_library`, `di_strategy`, `pagination.strategy`.
- **B1.2** Se o `CLAUDE.md` não cobrir um ponto, usar o default deste documento e registrar a decisão no arquivo de entrega.

### B2. Princípios de engenharia
- **B2.1** Seguir CLEAN Code e SOLID rigorosamente.
- **B2.2** Aplicar design patterns quando pertinentes (Factory, Strategy, Repository, Observer…).
- **B2.3** Preferir composição a herança.
- **B2.4** Aplicar Dependency Injection para toda dependência externa (banco, APIs, serviços).
- **B2.5** Preferir funções puras e imutabilidade.
- **B2.6** Cada função/método público tem responsabilidade única e clara.
- **B2.7** Priorizar simplicidade: módulos pequenos e focados; evitar complexidade acidental, respeitar YAGNI, evitar abstrações prematuras.

### B3. Convenções de nomenclatura
> Precedência do `CLAUDE.md`.

| Elemento | Padrão | Exemplo |
|---|---|---|
| Arquivos | kebab-case | `user-profile.service.ts` |
| Classes | PascalCase | `UserProfileService` |
| Funções/métodos | camelCase | `getUserById()` |
| Constantes | SCREAMING_SNAKE | `MAX_RETRY_ATTEMPTS` |
| Variáveis | camelCase | `isActive` |
| Interfaces | IPascalCase | `IUserRepository` |
| Types | PascalCase | `CreateUserInput` |
| DTOs | PascalCaseDTO | `CreateUserDTO` |
| Enums | PascalCase (membros UPPER_SNAKE) | `UserRole.ADMIN` |
| Tabelas DB | snake_case (plural) | `user_profiles` |
| Colunas DB | snake_case | `created_at` |
| Rotas de API | kebab-case (plural) | `/api/v1/user-profiles` |
| Env vars | SCREAMING_SNAKE | `DATABASE_URL` |
| Testes | mesmo nome + `.spec`/`.test` | `user-profile.service.spec.ts` |

### B4. Qualidade de código TypeScript
- **B4.1** TypeScript estrito: `strict: true`, `noImplicitAny`, `strictNullChecks`.
- **B4.2** Proibido `any` — usar `unknown`, generics ou tipos explícitos.
- **B4.3** Evitar `as`; usar type guards e narrowing.
- **B4.4** Assinaturas públicas com tipos explícitos (parâmetros e retorno).
- **B4.5** `readonly` para propriedades que não devem ser reatribuídas.
- **B4.6** Preferir `const enum` ou union types a enums convencionais.
- **B4.7** Usar padrão `Result<T, E>` / Either para operações que podem falhar (evitar `throw` em lógica de negócio).
- **B4.8** Funções com ~30 linhas no máximo; extrair lógica complexa em helpers nomeados.
- **B4.9** Máximo de 3 parâmetros por função — usar objeto acima disso.
- **B4.10** Sem números/strings mágicos — extrair constantes nomeadas.

### B5. Arquitetura
- **B5.1** Arquitetura em camadas (Layered/Clean) ou Hexagonal quando aplicável.
- **B5.2** Camadas mínimas: `Controller → Service/UseCase → Repository/Gateway`.
- **B5.3** Regras de negócio isoladas de frameworks e I/O.
- **B5.4** Ports & Adapters para integrações externas (banco, filas, APIs de terceiros).
- **B5.5** Entidades de domínio não dependem de bibliotecas externas.
- **B5.6** Cada módulo/domínio é autossuficiente — sem dependências circulares.
- **B5.7** Separar claramente configuração, bootstrap e lógica de aplicação.

#### SRP dentro de uma classe de serviço
- **B5.8** Se os métodos de um serviço referenciam dois ou mais domínios de substantivos distintos, viola SRP → dividir em um serviço por conceito de domínio.
- **B5.9** Adicionar responsabilidade = nova classe de serviço, nunca um novo método na classe existente.

#### OCP no design da feature
- **B5.10** Conceito extensível declarado (spec/`CLAUDE.md`) → interface + uma classe por variante + factory. Nova variante = novo arquivo, sem modificar existentes.
- **B5.11** Variantes fechadas declaradas → `switch`/lookup map é correto; não superengenheirar.
- **B5.12** Sem declaração na spec → perguntar antes. Default: closed enum se as variantes forem estáveis no domínio (ex.: `OrderStatus`); Strategy se forem pontos de integração (ex.: gateways de pagamento, storage).
- **B5.13** **Violação a evitar:** `switch(type)` dentro de um serviço quando a spec declara o conceito extensível.

#### ISP no design da interface
- **B5.14** Antes de finalizar uma interface com 4+ métodos, listar consumidores e verificar se cada um usa todos os métodos. Consumidores usam subconjuntos disjuntos → dividir em uma interface por necessidade.

### B6. Dependency Injection
- **B6.1** Default: `manual-factory` (ler `di_strategy` do `CLAUDE.md`; alternativas: `nestjs-ioc`, `inversify`).
- **B6.2** Construtores recebem **interfaces**, nunca classes concretas.
- **B6.3** Nunca instanciar dependência dentro de um serviço — receber por construtor.
- **B6.4** Nunca `new SomeService()` inline em controller ou rota.
- **B6.5** Factory functions são o único lugar onde `new` conecta dependências (`src/factories/[resource].factory.ts` na estratégia manual-factory).

### B7. Padrão DTO / Validação
- **B7.1** Default: **Zod** (ler `validation_library` do `CLAUDE.md`; alternativas: `class-validator`, `joi`).
- **B7.2** Nome do schema = `PascalCase + "Schema"`; tipo = `PascalCase + "Dto"` ou `"Response"`.

| Uso | Schema | Tipo | Arquivo |
|---|---|---|---|
| Create | `Create{Resource}Schema` | `Create{Resource}Dto` | `create-{resource}.dto.ts` |
| Update | `Update{Resource}Schema` | `Update{Resource}Dto` | `update-{resource}.dto.ts` |
| Response | `{Resource}ResponseSchema` | `{Resource}Response` | `{resource}-response.dto.ts` |
| Query | `List{Resource}QuerySchema` | `List{Resource}Query` | `list-{resource}-query.dto.ts` |

- **B7.3** Validar na fronteira (rota/middleware) — o serviço recebe DTO já tipado, nunca `req.body` cru.
- **B7.4** DTOs ficam em `src/dto/` ou `src/modules/{domain}/dto/` — nunca inline em controllers.
- **B7.5** Não redefinir schema em testes — importar de `src/dto/`.

### B8. Estrutura de pastas (default `layered`)
```
src/
├── routes/          controllers/     services/      repositories/
├── models/          dto/             middleware/    migrations/
├── config/          types/           factories/     utils/
└── __tests__/  (integration/  unit/  — espelha src/)
```
- **B8.1** `src/types/pagination.ts` (`PaginatedResponse<T>`, metas) e `src/types/api.ts` ficam sempre na raiz `src/types/` — nunca duplicados por módulo.
- **B8.2** Alternativa `folder_structure: modules` → `src/modules/{domain}/{controller,dto,service,repository,entity,factory}/`; tipos compartilhados permanecem na raiz.

### B9. Tratamento de erros
- **B9.1** Usar tipos de erro explícitos — evitar `throw new Error("something went wrong")`.
- **B9.2** Diferenciar erros operacionais (esperados, ex.: recurso não encontrado) de erros de programação (bugs).
- **B9.3** Nunca silenciar erro com `catch {}` vazio.
- **B9.4** Propagar contexto: `throw new AppError("createUser failed", { cause: err })`.
- **B9.5** Camadas de erro: Controller mapeia erro→status HTTP; Service lança erros de negócio (NotFound/Conflict/Validation); Repository lança erros de dados (Connection/Query); Middleware error handler captura não-tratados e formata resposta padrão.
- **B9.6** Toda classe de erro custom herda de `Error` e inclui: `name`, `message`, `statusCode`, `context`.
- **B9.7** Logar erros com contexto suficiente (correlation ID, input relevante, stack trace).
- **B9.8** Nunca expor stack trace ou detalhe interno ao cliente em produção.
- **B9.9** Formato padrão de resposta de erro:
```json
{ "error": { "code": "RESOURCE_NOT_FOUND", "message": "User with ID 123 not found", "details": {} } }
```

### B10. Design de API
- **B10.1** RESTful por padrão; documentar com OpenAPI/Swagger.
- **B10.2** Versionamento por prefixo de URL: `/api/v1/`.
- **B10.3** Status HTTP corretos: 201 criação, 204 delete sem body, 422 falha de validação, 404 não encontrado, 409 conflito, 429 rate limit.
- **B10.4** Validar input na fronteira via DTOs de `src/dto/` — nunca `req.body` cru em serviços.
- **B10.5** Respostas paginadas usam `PaginatedResponse<T>` — nunca formatos ad-hoc `{ data, meta }`.
- **B10.6** Idempotência para operações sensíveis (POST com idempotency key).

### B11. Paginação
- **B11.1** Default: `offset` (ler `pagination.strategy` do `CLAUDE.md`; alternativa: `cursor`).
- **B11.2** Tipos canônicos sempre em `src/types/pagination.ts`:
```typescript
interface OffsetPaginationMeta { page: number; limit: number; total: number; pages: number; }
interface CursorPaginationMeta { next_cursor: string | null; has_more: boolean; limit: number; }
interface PaginatedResponse<T> { data: T[]; meta: OffsetPaginationMeta | CursorPaginationMeta; }
```
- **B11.3** Lista vazia → `PaginatedResponse<T>` com `data: []`, **nunca** `null`.
- **B11.4** `default_limit` e `max_limit` vêm do `CLAUDE.md` — nunca hardcoded.
- **B11.5** `limit` acima de `max_limit` → 400 com `error.code: PAGINATION_LIMIT_EXCEEDED`.
- **B11.6** `pages` (offset) sempre computado `Math.ceil(total / limit)` — nunca omitido nem hardcoded.
- **B11.7** `offset` para listas admin, relatórios, exports (default); `cursor` para feeds, timelines, streams em tempo real.

### B12. Proibições explícitas
- **B12.1** `console.log` em código de produção (usar o logger configurado).
- **B12.2** Credenciais, tokens ou URLs de ambiente hardcoded.
- **B12.3** `any` em TypeScript.
- **B12.4** `as` sem type guard/narrowing correspondente.
- **B12.5** Imports não usados.
- **B12.6** Código comentado (apagar, não comentar).
- **B12.7** `TODO`/`FIXME` sem referência a Task Contract/issue (permitido `// TODO(TC-12): ...`).
- **B12.8** Alterar código fora do escopo do Task Contract sem criar um TC técnico separado.
- **B12.9** SQL cru sem parametrização (risco de injeção).
- **B12.10** Segredos em logs ou mensagens de erro retornadas ao cliente.
- **B12.11** Migração destrutiva sem rollback (sempre `up` e `down`).

---

## PARTE C — TESTES E QUALIDADE (compartilhado Dev/QA)

### C1. Testes obrigatórios por tipo de Task Contract
| Tipo | O que entregar |
|---|---|
| **feature** | Unit (services/utils) + Integration (rota request→response) + teste de validação de input |
| **refactoring** | Testes dos comportamentos modificados + atualização dos testes afetados; regressão obrigatória |
| **refactoring (structure-only)** | Testes de comportamentos preservados devem continuar passando; não adicionar lógica sem teste |
| **bugfix** | Teste de regressão: reproduz o bug antes do fix e confirma que passa depois |

### C2. Critérios de qualidade de teste
- **C2.1** Cada critério de aceite tem ≥1 teste mapeado (ausência = BUG High).
- **C2.2** Cada edge case tratado em código tem teste (ausência = BUG Medium).
- **C2.3** Testar **comportamento**, não implementação: `expect(response.body.data.name).toBe("John")` em vez de `expect(repo.findById).toHaveBeenCalled()`.
- **C2.4** Testes de integração cobrem sucesso **e** erro (4xx/5xx + verificação do body).
- **C2.5** Testes isolados: cada um limpa seu estado (truncate/rollback/reset de mocks); sem dependência de ordem.
- **C2.6** Seguir AAA (Arrange → Act → Assert).
- **C2.7** Nomes descritivos: `should return error when email is already registered`.
- **C2.8** Mocks/stubs apenas em fronteiras (I/O, banco, APIs externas) — nunca em lógica de negócio.
- **C2.9** Proibido teste tautológico (`expect(true).toBe(true)`).
- **C2.10** Proibido `TODO`/`FIXME` sem referência de issue/TC no código commitado.
- **C2.11** Proibido lint-disable (`eslint-disable`, `# noqa`, `// nolint`) sem comentário justificando.

### C3. Checklist universal de edge cases
- **Input:** null/undefined, string vazia `""`, zero/negativo, lista vazia `[]`, valores de fronteira, caracteres especiais/unicode, payload acima do tamanho máximo.
- **Segurança/auth:** sem token → 401; token expirado → 401; token válido sem permissão → 403; tentativa de SQL injection; acesso a recurso de outro usuário → 403/404; headers obrigatórios ausentes.
- **Estado do sistema:** não encontrado → 404 (não 500); duplicado (unique constraint) → 409; estado inválido para a operação → 422; concorrência (duas requisições simultâneas no mesmo recurso).
- **Integração/infra:** banco indisponível → erro tratado, não crash; serviço externo com erro/timeout → fallback ou erro claro; resposta em formato inesperado → erro tratado; rollback de migração funciona.
- **Padrões de tratamento:** null/undefined na camada de validação; lista vazia → `data: []`; não encontrado → `NotFoundError` → 404; duplicado → 409; transação parcial → rollback; payload grande → limite no middleware; rate limit → 429 com `Retry-After`.

### C4. Classificação de severidade de bug
| Severidade | Critério | Impacto no TC |
|---|---|---|
| **Critical** | Crash, corrupção de dados, brecha de segurança, SQL injection possível | Rejeita + bloqueia demais testes |
| **High** | Critério de aceite não atendido, fluxo principal quebrado, 500 em caso esperado | Rejeita o TC |
| **Medium** | Edge case não tratado, mensagem de erro pobre, campo de resposta incorreto | Aprova com ressalva obrigatória |
| **Low** | Inconsistência de nome, log desnecessário, doc incompleta | Registra, não bloqueia |

### C5. Falsificação de causa-raiz (para timeouts/flakes/performance)
- **C5.1** Antes de atribuir causa a um timeout/flake/performance: reproduzir isolado vs. sob carga; variar o knob relevante (timeout, `--maxWorkers`, ordem/seed); registrar em `root_cause.evidence` e `root_cause.confidence`.
- **C5.2** `confidence: high` só quando a causa foi reproduzida/verificada; `low` quando apenas inferida por leitura.
- **C5.3** Heurística: teste que estoura no suite completo mas passa isolado ⇒ suspeitar de contenção/ordem/estado-compartilhado, não do código sob teste, até prova em contrário.
- **C5.4** Ao consumir finding com `confidence` abaixo de `high`: reproduzir antes de aplicar o fix sugerido; não aplicar verbatim.

### C6. Quality BUGs específicos (DI / DTO / Paginação)
- DI: instanciar dependência no construtor do serviço → **Medium**; ausência de factory com `di_strategy: manual-factory` → **Medium**; construtor recebe classe concreta havendo interface → **Low**.
- DTO: `req.body` direto ao serviço sem validação → **High**; nome de arquivo DTO fora da convenção → **Low**; schema redefinido inline em teste → **Low**.
- Paginação: retornar `null` em vez de `{ data: [], meta }` → **High**; `meta.pages` ausente/hardcoded → **Medium**; `PaginatedResponse` redefinido por módulo → **Medium**; `limit` não validado contra `max_limit` → **Medium**.

---

## PARTE D — GIT E ENTREGA (fluxo de desenvolvimento)

### D1. Branch e commits
- **D1.1** Uma branch por Task Contract, a partir de `main`: `feat/TC-XX` (feature/improvement), `fix/TC-XX` (fix de QA), `refactor/TC-XX` (refactoring).
- **D1.2** Trabalhar exclusivamente na branch do TC — nunca commitar direto em `main`; nunca fazer merge em `main` (integração é responsabilidade do orquestrador).
- **D1.3** Remover arquivos scratch/backup (ex.: `*.tcNN`) antes de finalizar.
- **D1.4** Prefixo semântico obrigatório no commit: `feat(TC-XX):`, `fix(TC-XX):`, `refactor(TC-XX):`, `test(TC-XX):`, `docs(TC-XX):`, `migration(TC-XX):`.
- **D1.5** Preferir commits por camada quando o TC abrange múltiplos módulos.

### D2. Fluxo obrigatório antes de codificar
1. Ler o Task Contract completo (narrativa + todos os critérios de aceite).
2. Ler os arquivos listados como dependências da entrega anterior.
3. Mapear os contratos de interface que o TC vai tocar/criar.
4. Confirmar que está na branch/worktree do TC.
5. Escrever o plano de implementação como comentário no topo do primeiro arquivo.
6. Só então implementar.
7. Escrever testes.

- **D2.1** Se surgir ambiguidade bloqueante → parar e registrar a ambiguidade no arquivo de entrega.

### D3. Verificação de dependências de infraestrutura
- **D3.1** Antes de implementar, mapear todos os serviços/recursos de infra que o TC exige (banco, filas, cache, serviços de terceiros, storage).
- **D3.2** Classificar cada dependência: **Available** (configuração encontrada e funcional), **Partial** (existe, configuração incompleta), **Missing** (não encontrada).
- **D3.3** Gerar relatório de pendências de infra sempre que houver ≥1 dependência `Partial` ou `Missing`.

### D4. Checklist de pré-entrega
- [ ] Todos os critérios de aceite endereçados (inclusive os não implementados, com justificativa).
- [ ] Nenhuma proibição explícita violada.
- [ ] Edge cases obrigatórios tratados e documentados.
- [ ] Cada critério de aceite tem ≥1 teste correspondente.
- [ ] Cada edge case tratado em código tem teste.
- [ ] Verificação de dependências de infra executada.
- [ ] Arquivo de entrega gerado.
- [ ] Trabalhando na branch correta com commits no padrão semântico.
- [ ] Branch contém apenas commits locais (push é do orquestrador após aprovação do QA).
- [ ] Migrações incluem `up` e `down`.
- [ ] Queries parametrizadas (sem concatenação de string em SQL).
- [ ] Sem segredos em logs ou respostas de erro.
- [ ] Se for fix pós-QA: apenas os bugs do relatório foram alterados — comportamentos aprovados intactos.

---

**Fim das regras.** Todas as seções são autossuficientes; ajuste os defaults (`di_strategy`, `validation_library`, `pagination.strategy`, `folder_structure`, `max_limit`, logger) via `CLAUDE.md` do projeto-alvo.
