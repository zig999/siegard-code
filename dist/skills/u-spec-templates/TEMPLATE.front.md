# Front-end Spec — Global

> Stack: {framework} | State: {zustand|redux|context} | Fetching: {react-query|swr|fetch}
> Version: 1.0.0

<!-- INSTRUCTION: This is the global frontend architecture document for the project. It does not belong to any specific domain — it is written once and updated as the project evolves. Per-screen configurations (data fetching, error mapping) go in each .screen.md. -->

## 1. Stack and Patterns
<!-- INSTRUCTION: Define framework, state library, data fetching, and UI components. Base on the project's CLAUDE.md. -->
- **Framework:** {React | Next.js | Vite+React | ...}
- **State management:** {zustand | redux | context API}
- **Data fetching:** {react-query | swr | native fetch}
- **Component library:** {shadcn/ui | MUI | Ant Design | Radix | none}
- **Router:** {react-router v6 | Next.js App Router | ...}
- **Language:** TypeScript

## 2. Routing Conventions
<!-- INSTRUCTION: Define the global route structure for the application. Every new route must follow this pattern. -->
- **Route prefix:** {/app/ | / | /dashboard/}
- **Root route (/):** {redirects to | displays}
- **Fallback route (404):** {/not-found | /404}
- **Protected routes:** {mechanism — e.g., auth guard via middleware, HOC, loader}
- **Layout strategy:** {shared root layout | layout per section | layout per route}

## 3. Global State Strategy
<!-- INSTRUCTION: Define what is the responsibility of global state vs local component state. Avoid "as needed" — be specific about categories. -->

### Global state (store / context)
- {data category} — {reason: shared across N screens}
- {e.g., user session, preferences, cart}

### Local state (component)
- {data category} — {reason: scope restricted to 1 screen or component}
- {e.g., form state, modal visibility}

### API Cache
- **Library:** {react-query | swr}
- **Default TTL:** {e.g., 30s for list data, 5min for detail data}
- **Default stale time:** {e.g., 10s}
- **Default revalidation:** {on-focus | on-reconnect | manual}

### Persistence
- **Between sessions:** {which data persists in localStorage/sessionStorage}
- **Between routes:** {which data survives via URL params vs state}

## 4. Component Patterns
<!-- INSTRUCTION: Define folder structure and naming. Must be specific enough that any developer knows where to create a new component. -->

### Folder structure
```
src/
  features/          # Components and logic per feature/domain
    {feature}/
      components/
      hooks/
      types/
  components/        # Shared components (pure UI, no business logic)
  lib/               # Utilities and configurations
  pages/ | app/      # Routes / entrypoints
```

### Naming
- Components: `PascalCase` (e.g., `UserCard.tsx`)
- Hooks: `camelCase` with `use` prefix (e.g., `useUserProfile.ts`)
- Utilities: `camelCase` (e.g., `formatDate.ts`)
- Types/Interfaces: `PascalCase` with descriptive suffix (e.g., `UserProfile`, `ApiResponse<T>`)

### Path aliases
```
@/components -> src/components
@/features   -> src/features
@/lib        -> src/lib
```

## 5. Global Error Handling
<!-- INSTRUCTION: Define behavior for errors that affect the entire application. Screen-specific errors go in each .screen.md. -->

| Error type | Behavior | Component |
|---|---|---|
| `AUTH_UNAUTHORIZED` (401) | Redirect to /login + clear session | middleware/guard |
| `AUTH_FORBIDDEN` (403) | Display access denied page | ErrorBoundary |
| Network error (offline) | Toast "No connection" + auto retry | NetworkBoundary |
| 500+ error (server) | Generic error page + support link | ErrorBoundary |
| Request timeout | Toast "Try again" + retry button | inline |

## 6. Global Accessibility
<!-- INSTRUCTION: Define minimum requirements that all components and screens must meet. Screen-specific requirements go in each .screen.md. -->
- **Minimum standard:** WCAG 2.1 AA
- **Keyboard navigation:** all actions accessible via Tab + Enter/Space
- **Focus management:** on modal/drawer open, focus first interactive element; on close, return to trigger
- **ARIA roles:** use semantic roles (role="dialog", role="alert", aria-live for updates)
- **Contrast:** minimum 4.5:1 for normal text, 3:1 for large text
- **Images:** descriptive alt on content images; alt="" on decorative images

## 7. Out of Scope (front global)
<!-- INSTRUCTION: What this frontend does NOT implement. Section is mandatory even if short. -->
- {e.g., server-side rendering of sensitive data — BFF responsibility}
- {e.g., OAuth authentication — redirect to external provider}

## 8. Design System
<!-- INSTRUCTION: This section is REFERENCE ONLY. Do not define tokens, colors, or values here. The content belongs in design-system/. -->
Full specification: [`{SPECS_DIR}/front/design-system/`](./design-system/_index.md)
Implementation: `{path to global.css or equivalent in the project}`

### Implementation Rules
- No token should be defined outside the project's global CSS file
- Arbitrary hardcoded values in components are forbidden — always `var(--token-name)`
- To check available tokens: read the project's global CSS file
- To check semantic usage rules: read `design-system/tokens.md`
- To add new tokens: edit `design-system/tokens.md` first, then the global CSS

## Changelog
<!-- INSTRUCTION: Mandatory. Never remove previous entries. -->
| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
