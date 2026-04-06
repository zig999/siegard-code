---
name: u-reverse-spec-detection
description: Auto-detection protocol for stack and context (backend/frontend) based on project structure and dependencies. Used by the Reverse Spec Orchestrator during the initial phase.
user-invocable: false
---

# Protocol: Stack Auto-Detection

## When to use
- Whenever the Reverse Spec Orchestrator starts on a new project
- When `CLAUDE.md` does not explicitly define the stack

---

## Detection process

### Phase 1: Configuration files

Search in the root of `{CODE_DIR}` (and up to 1 level deep):

```
Glob("{CODE_DIR}/package.json")        -> Node.js
Glob("{CODE_DIR}/tsconfig.json")       -> TypeScript
Glob("{CODE_DIR}/requirements.txt")    -> Python
Glob("{CODE_DIR}/pyproject.toml")      -> Python
Glob("{CODE_DIR}/pom.xml")             -> Java
Glob("{CODE_DIR}/build.gradle*")       -> Java/Kotlin
Glob("{CODE_DIR}/go.mod")              -> Go
Glob("{CODE_DIR}/Gemfile")             -> Ruby
Glob("{CODE_DIR}/Cargo.toml")         -> Rust
Glob("{CODE_DIR}/composer.json")       -> PHP
```

If none found, search immediate subdirectories (monorepo):
```
Glob("{CODE_DIR}/*/package.json")
Glob("{CODE_DIR}/*/requirements.txt")
```

### Phase 2: Framework and context

**Node.js/TypeScript — read `package.json` and analyze `dependencies`:**

| Dependency found | Framework | Context |
|------------------|-----------|---------|
| `@nestjs/core` | NestJS | backend |
| `express` (without react/vue/angular) | Express | backend |
| `fastify` | Fastify | backend |
| `koa` | Koa | backend |
| `react` + `next` | Next.js | frontend (or fullstack) |
| `react` (without next) | React | frontend |
| `vue` + `nuxt` | Nuxt | frontend (or fullstack) |
| `vue` (without nuxt) | Vue | frontend |
| `@angular/core` | Angular | frontend |
| `svelte` | Svelte | frontend |

**Python — read `requirements.txt` or `pyproject.toml`:**

| Dependency found | Framework | Context |
|------------------|-----------|---------|
| `django` | Django | backend |
| `djangorestframework` | Django REST | backend |
| `fastapi` | FastAPI | backend |
| `flask` | Flask | backend |

**Java/Kotlin — read `pom.xml` or `build.gradle`:**

| Dependency found | Framework | Context |
|------------------|-----------|---------|
| `spring-boot-starter-web` | Spring Boot | backend |
| `quarkus` | Quarkus | backend |

### Phase 3: Context detection by structure

If dependency-based detection is ambiguous, use the folder structure:

**Backend indicators:**
```
Glob("**/controllers/**") or Glob("**/routes/**")     -> backend
Glob("**/models/**") or Glob("**/entities/**")         -> backend
Glob("**/services/**") or Glob("**/usecases/**")       -> backend
Glob("**/migrations/**")                                -> backend
Glob("**/middleware/**")                                 -> backend
```

**Frontend indicators:**
```
Glob("**/pages/**/*.{tsx,jsx,vue}")                     -> frontend
Glob("**/components/**/*.{tsx,jsx,vue}")                 -> frontend
Glob("**/hooks/**")                                      -> frontend
Glob("**/screens/**")                                    -> frontend
Glob("**/stores/**") or Glob("**/store/**")             -> frontend
Glob("**/public/**") or Glob("**/static/**")            -> frontend
```

### Phase 4: Database detection

Analyze dependencies + search for configs:

```
Grep("typeorm|TypeOrmModule") -> TypeORM
Grep("PrismaClient|@prisma") -> Prisma
Grep("sequelize|Sequelize") -> Sequelize
Grep("mongoose|Schema\(") -> Mongoose (MongoDB)
Grep("knex") -> Knex
```

Search for connection config:
```
Glob("**/.env*") -> read DATABASE_URL or DB_*
Glob("**/ormconfig*") -> TypeORM config
Glob("**/prisma/schema.prisma") -> Prisma schema
```

### Phase 5: Final classification

| Backend detected | Frontend detected | Classification |
|------------------|-------------------|----------------|
| Yes | No | backend |
| No | Yes | frontend |
| Yes | Yes | fullstack — ask the user |
| No | No | undetermined — ask the user |

---

## Shortcut via CLAUDE.md

If `CLAUDE.md` contains stack information, use it as the primary source:

```
Grep in CLAUDE.md for:
- "domain: frontend" or "domain: backend"
- "stack:" or "framework:"
- "database:" or "db:"
```

If CLAUDE.md defines the stack, confirm with the user but skip auto-detection.

---

## Output

Deliver to the Orchestrator:

```
context: {backend|frontend|fullstack}
language: {TypeScript|Python|Java|...}
framework: {NestJS|Express|FastAPI|React|Vue|...}
database: {PostgreSQL|MongoDB|MySQL|"N/A"}
orm: {TypeORM|Prisma|Mongoose|"N/A"}
state_management: {zustand|redux|pinia|"N/A"}
data_fetching: {react-query|swr|axios|"N/A"}
auth: {JWT|session|OAuth|"not identified"}
```
