<!--
  CLAUDE.md fragment — Fixed frontend stack profile.

  WHEN TO USE: paste this block into the target project's CLAUDE.md, inside the
  "## Stack — Frontend" section, ONLY when the project uses this exact stack:
  Vite + React 19 + TypeScript (strict) + Tailwind v4 + shadcn/ui +
  TanStack Query/Router/Table + React Hook Form + Zod.

  For any other stack, omit this fragment — the generic u-fe-* skills stay library-agnostic.
  This file is an authoring-time include; it lives outside dist/.claude/ and is NOT part of the copied distribution.
-->

### Fixed stack contract

- Stack: **Vite + React 19 + TypeScript (strict) + Tailwind v4 + shadcn/ui + TanStack Query/Router/Table + React Hook Form + Zod**.
- Do not swap any item without explicit instruction. These rules are imperative defaults; "on demand" means only when the Task Contract asks for it.

---

### Data layer — TanStack Query

- Every server call lives in `features/<x>/api/` as a hook (`useCustomers`, `useCreateOrder`).
- **Forbidden:** `fetch`/`axios` called directly inside a component; `useEffect` used to fetch data.
- Query keys are typed and centralized per entity:
  ```ts
  export const customerKeys = {
    all: ["customers"] as const,
    detail: (id: string) => ["customers", id] as const,
  };
  ```
- `staleTime` defaults — concrete, do not invent per file: **stable data 5min, volatile data 0**.
- Mutations always `invalidateQueries` for the affected keys. Optimistic updates only on demand.
- Global `QueryClient`: `retry: 1`; errors handled centrally in the Query Cache `onError`.

---

### Component contract — React 19 + Tailwind

Every component exported from the shared UI layer:

- Accepts `className` and merges it with `tailwind-merge` + `clsx` (the project's `cn()` util) — never string concatenation.
- Accepts `ref` as a normal prop (React 19) — **do not use `forwardRef`**.
- Consumes semantic tokens only (never raw values).
- Uses CVA (`class-variance-authority`) **only when there are 2+ visual variants** — no variants → no CVA.
- Files per component: `component.tsx`, `component.types.ts`, `index.ts`. (Stack exception to the generic no-barrel rule: a per-component `index.ts` re-exporting that single component's public surface is allowed; project-wide `export *` barrels remain forbidden.)

---

### Forms — React Hook Form + Zod

- Stack: React Hook Form + Zod, **schema-first**: `schema → z.infer → form`. Always use `zodResolver`.
- Validate client-side (Zod) **and** assume server-side validation — never trust the client alone.
- Visible loading and error states; friendly messages.
- Accessibility: associated `label`; `aria-invalid` on invalid fields; error linked via `aria-describedby` (see `u-fe-standards §4`).

---

### Tables — TanStack Table

- Standard: TanStack Table, always with sorting, filtering, pagination, selection, loading, and empty states.
- Persist sorting / filtering / pagination in the **URL**.
- Virtualization: on demand, only for large lists (> ~1000 rows).

---

### Responsive — Tailwind

- Mobile First. Use Tailwind named breakpoints: `sm`, `md`, `lg`, `xl`, `2xl`.
- Use **container queries** for reusable components (sized by their container, not the viewport).
- **Forbidden:** custom CSS media queries.
- QA test viewports map to breakpoints: 320px (base/mobile) · 768px (`md`) · 1024px (`lg`) · 1440px (`xl`/`2xl`).

---

### Stack-specific forbidden patterns

- `fetch`/`axios` in a component · `useEffect` for data fetching → use a `features/<x>/api/` Query hook.
- `forwardRef` → pass `ref` as a prop (React 19).
- Custom CSS media queries → Tailwind breakpoints / container queries.
- Raw `className` string concatenation → `cn()` (`tailwind-merge` + `clsx`).
- Duplicated query key or token literal → reuse the centralized key factory / semantic token.
