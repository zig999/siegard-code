# Project

domain: frontend
stack: React 18, TypeScript 5, Next.js 14 (App Router), Tailwind CSS 3, Zustand, React Query, Vitest, Playwright
specs_dir: docs/specs
sessions_dir: docs/sessions

## Architecture

- Next.js App Router with server and client components
- Feature-based folder structure under `src/features/{feature}/`
- Shared UI components under `src/components/ui/`
- API consumption via React Query (TanStack Query v5)
- Client state via Zustand (one store per feature)
- Server state exclusively via React Query cache
- Authentication via NextAuth.js with JWT

## Conventions

- Language: TypeScript strict mode
- Naming: camelCase for variables/functions, PascalCase for components/types, UPPER_SNAKE_CASE for constants
- File naming: kebab-case (e.g., `user-profile-card.tsx`)
- Component files: one component per file, named export (not default)
- Hooks: `use-` prefix, colocated in `hooks/` within the feature folder
- Types: colocated in `types.ts` per feature; shared types in `src/types/`
- Pages: Next.js App Router conventions (`page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`)

## Component Patterns

- Presentational components: props-driven, no internal state management
- Container components: connect to stores/queries, pass data down
- Server components by default; add `"use client"` only when needed
- Forms: React Hook Form + Zod for validation
- Modals/dialogs: Radix UI primitives
- Icons: Lucide React

## Styling

- Tailwind CSS with project-specific design tokens in `tailwind.config.ts`
- No inline styles or CSS modules
- Responsive: mobile-first with `sm:`, `md:`, `lg:` breakpoints
- Dark mode: `class` strategy via `next-themes`
- Animation: Tailwind `animate-` utilities + Framer Motion for complex transitions

## Testing

- Unit tests: Vitest + Testing Library, colocated as `*.test.tsx`
- E2E tests: Playwright under `e2e/`
- Minimum coverage: 80% for hooks/utils, 60% for components
- MSW (Mock Service Worker) for API mocking in tests

## Personas

- End User: authenticated user navigating the application
- Administrator: user with elevated permissions for management screens
- Guest: unauthenticated visitor with limited access

## Error Handling

- API errors: React Query `onError` callbacks + global error boundary
- Form validation: Zod schemas with inline error messages
- Network errors: retry with exponential backoff (React Query default)
- 401/403: redirect to login via NextAuth session check
- Unexpected errors: `error.tsx` boundary per route segment

## API Integration

- Base URL configured via `NEXT_PUBLIC_API_URL` environment variable
- HTTP client: Axios instance with interceptors for auth token injection
- All API calls wrapped in React Query hooks under `src/features/{feature}/api/`
- Optimistic updates for mutations where applicable

## Environment

- Node: v20 LTS
- Package manager: pnpm
- Linter: ESLint with eslint-config-next + @typescript-eslint
- Formatter: Prettier + prettier-plugin-tailwindcss
- CI: GitHub Actions
- Dev server: `next dev` with Turbopack
