# Stack-Specific References Analysis

Analysis of all stack-specific, framework-specific, and environment-specific references found in agent files (`dist/.claude/`). These references violate the principle that agents should be generic and stack-agnostic, adapting behavior from the target project's `CLAUDE.md` configuration.

> **Analysis date**: 2026-04-05
> **Files analyzed**: 89 files in `dist/.claude/`
> **Purpose**: Identify what needs to change so agents work with any stack, not just TypeScript/React

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| **High** | 7 | Hardcoded as mandatory requirement -- blocks usage with other stacks |
| **Medium** | 6 | Fixed tool/library lists -- limits flexibility |
| **Low** | ~8 | Acceptable in context (stack detection is multi-stack by design) |

---

## HIGH severity -- Hardcoded requirements

These references treat a specific technology as a mandatory requirement rather than reading the project's declared stack.

### 1. TypeScript assumed as universal language

**File**: `skills/u-fe-development/SKILL.md`
- Description line states: "Covers React, TypeScript, and feature-based architecture"
- Dedicated `## TypeScript` section with `strict: true`, `noImplicitAny` rules
- File extensions `.ts`, `.tsx` assumed as standard for all code files

**File**: `skills/u-be-development/SKILL.md`
- Dedicated `## TypeScript code quality` section with strict configuration rules
- File extensions `.ts` assumed as standard for all backend code

**Impact**: Any project using JavaScript, Python, Go, Java, or other languages would receive TypeScript-specific instructions that don't apply.

**Recommendation**: Replace hardcoded TypeScript rules with a conditional: "Follow the language and type system rules declared in the project's `CLAUDE.md` (`stack:` field). If TypeScript is declared, enforce strict mode."

---

### 2. React assumed as frontend framework

**File**: `skills/u-fe-development/SKILL.md`
- Description explicitly states: "Covers React, TypeScript, and feature-based architecture"

**Impact**: Projects using Vue, Angular, Svelte, or other frameworks receive React-specific patterns.

**Recommendation**: Change to: "Covers the frontend framework declared in CLAUDE.md." Move React-specific patterns to a conditional section or separate skill.

---

### 3. CSS approach hardcoded

**File**: `skills/u-fe-development/SKILL.md`
- Explicit prohibition: `style=""` or `style={{}}` forbidden
- Approved approaches listed as: "CSS classes, CSS Modules, or Tailwind"

**File**: `skills/u-fe-standards/SKILL.md`
- Quality criterion references: "all styling via CSS classes, CSS Modules, or Tailwind"

**Impact**: Projects using styled-components, Emotion, Sass, or other CSS-in-JS solutions are not covered. The inline CSS prohibition may conflict with some frameworks (e.g., React Native's StyleSheet).

**Recommendation**: Change to: "Follow the styling approach declared in the project's `CLAUDE.md`. If no approach is declared, prefer class-based styling over inline styles."

---

## MEDIUM severity -- Fixed tool/library lists

These references list specific tools as options rather than reading the project's configuration.

### 4. Frontend testing tools hardcoded

**File**: `skills/u-fe-qa-docs/SKILL.md`
- Description: "...with Vitest, Testing Library, and Playwright"
- Test matrix:
  - Unit: `Jest, Vitest`
  - Component: `Testing Library + Vitest/Jest`
  - Integration: `Testing Library + MSW`
  - E2E: `Playwright, Cypress`

**Impact**: Projects using Mocha, Karma, Selenium, or framework-specific test tools (Angular TestBed, Vue Test Utils) receive incorrect guidance.

**Recommendation**: Change to: "Use the testing tools configured in the project. Read `CLAUDE.md` and dependency manifests to identify the test framework, component testing library, and E2E tool."

---

### 5. Backend testing tools hardcoded

**File**: `skills/u-be-qa-docs/SKILL.md`
- Test matrix:
  - Unit: `Jest, Vitest, pytest`
  - Integration: `Supertest + Jest, httptest, pytest + TestClient`
  - E2E: `Supertest, pytest, Postman/Newman`

**Impact**: Projects using JUnit, Go's testing package, RSpec, or other language-specific tools receive a Node.js/Python-biased matrix.

**Recommendation**: Same as frontend -- read testing tools from project configuration.

---

### 6. State management libraries listed

**File**: `skills/u-fe-development/SKILL.md`
- Global UI state options: `Zustand, Redux, Jotai, Context API`
- Server data options: `React Query, SWR, RTK Query`

**Impact**: These are React-ecosystem libraries. Projects using Vue (Pinia), Angular (NgRx), or Svelte stores receive irrelevant options.

**Recommendation**: Change to: "Use the state management and data fetching libraries declared in CLAUDE.md or detected from project dependencies."

---

## LOW severity -- Acceptable references

These references exist in files whose explicit purpose is multi-stack detection. They are acceptable by design.

### 7. Reverse spec analysis patterns

**File**: `skills/u-reverse-spec-analysis/SKILL.md`

Contains framework-specific search patterns for:
- **Node.js**: NestJS (controllers, services, guards, interceptors), Express (routes, middleware), Fastify, Koa
- **Python**: Django (views, models, serializers), FastAPI (routers, schemas), Flask
- **Java/Kotlin**: Spring Boot (controllers, services, repositories), Quarkus
- **Frontend**: React, Vue, Angular, Svelte, Next.js, Nuxt

**Why acceptable**: The Analyzer's job is to detect and understand any stack. These patterns are lookup tables for identification, not requirements imposed on the project.

---

### 8. Stack detection protocol

**File**: `agents/reverse-spec/protocols/u-reverse-spec-detection.md`

Contains detection rules via dependency manifests:
- `package.json` -> Node.js
- `requirements.txt`, `pyproject.toml`, `Pipfile` -> Python
- `pom.xml`, `build.gradle` -> Java/Kotlin
- `go.mod` -> Go
- `Gemfile` -> Ruby
- `Cargo.toml` -> Rust
- `composer.json` -> PHP

ORM detection: Prisma, TypeORM, Sequelize, Mongoose, Knex
Database detection: PostgreSQL, MySQL, MongoDB, SQLite, Redis

**Why acceptable**: Detection is inherently multi-stack and adapts to what it finds.

---

### 9. Source code validation

**File**: `commands/u-reverse-spec.md`

Checks for `package.json`, `requirements.txt`, `src/`, `tsconfig.json` as indicators that a directory contains source code.

**Why acceptable**: These are heuristics for confirming a directory has code, not stack requirements.

---

### 10. Infrastructure mention

**File**: `skills/u-be-development/SKILL.md`
- "Docker compose / setup scripts" mentioned in infrastructure dependency section
- Validation libraries listed: `Zod, Joi, class-validator`

**Why low severity**: These are mentioned as options in a discovery checklist, not as requirements. However, the validation library list leans toward Node.js ecosystem.

---

## Affected files summary

| File | Issues | Severities |
|------|--------|-----------|
| `skills/u-fe-development/SKILL.md` | React, TypeScript, CSS, state mgmt, data fetching | High x3, Medium x1 |
| `skills/u-be-development/SKILL.md` | TypeScript, validation libs | High x1, Low x1 |
| `skills/u-fe-qa-docs/SKILL.md` | Testing tools | Medium x1 |
| `skills/u-be-qa-docs/SKILL.md` | Testing tools | Medium x1 |
| `skills/u-fe-standards/SKILL.md` | CSS approach | High x1 |
| `skills/u-reverse-spec-analysis/SKILL.md` | Multi-stack patterns | Low (acceptable) |
| `agents/reverse-spec/protocols/u-reverse-spec-detection.md` | Multi-stack detection | Low (acceptable) |
| `commands/u-reverse-spec.md` | Source code validation | Low (acceptable) |

---

## Recommended changes

### Pattern to adopt

Instead of:
```markdown
## TypeScript
- strict: true
- noImplicitAny: true
```

Use:
```markdown
## Language and type system
Follow the language rules declared in the project's CLAUDE.md (stack: field).
If the project uses a typed language, enforce strict type checking.
```

Instead of:
```markdown
## Testing
Unit | Jest, Vitest
E2E  | Playwright, Cypress
```

Use:
```markdown
## Testing
Read the project's test configuration from CLAUDE.md and dependency manifests.
Apply the test types appropriate for the Story type using the project's configured tools.
```

### Migration priority

1. **`u-fe-development/SKILL.md`** -- Most impacted file (5 issues). Start here.
2. **`u-be-development/SKILL.md`** -- TypeScript assumption.
3. **`u-fe-qa-docs/SKILL.md`** and **`u-be-qa-docs/SKILL.md`** -- Testing tool matrices.
4. **`u-fe-standards/SKILL.md`** -- CSS approach criterion.
