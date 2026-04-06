# Project

domain: backend
stack: Node.js 20, TypeScript 5, NestJS 10, PostgreSQL 16, Prisma 5, Jest
specs_dir: docs/specs
sessions_dir: docs/sessions

## Architecture

- Monolith modular (one service, multiple domain modules)
- REST API with OpenAPI documentation
- Layered: Controller -> Service -> Repository
- PostgreSQL as primary database with Prisma ORM
- Redis for caching and session storage
- Bull for background job processing

## Conventions

- Language: TypeScript strict mode
- Naming: camelCase for variables/functions, PascalCase for classes/interfaces, UPPER_SNAKE_CASE for constants
- File naming: kebab-case (e.g., `user-profile.service.ts`)
- Folder structure: feature-based modules under `src/modules/{domain}/`
- Each module contains: `controller/`, `service/`, `repository/`, `dto/`, `entity/`, `spec/`
- DTOs use class-validator decorators for input validation
- All endpoints return standardized response shape: `{ data, meta, errors }`
- Error codes follow the pattern: `DOMAIN_ACTION_REASON` (e.g., `AUTH_LOGIN_INVALID_CREDENTIALS`)

## Testing

- Unit tests: Jest with mocked dependencies, colocated as `*.spec.ts`
- Integration tests: Supertest + test database, under `test/integration/`
- Minimum coverage: 80% for services, 60% for controllers
- Test database: Docker PostgreSQL container via `docker-compose.test.yml`

## Personas

- Administrator: manages system settings, users, and permissions
- API Consumer: external service that integrates via REST endpoints
- End User: authenticated user who interacts with the system through the API

## Error Handling

- Business errors: throw domain-specific exceptions extending `AppException`
- Validation errors: handled by NestJS `ValidationPipe` + class-validator
- Unhandled errors: global exception filter returns 500 with correlation ID
- All errors logged with structured JSON (Winston)

## Database

- Migrations: Prisma Migrate (`prisma/migrations/`)
- Seeds: `prisma/seed.ts` for development data
- Naming: snake_case for tables and columns
- All tables have `created_at`, `updated_at`, `deleted_at` (soft delete)

## Environment

- Node: v20 LTS
- Package manager: pnpm
- Linter: ESLint with @typescript-eslint
- Formatter: Prettier
- CI: GitHub Actions
- Container: Docker + docker-compose for local development
