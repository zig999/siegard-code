# Front-end Spec -- Global

> Stack: {framework} | State: {zustand \| redux \| context} | Fetching: {react-query \| swr \| fetch}
> Version: 1.0.0 | Status: draft | review | approved | Layer: permanent

> This is the global frontend architecture document for the project — written once, updated as the project evolves. Per-feature configurations (data fetching, error mapping, transforms) go in each .feature.spec.md.

---

## 1. Stack and Patterns

> Framework, state library, data fetching, and UI components. Base on CLAUDE.md.

- **Framework:** {React \| Next.js \| Vite+React \| ...}
- **State management:** {zustand \| redux \| context API}
- **Data fetching:** {react-query \| swr \| native fetch}
- **Component library:** {shadcn/ui \| MUI \| Ant Design \| Radix \| none}
- **Router:** {react-router v6 \| Next.js App Router \| ...}
- **Language:** TypeScript

---

## 2. Routing Conventions

> Global route structure — every new route must follow this pattern.

- **Route prefix:** {/app/ \| / \| /dashboard/}
- **Root route (/):** {redirects to \| displays}
- **Fallback route (404):** {/not-found \| /404}
- **Protected routes:** {mechanism — e.g., auth guard via middleware, HOC, loader}
- **Layout strategy:** {shared root layout \| layout per section \| layout per route}

---

## 3. Global State Strategy

> Define what is the responsibility of global state vs local component state. Be specific — avoid "as needed".

### Global state (store / context)
- {data category} — {reason: shared across N screens}

### Local state (component)
- {data category} — {reason: scope restricted to 1 screen or component}

### API Cache
- **Library:** {react-query \| swr}
- **Default TTL:** {e.g., 30s for list data, 5min for detail data}
- **Default stale time:** {e.g., 10s}
- **Default revalidation:** {on-focus \| on-reconnect \| manual}

### HTTP Adapter (optional — omit if responses are consumed as-is)
> Global transforms applied to all responses before reaching the UI layer. Feature-specific transforms belong in `feature.spec.md §4`.
- **Case conversion:** {none \| snake_case → camelCase via {library/interceptor}}
- **Date parsing:** {none \| ISO 8601 strings → Date via {library}, fields matching: {pattern}}
- **Other global transforms:** {none \| {description}}

### Persistence
- **Between sessions:** {which data persists in localStorage/sessionStorage}
- **Between routes:** {which data survives via URL params vs state}

---

## 4. Component Patterns

> Folder structure and naming must be specific enough that any developer knows where to create a new component.

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
- Types/Interfaces: `PascalCase` (e.g., `UserProfile`, `ApiResponse<T>`)

### Path aliases
```
@/components -> src/components
@/features   -> src/features
@/lib        -> src/lib
```

---

## 5. Global Error Handling

> Behavior for errors that affect the entire application. Feature-specific errors go in each .feature.spec.md §6.

| Error type | Behavior | Component |
|---|---|---|
| `AUTH_UNAUTHORIZED` (401) | Redirect to /login + clear session | middleware/guard |
| `AUTH_FORBIDDEN` (403) | Display access denied page | ErrorBoundary |
| Network error (offline) | Toast "No connection" + auto retry | NetworkBoundary |
| 500+ error (server) | Generic error page + support link | ErrorBoundary |
| Request timeout | Toast "Try again" + retry button | inline |

---

## 6. Global Accessibility

> Minimum requirements that all components and screens must meet. Feature-specific requirements go in each .feature.spec.md §8.

- **Minimum standard:** WCAG 2.2 AA
- **Keyboard navigation:** all actions accessible via Tab + Enter/Space
- **Focus management:** on modal/drawer open, focus first interactive element; on close, return to trigger
- **Focus visibility (SC 2.4.11):** focus indicator never fully obscured by sticky headers or overlays
- **ARIA roles:** use semantic roles (role="dialog", role="alert", aria-live for updates)
- **Form fields:** invalid inputs set `aria-invalid` and link the message via `aria-describedby`
- **Contrast:** minimum 4.5:1 for normal text, 3:1 for large text
- **Target size (SC 2.5.8):** interactive targets ≥ 24×24px CSS (project floor stricter — ≥ 32px any context, ≥ 44×44px mobile)
- **Images:** descriptive alt on content images; alt="" on decorative images

---

## 7. Permitted and Prohibited Libraries

> Project-specific configuration — varies per project, not defined in SKILL files.

| Library | Status | Rationale |
|---------|--------|-----------|
| `{name}` | Permitted | {single approved use case} |
| `{name}` | Prohibited | {reason — use {alternative} instead} |
| `{name}` | Approved exception | {narrow scope where use is allowed} |

---

## Changelog

> Mandatory — never remove previous entries.

| Version | Date | Author | Type | Description | CR |
|---------|------|--------|------|-------------|----|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
