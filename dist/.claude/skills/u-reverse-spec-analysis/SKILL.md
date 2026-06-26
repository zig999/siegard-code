---
name: u-reverse-spec-analysis
description: Source code analysis patterns by stack/framework for identifying entities, endpoints, business rules, events, and UI structure. Used by the Reverse Spec Analyzer Agent.
user-invocable: false
---

# SKILL: Source Code Analysis for Reverse Engineering

## Purpose
Provide the Analyzer Agent with framework/stack-specific search patterns to extract structured information from existing source code.

---

## Stack Detection

### Step 1: Identify language and framework

Search for configuration files in the project root:

| File | Stack |
|------|-------|
| `package.json` | Node.js (analyze dependencies for framework) |
| `tsconfig.json` | TypeScript |
| `requirements.txt` / `pyproject.toml` / `Pipfile` | Python |
| `pom.xml` / `build.gradle` | Java/Kotlin |
| `go.mod` | Go |
| `Gemfile` | Ruby |
| `Cargo.toml` | Rust |
| `composer.json` | PHP |

### Step 2: Identify specific framework

**Node.js/TypeScript — via `package.json` dependencies:**

| Dependency | Framework | Context |
|------------|-----------|---------|
| `@nestjs/core` | NestJS | Backend |
| `express` | Express | Backend |
| `fastify` | Fastify | Backend |
| `hapi`, `@hapi/hapi` | Hapi | Backend |
| `koa` | Koa | Backend |
| `react`, `react-dom` | React | Frontend |
| `next` | Next.js | Frontend (or fullstack) |
| `vue` | Vue | Frontend |
| `nuxt` | Nuxt | Frontend (or fullstack) |
| `@angular/core` | Angular | Frontend |
| `svelte` | Svelte | Frontend |

**Python — via `requirements.txt` or `pyproject.toml`:**

| Dependency | Framework | Context |
|------------|-----------|---------|
| `django` | Django | Backend |
| `fastapi` | FastAPI | Backend |
| `flask` | Flask | Backend |
| `starlette` | Starlette | Backend |

**Java/Kotlin — via `pom.xml` or `build.gradle`:**

| Dependency | Framework | Context |
|------------|-----------|---------|
| `spring-boot` | Spring Boot | Backend |
| `quarkus` | Quarkus | Backend |

### Step 3: Identify database

| Indicator | Database |
|-----------|----------|
| `typeorm`, `@prisma/client`, `sequelize`, `knex` | Check config for type (PostgreSQL, MySQL, SQLite) |
| `mongoose`, `mongodb` | MongoDB |
| `@supabase/supabase-js` | Supabase (PostgreSQL) |
| `pg`, `mysql2`, `better-sqlite3` | PostgreSQL / MySQL / SQLite |
| `sqlalchemy`, `django.db` | Check config |
| `redis`, `ioredis` | Redis (cache/session) |

### Step 4: Identify state management (frontend)

| Indicator | Solution |
|-----------|----------|
| `zustand` | Zustand |
| `@reduxjs/toolkit`, `redux` | Redux |
| `jotai` | Jotai |
| `recoil` | Recoil |
| `pinia` | Pinia (Vue) |
| `vuex` | Vuex (Vue) |
| `@ngrx/store` | NgRx (Angular) |
| `React.createContext`, `useContext` | Context API |

### Step 5: Identify data fetching (frontend)

| Indicator | Solution |
|-----------|----------|
| `@tanstack/react-query`, `react-query` | React Query |
| `swr` | SWR |
| `axios` | Axios (manual) |
| `fetch(` | Fetch API (manual) |
| `@apollo/client`, `graphql` | Apollo/GraphQL |
| `trpc`, `@trpc/client` | tRPC |

---

## Search Patterns by Framework

### NestJS (Backend)

| What to search for | Search pattern (Grep) | Spec artifact |
|--------------------|----------------------|---------------|
| Controllers | `@Controller(` | endpoints -> openapi.yaml |
| GET routes | `@Get(` | paths GET |
| POST routes | `@Post(` | paths POST |
| PUT routes | `@Put(` | paths PUT |
| PATCH routes | `@Patch(` | paths PATCH |
| DELETE routes | `@Delete(` | paths DELETE |
| Entities | `@Entity(` | data model -> .back.md |
| DTOs | `class.*Dto` | schemas -> openapi.yaml |
| Services | `@Injectable()` + `class.*Service` | business logic -> .spec.md |
| Guards | `@Injectable()` + `implements CanActivate` | business rules -> .back.md |
| Interceptors | `@Injectable()` + `implements NestInterceptor` | cross-cutting behavior |
| Events | `@EventPattern(` or `EventEmitter` | events -> .back.md |
| Pipes/Validators | `@UsePipes(` or `class-validator` decorators | validations -> .back.md |
| Modules | `@Module(` | domains (grouping) |
| Enums | `enum.*Status` or `enum.*State` | state machine -> .back.md |
| Zod schemas | `z\.object\(` | schemas -> openapi.yaml |
| Zod type alias | `z\.infer<` | DTO type name → schema |
| Joi schemas | `Joi\.object\(` | schemas -> openapi.yaml |
| Repositories | `class.*Repository` or `@InjectRepository\(` | data access -> .back.md |

**Typical folder structure:**
```
src/
  {module}/
    {module}.controller.ts  -> endpoints
    {module}.service.ts     -> business rules
    {module}.module.ts      -> domain
    dto/                    -> schemas
    entities/               -> data model
    guards/                 -> authorization
    events/                 -> events
```

### Express (Backend)

| What to search for | Search pattern | Spec artifact |
|--------------------|---------------|---------------|
| Routes | `router\.(get\|post\|put\|patch\|delete)\(` | endpoints -> openapi.yaml |
| App routes | `app\.(get\|post\|put\|patch\|delete)\(` | endpoints -> openapi.yaml |
| Middleware | `(req, res, next)` or `function.*middleware` | cross-cutting |
| Models (Mongoose) | `mongoose\.Schema\(` or `new Schema\(` | data model -> .back.md |
| Models (Sequelize) | `sequelize\.define\(` or `Model\.init\(` | data model -> .back.md |
| Validation | `Joi\.` or `yup\.` or `zod\.` | validations -> .back.md |
| Error handler | `(err, req, res, next)` | errors -> error-codes.md |
| Zod schemas | `z\.object\(` | schemas -> openapi.yaml |
| Repositories | `class.*Repository` | data access -> .back.md |

**Typical folder structure (manual-factory pattern):**
```
src/
  routes/        ← route/endpoint definitions ([resource].routes.ts)
  controllers/   ← HTTP handlers ([resource].controller.ts)
  services/      ← business rules ([resource].service.ts)
  repositories/  ← data access ([resource].repository.ts)
  models/        ← entity/DB schema definitions ([resource].model.ts)
  dto/           ← input/output schemas (Zod, Joi, or class-validator)
  middleware/    ← auth, logging, error handler
  factories/     ← DI wiring ([resource].factory.ts)
  config/        ← application configuration
  types/         ← global types and interfaces
  __tests__/     ← tests (mirrors src/)
```
Module-based alternative: `src/modules/{domain}/` with `controller/`, `service/`, `repository/`, `dto/`, `entity/`, `factory/`.

### FastAPI (Backend)

| What to search for | Search pattern | Spec artifact |
|--------------------|---------------|---------------|
| Routes | `@(app\|router)\.(get\|post\|put\|patch\|delete)\(` | endpoints -> openapi.yaml |
| Models | `class.*\(BaseModel\)` | schemas -> openapi.yaml |
| ORM Models | `class.*\(Base\)` or `class.*\(SQLModel\)` | data model -> .back.md |
| Dependencies | `Depends\(` | middleware/guards |
| Exceptions | `HTTPException\(` | errors -> error-codes.md |
| Events | `@app\.on_event\(` | events -> .back.md |

### Django (Backend)

| What to search for | Search pattern | Spec artifact |
|--------------------|---------------|---------------|
| Models | `class.*\(models\.Model\)` | data model -> .back.md |
| Views | `class.*\(APIView\)` or `def.*\(request` | endpoints -> openapi.yaml |
| ViewSets | `class.*\(ModelViewSet\)` | CRUD endpoints -> openapi.yaml |
| Serializers | `class.*\(serializers\.Serializer\)` | schemas -> openapi.yaml |
| URLs | `path\(` or `url\(` | routes -> openapi.yaml |
| Signals | `@receiver\(` | events -> .back.md |
| Validators | `def validate_` | validations -> .back.md |

### Spring Boot (Backend)

| What to search for | Search pattern | Spec artifact |
|--------------------|---------------|---------------|
| Controllers | `@RestController` | endpoints -> openapi.yaml |
| Routes | `@(Get\|Post\|Put\|Patch\|Delete)Mapping` | paths -> openapi.yaml |
| Entities | `@Entity` | data model -> .back.md |
| Services | `@Service` | business logic -> .spec.md |
| Repositories | `@Repository` or `extends JpaRepository` | persistence -> .back.md |
| DTOs | `record.*Dto` or `class.*Dto` | schemas -> openapi.yaml |
| Validators | `@Valid` or `@Validated` | validations -> .back.md |
| Events | `ApplicationEvent` or `@EventListener` | events -> .back.md |
| Enums | `enum.*Status` | state machine -> .back.md |

### React / Next.js (Frontend)

| What to search for | Search pattern | Spec artifact |
|--------------------|---------------|---------------|
| Pages (Next pages) | Files in `pages/` or `app/` | features -> .feature.spec.md |
| Page components | `export (function\|const) [A-Z][a-zA-Z]*(Page\|Screen\|View)` | features -> .feature.spec.md |
| API calls | `fetch\(` or `axios\.(get\|post)` or `useQuery\(` | consumed domains |
| Custom hooks | `function use[A-Z]` or `const use[A-Z]` | state logic |
| State stores | `create\(` (zustand) or `createSlice\(` (redux) | state strategy -> feature.spec.md (§4 Requests, Order, and Cache) |
| Routes | `<Route` or `<Link` or `useRouter` or `useNavigate` | flows -> .flow.md |
| Forms | `<form` or `useForm\(` or `Formik` | validations -> .feature.spec.md (§5) |
| Error boundaries | `componentDidCatch` or `ErrorBoundary` | error handling -> .feature.spec.md (§6) |
| Loading states | `isLoading` or `isPending` or `<Skeleton` or `<Spinner` | UI states -> .feature.spec.md (§2) |

### Vue / Nuxt (Frontend)

| What to search for | Search pattern | Spec artifact |
|--------------------|---------------|---------------|
| Pages | Files in `pages/` (`.vue`) | features -> .feature.spec.md |
| Components | `defineComponent\(` or `<script setup>` | screen components |
| API calls | `useFetch\(` or `$fetch\(` or `axios` | consumed domains |
| State | `defineStore\(` (Pinia) or `new Vuex.Store` | state strategy -> feature.spec.md (§4 Requests, Order, and Cache) |
| Router | `createRouter\(` or `<RouterLink` | flows -> .flow.md |
| Guards | `beforeEach\(` or `beforeEnter` | navigation rules -> .flow.md |

### Angular (Frontend)

| What to search for | Search pattern | Spec artifact |
|--------------------|---------------|---------------|
| Components | `@Component\(` | screens/components |
| Services | `@Injectable\(` + `HttpClient` | consumed domains |
| Routes | `Routes` or `RouterModule` | flows -> .flow.md |
| Guards | `canActivate` or `CanActivateFn` | navigation rules |
| Forms | `FormGroup` or `FormControl` | validations -> .feature.spec.md (§5) |
| State | `@ngrx/store` or `BehaviorSubject` | state strategy -> feature.spec.md (§4 Requests, Order, and Cache) |

---

## ORM-Specific Entity Patterns

When the project uses an ORM other than TypeORM, use these patterns **instead of** `@Entity(` for entity detection.

### Prisma

Entities are defined in `schema.prisma`, not in TypeScript files. Use `Glob("**/schema.prisma")` to locate the file.

| What to detect | Search | Notes |
|----------------|--------|-------|
| Entity definition | `^model [A-Z]` in `*.prisma` | Each `model` block = one entity |
| Required field | Field line without `?` inside model block | e.g., `name String` |
| Optional field | Field line with `?` | e.g., `bio String?` |
| Default value | `@default\(` | e.g., `@default(now())`, `@default(uuid())` |
| Unique constraint | `@unique` or `@@unique\(` | Single-field or composite |
| Relationship | `@relation\(` | Read both sides to determine cardinality |
| Enum | `^enum [A-Z]` in `*.prisma` | State machine candidates |

Prisma type → OpenAPI type mapping: `String→string`, `Int→integer`, `Float→number`, `Boolean→boolean`, `DateTime→string(format:date-time)`, `Json→object`.

### Mongoose (Node.js)

| What to detect | Search pattern | Notes |
|----------------|---------------|-------|
| Schema definition | `new Schema\(` or `mongoose\.Schema\(` | — |
| Model registration | `mongoose\.model\(` | Entity name = first argument |
| Required field | `required: true` | Inside schema field definition |
| Unique constraint | `unique: true` | Inside schema field definition |
| Relationship | `ref:` | Cross-model reference (populate) |

### Sequelize (TypeScript class style)

| What to detect | Search pattern | Notes |
|----------------|---------------|-------|
| Model class | `class.*extends Model` | TypeScript Sequelize style |
| Column decorator | `@Column\(` | From `sequelize-typescript` |
| Primary key | `@PrimaryKey` | — |
| Relationship | `@HasMany\(` or `@BelongsTo\(` or `@HasOne\(` or `@BelongsToMany\(` | Relationship decorators |

---

## Analysis Rules

### Domain Identification

1. **Backend:** each module/folder with controller + service + model = 1 domain
2. **Frontend:** group by feature folder or by functional area (related pages)
3. **Domain names:** use `kebab-case`, derive from the module/folder name
4. If the project has no clear modular structure, group by primary entity

### Entity Identification

1. Class/interface with persisted fields = entity
2. Fields with `id`, `createdAt`, `updatedAt` = root entity (aggregate root)
3. Class embedded within another (nested) = value object
4. Entity with a `status` or `state` field (enum or union type) = state machine candidate

### Relationship Identification

Search for inter-entity relationships using ORM-specific patterns:

| ORM | Pattern | Cardinality |
|-----|---------|-------------|
| TypeORM | `@OneToMany\(` | 1:N |
| TypeORM | `@ManyToOne\(` | N:1 |
| TypeORM | `@OneToOne\(` | 1:1 |
| TypeORM | `@ManyToMany\(` + `@JoinTable\(` | N:N |
| Prisma | `@relation\(` in `*.prisma` | Read both field sides |
| Mongoose | `ref:` | Cross-model reference |
| Sequelize | `@HasMany\(`, `@BelongsTo\(`, `@HasOne\(`, `@BelongsToMany\(` | various |

For each relationship found: identify source entity, target entity, cardinality, and whether bidirectional. Record in `analysis-report.md` Entities → Relationships table.

### Field and Constraint Extraction

For each entity, extract fields and constraints using the active ORM/validation library:

#### TypeORM decorators
| What to extract | Pattern |
|----------------|---------|
| Column | `@Column\(` |
| Primary key | `@PrimaryGeneratedColumn\(` or `@PrimaryColumn\(` |
| Timestamps | `@CreateDateColumn\(`, `@UpdateDateColumn\(` |
| Nullable | `nullable: true` inside `@Column` |
| Unique | `unique: true` inside `@Column` |
| Default | `default:` inside `@Column` |
| Enum values | `enum:` inside `@Column` |

#### Zod schemas (default TS library)
| What to extract | Pattern | OpenAPI mapping |
|----------------|---------|----------------|
| Required string | `.string()` without `.optional()` | `type: string, required: true` |
| Optional | `.optional()` or `.nullable()` | `required: false` |
| Min/max length | `.min\(N\)`, `.max\(N\)` | `minLength`, `maxLength` |
| Email | `.email\(\)` | `format: email` |
| UUID | `.uuid\(\)` | `format: uuid` |
| Enum | `z\.enum\(\[` | `enum: [...]` |
| Default | `.default\(` | `default:` |

#### class-validator (NestJS)
| What to extract | Pattern | OpenAPI mapping |
|----------------|---------|----------------|
| Required | `@IsNotEmpty\(` | `required: true` |
| Optional | `@IsOptional\(` | `required: false` |
| Email | `@IsEmail\(` | `format: email` |
| UUID | `@IsUUID\(` | `format: uuid` |
| Length | `@MinLength\(`, `@MaxLength\(` | `minLength`, `maxLength` |
| Enum | `@IsEnum\(` | `enum: [...]` |

### Business Rule Identification

1. Validations in services/use-cases = BR candidate
2. Guards/middleware with authorization logic = BR candidate
3. `if/else` conditions in domain logic (not UI) = BR candidate
4. Each rule must be nameable and testable

### Error Identification

1. Search for `throw new.*Error\(` or `throw new.*Exception\(`
2. Search for `res\.status\(4` or `res\.status\(5` or `HttpException\(`
3. Search for error constants: `ERROR_`, `ERR_`, `error.code`
4. For each error: extract HTTP code, message, and context

### Screen Identification (Frontend)

1. Each file in `pages/` or `app/` with default export = 1 screen
2. Derive the route from the file/folder name (Next.js file-based routing)
3. Identify components consumed by each page
4. Identify API calls within each page/component

### Flow Identification (Frontend)

1. Navigation sequences (`router.push`, `navigate`, `<Link>`)
2. Route guards (conditional redirects)
3. Wizards/steps (components with sequential stages)
4. Group connected screens by navigation = 1 flow

---

## Expected Output

The Analyzer must produce `{SPECS_DIR}/_temp/analysis-report.md` following the structure defined in the `u-reverse-spec-analyzer.md` agent.
