---
name: u-fe-development
description: Coding standards, commit conventions, folder structure, naming rules, and error handling patterns for front-end implementation. Covers React, TypeScript, and feature-based architecture. Loaded by orchestrator-dev when activating the Developer agent.
user-invocable: false
---

# SKILL: Development

## Purpose
This skill defines how the Developer Agent must structure, name, organize, and deliver code — ensuring consistency across Stories and predictability for the QA Agent.

---

## Customization via CLAUDE.md

> Precedence rule defined in `orchestrator-core.md`. Not repeated here.

Before creating any file, extract from `CLAUDE.md`:

| What to look for | Used in |
|---|---|
| Project folder structure | Where to create new files |
| Naming conventions | File, class, and function names |
| Testing framework/library | How to write and run tests |
| Configured logger | Replace `console.log` |
| Custom error pattern | Error classes to extend |
| Already defined environment variables | Avoid hardcoding and duplicates |
| Global CSS file path (design tokens) | Before implementing any component cataloged in `design-system/components.md`, check whether base classes already exist for it (buttons, inputs, cards). If they do, use them — do not reimplement states (hover, focus, active, disabled) inline in the component. |

If `CLAUDE.md` does not cover a given point, use the defaults from this skill and document the decision in the delivery file.

> **Design system rule:** defining visual tokens (colors, spacing, typography) in component files is forbidden. Always reference tokens via the project’s CSS variables (`var(--token-name)`). To check which tokens exist and how to use them, read `{SPECS_DIR}/front/design-system/tokens.md`.

---

## Mandatory flow before coding

```
1. Read the full Story (narrative + all acceptance criteria)
2. Read the files listed as dependencies in the previous delivery (if any)
3. Map the interface contracts the Story will touch or create
4. Write the plan as a comment at the top of the first file created
5. Only then begin implementation
```

If any step reveals a blocking ambiguity -> **stop and record it in the delivery file before continuing**.

---

## Branch and commits

### Branch per Story

Before any implementation, create a branch from `main`:

```
feat/US-XX    <- for Stories of type New feature, Improvement, Visual fix
fix/US-XX     <- for fixes coming from QA
refactor/US-XX <- for Stories of type Refactoring
```

**Rules:**
- Work exclusively on the Story branch — never commit directly to `main`
- **Never push** — pushing is the sole responsibility of the Orchestrator-Dev, after QA approval
- Commit locally as often as you like

### Commit format

Mandatory semantic prefix:

```
feat(US-XX): [description of what was added]
fix(US-XX):  [description of what was fixed]
refactor(US-XX): [description of improvement without behavior change]
test(US-XX): [description of tests added]
docs(US-XX): [documentation update]
```

Prefer per-UI-module commits when the Story involves multiple components or screens (e.g., first `feat(US-05): add ProductCard component`, then `feat(US-05): add ProductList page`, then `feat(US-05): add product store`).

---

## Naming conventions

| Element | Pattern | Example |
|---|---|---|
| Files | kebab-case | `user-profile.component.tsx` |
| Components | PascalCase | `UserProfile` |
| Functions/hooks | camelCase | `useUserProfile()` |
| Constants | SCREAMING_SNAKE | `MAX_ITEMS_PER_PAGE` |
| Variables | camelCase | `isLoading` |
| Types/Interfaces | PascalCase | `UserProfile`, `UserProfileProps` |
| Tests | same name + `.spec` or `.test` | `user-profile.component.spec.tsx` |

> `CLAUDE.md` conventions take precedence (see precedence rule in orchestrator-core).

---

## TypeScript

- Prefer `type` over `interface` — use `interface` only when extension or implementation is needed (e.g., `implements`, `extends` from third parties)
- Components with more than 3 render conditionals -> extract subcomponents
- `any` is forbidden — use `unknown` + type guard (already covered in prohibitions)

---

## State management

Each type of state has its place — mixing responsibilities leads to subtle bugs and makes debugging harder.

| State type | Where to manage | Example libraries |
|---|---|---|
| Server data (cache) | Server-state library | React Query, SWR, RTK Query |
| Mutations (server writes) | Server-state library | React Query, SWR |
| Global UI state | Dedicated store | Zustand, Jotai, Redux |
| Local component state | `useState` / `useReducer` | — |

**Forbidden:**
- Using a server-state library to manage UI state (e.g., storing a sidebar toggle in React Query)
- Using a UI store for server data cache (e.g., duplicating API data in Zustand)

> The specific library is a project decision (defined in `CLAUDE.md`). This rule defines the **separation of concerns**, not the tool.

---

## Default folder structure

```
src/
├── components/          <- reusable components
│   └── [component]/
│       ├── [component].tsx
│       ├── [component].types.ts
│       └── __tests__/
│           └── [component].spec.tsx
├── pages/               <- screens (one folder per route/screen)
│   └── [page]/
│       ├── index.tsx
│       └── [page].spec.tsx
├── hooks/               <- custom hooks
├── store/               <- global state (e.g., Zustand, Redux, Context)
├── services/            <- external API consumption functions (fetch/axios)
├── types/               <- global types and interfaces
└── utils/               <- pure utility functions
```

> Adapt according to the structure defined in `CLAUDE.md`.

---

## Mandatory tests and quality criteria

> Refer to `standards/SKILL.md` for the mandatory tests per Story type table and test quality criteria. Tests are part of the delivery — the QA Agent does not write tests; it validates the coverage of the tests you delivered.

---

## Error handling

Every function that can fail must:

1. Use explicit error types — avoid `throw new Error("something went wrong")`
2. Differentiate operational errors (expected, e.g., 404 from API) from programming errors (bugs)
3. Never silence errors with an empty `catch {}`
4. Propagate context: `throw new Error("fetchUser failed", { cause: err })`

```typescript
// Bad
try {
  const data = await fetch("/api/users/" + id).then(r => r.json());
  return data;
} catch (e) {
  throw new Error("error");
}

// Good
try {
  const res = await fetch("/api/users/" + id);
  if (!res.ok) throw new ApiError(`fetchUser(${id}) returned ${res.status}`);
  return res.json();
} catch (err) {
  throw new ApiError(`fetchUser(${id}) failed`, { cause: err });
}
```

---

## Edge cases

> Refer to the **universal checklist** and **handling patterns** in `standards/SKILL.md`. For every implemented function, handle applicable scenarios and document them in the delivery file.

---

## Explicit prohibitions

- `console.log` in production code (use the project’s configured logger)
- Hardcoded credentials, tokens, or environment URLs
- `any` in TypeScript without a justifying comment
- Unused imports
- Commented-out code (delete it, don’t comment it)
- `TODO` without a Story or issue reference (`// TODO(US-12): remove after migration`)
- Changing code outside the Story scope without creating a separate technical Story
- Inline CSS — using `style=""` in JSX or `style={{}}` in React components is forbidden; use CSS classes, CSS Modules, or Tailwind

### Linting configuration for inline CSS

Add to the project’s ESLint for automatic enforcement:

```js
// eslint.config.js (flat config) or equivalent in .eslintrc
{
  rules: {
    "react/forbid-dom-props": ["error", {
      forbid: [{ propName: "style", message: "Use CSS classes or Tailwind instead of inline style" }]
    }],
    "react/forbid-component-props": ["error", {
      forbid: [{ propName: "style", message: "Use CSS classes or Tailwind instead of inline style" }]
    }]
  }
}
```

> Requires `eslint-plugin-react`. `forbid-dom-props` covers HTML elements (`<div style={...}>`). `forbid-component-props` covers React components (`<Button style={...}>`). Both are needed for full coverage.

---

## Delivery file template

> When generating `us-XX-delivery.md`, read the full template at `.claude/skills/u-fe-templates/delivery.md`.

---

## Backend dependency verification

Before starting implementation, map **all backend endpoints and services** the Story needs to consume.

### How to verify

1. Extract from the Story and UI Spec all actions that imply server communication
2. For each action, identify the expected endpoint (HTTP method, route, payload, response)
3. Search the backend project (or the API documentation referenced in `CLAUDE.md`)
4. Classify each endpoint:
   - **Available** — found and compatible with the expected contract
   - **Partial** — exists but with a different contract than needed
   - **Missing** — not found in any source

### When to generate the report

Generate the file `{SESSIONS_DIR}/{SESSION}/us-XX-backend-pending-items.md` whenever there is **at least one endpoint classified as Partial or Missing**.

> For the full report template, read `.claude/skills/u-fe-templates/backend-pending-items.md`.

---

## Pre-delivery checklist

- [ ] All acceptance criteria have been addressed (even those not implemented, with justification)
- [ ] None of the explicit prohibitions were violated
- [ ] Mandatory edge cases have been handled
- [ ] **Each acceptance criterion has at least one corresponding test**
- [ ] **Edge cases handled in code have a corresponding test**
- [ ] "Tests written" section filled in the delivery file
- [ ] Backend dependency verification executed (Step 1B)
- [ ] If there are backend issues: `us-XX-backend-pending-items.md` report generated and Orchestrator notified
- [ ] Delivery file generated at `{SESSIONS_DIR}/{SESSION}/us-XX-delivery.md`
- [ ] Story status in `backlog.md` updated to `In testing`
- [ ] Working on the correct branch (`feat/US-XX`, `fix/US-XX`, or `refactor/US-XX`)
- [ ] Commits follow the semantic pattern (including `test(US-XX):` for test commits)
- [ ] **No push performed** — pushing is the Orchestrator-Dev’s responsibility
- [ ] If this is a post-QA fix: only the bugs from the report were changed — approved behaviors left untouched
- [ ] Orchestrator-Dev notified of completion
