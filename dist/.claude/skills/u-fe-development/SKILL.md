---
name: u-fe-development
description: Coding standards, commit conventions, folder structure, naming rules, and error handling patterns for front-end implementation. Covers React, TypeScript, and feature-based architecture. Loaded by orchestrator-dev when activating the Developer agent.
user-invocable: false
---

# SKILL: Development

## Required context

The following variables must be resolved by the Orchestrator before this skill is consumed. If any variable is absent, stop and request it before proceeding.

```yaml
required_context:
  - name: SESSIONS_DIR
    source: orchestrator-core (injected at activation)
    used_in: delivery file path, backend-pending-items path, backlog.md update
  - name: SESSION
    source: orchestrator-core (injected at activation)
    used_in: same as SESSIONS_DIR
  - name: SPECS_DIR
    source: orchestrator-core (injected at activation)
    used_in: design-system tokens path
```

> **Validation rule:** before executing any step that writes to `$SESSION_DIR/` or reads from `$SPECS_DIR/`, confirm the variables are resolved strings (not literal placeholders). If they are still placeholders, emit `status: blocked / reason: unresolved_context_variables` and halt.

---

## Purpose
This skill defines how the Developer Agent must structure, name, organize, and deliver code — ensuring consistency across Task Contracts and predictability for the QA Agent.

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

> **Design system rule:** defining visual tokens (colors, spacing, typography) in component files is forbidden. Always use Tailwind utility classes generated from the design system tokens (`bg-surface`, `text-content`, `rounded-md`, `p-lg`, `duration-fast`, `ease-out`). `var(--token-name)` is only allowed for dynamic inline values with no equivalent Tailwind utility — this is the exception, not the pattern.

### Design system loading routing

The Orchestrator selects which files to load based on `exec_type` and TC content. Machine-readable routing table:

```yaml
design_system_routing:
  always_load:
    - "{SPECS_DIR}/front/design-system-rules.md"   # < 150 lines — always in context

  by_exec_type:
    feature:
      required: [tokens.md, components.md]
      conditional:
        - file: composition.md
          load_when: tc_involves_layout_or_effects   # dashboard, multi-column, visual effects
        - file: implementation.md
          load_when: tc_involves_animation_or_a11y

    enhancement:
      required: []
      conditional:
        - file: tokens.md
          load_when: tc_affects_colors_spacing_typography
        - file: components.md
          load_when: tc_modifies_cataloged_component
        - file: composition.md
          load_when: tc_involves_layout_or_effects
        - file: implementation.md
          load_when: tc_involves_animation_or_a11y

    refactoring:
      required: []
      conditional:
        - file: components.md
          load_when: tc_modifies_cataloged_component

    visual-adjustment:
      required: [tokens.md, implementation.md]
      conditional:
        - file: components.md
          load_when: tc_modifies_cataloged_component
        - file: composition.md
          load_when: tc_involves_layout_or_effects

    bugfix:
      required: []
      conditional:
        - file: tokens.md
          load_when: tc_affects_colors_spacing_typography
        - file: components.md
          load_when: tc_modifies_cataloged_component
```

> `tc_involves_layout_or_effects`, `tc_modifies_cataloged_component`, `tc_affects_colors_spacing_typography`, `tc_involves_animation_or_a11y` are boolean flags evaluated by the Orchestrator from the TC `objective` and `acceptance_criteria` fields before activation. Full mounting logic: `.claude/agents/dev/protocols/u-fe-context-mounting-developer.md`.

---

## Progress reporting (mandatory)

Emit `task_progress` at each checkpoint before proceeding to the next phase of work. These events reset the stale detection timer and give the orchestrator visibility during long-running tasks.

```bash
# Checkpoint 1 — after reading and validating the task spec
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"spec_validated"}'

# Checkpoint 2 — after analysis, before writing any code
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"analysis_complete"}'

# Checkpoint 3 — after creating the branch, before first file write
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"branch_created"}'

# Checkpoint 4 — after all source code is written, before tests
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"implementation_done"}'

# Checkpoint 5 — after tests are written, before delivery.md
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_progress \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","checkpoint":"tests_written"}'
```

Never skip a checkpoint. If `$ORCH_WORKER_ID`, `$ORCH_TASK_ID`, or `$ORCH_ATTEMPT` are unresolved, stop and emit `task_failed` with `reason: unresolved_context_variables, retryable: false`.

---

## Terminal event guarantee (mandatory)

Before stopping for any reason — tool failure, blocked state, unexpected error, context limit — verify that a terminal event (`task_completed` or `task_failed`) has been emitted for `$ORCH_TASK_ID / $ORCH_ATTEMPT`.

**If no terminal has been emitted, emit `task_failed` immediately before stopping:**

```bash
python3 .claude/skills/orch-log/scripts/append.py \
  --agent $ORCH_WORKER_ID --event-type task_failed \
  --task-id $ORCH_TASK_ID --attempt $ORCH_ATTEMPT \
  --data '{"phase":"dev","reason":"<specific_reason>","retryable":true}'
```

| Situation | reason | retryable |
|-----------|--------|-----------|
| Tool call denied or failed | `tool_failure` | `true` |
| Required file not found | `missing_input:<file>` | `false` |
| Implementation blocked by ambiguity | `blocked_ambiguity` | `false` |
| Context limit approaching | `context_limit` | `true` |
| Unresolved env variables | `unresolved_context_variables` | `false` |
| Any other unexpected stop | `unexpected_exit` | `true` |

The `on_subagent_stop` hook synthesizes `task_failed` if this rule is not followed, but explicit emission is always preferred — it carries an accurate reason and retryable flag.

---

## Mandatory flow before coding

### Decision order — resolve before writing any component

Stop at the first step that resolves the need:

1. Before writing any UI markup, inspect the DS primitive layer (`components/ui/`, per `CLAUDE.md`). If an equivalent primitive exists (Card, Badge, Table, Form…), use it **by composition** — never reimplement it by hand (`u-fe-standards §2.2 Primitive reuse`; anti-pattern `reimplemented-primitive`). The `design-system/components.md` catalog is the source of truth for which primitives are cataloged.
2. Is there an equivalent component in the project's component library (declared in `CLAUDE.md`)? Add and use it.
3. Is there a semantic token for the value? Use the token — never the raw value.
4. Is there a similar feature/entity already implemented? Follow the same pattern.
5. Does the change respect the project's architecture rules (dependency direction, no sibling-feature imports)? If not, reorganize before coding.
6. Does it respect the accessibility standard declared in `CLAUDE.md` (`u-fe-standards §4`)? If not, fix it before delivering.

Generate **only what the Task Contract asks for**. Do not create stories, visual-regression, token pipeline, i18n, or ADR unless the Task Contract explicitly requires it.

```
1. Read the full Task Contract (narrative + all acceptance criteria)
   → emit checkpoint: spec_validated
2. Read the files listed as dependencies in the previous delivery (if any)
2.5 Check component specs — covered in Step 1C (Pre-flight gate). By the time you reach this step, component specs for §7 components must already be confirmed present and read. If Step 1C was not executed, stop and run it now before continuing.
3. Map the interface contracts the Task Contract will touch or create
   → emit checkpoint: analysis_complete
4. Create the feature branch (feat/TC-XX, fix/TC-XX, or refactor/TC-XX)
   → emit checkpoint: branch_created
5. Write the implementation plan as a comment at the top of the first file created
6. Only then begin implementation
   → emit checkpoint: implementation_done (after all source code is written, before tests)
7. Write tests
   → emit checkpoint: tests_written (after tests, before delivery.md)
```

If any step reveals a blocking ambiguity -> **stop, emit `task_failed` with `reason: blocked_ambiguity, retryable: false`, and record the ambiguity in the delivery file**.

---

## Branch and commits

### Branch per Task Contract

Before any implementation, create a branch from `main`:

```
feat/TC-XX      <- exec_type: feature | enhancement | visual-adjustment
fix/TC-XX       <- exec_type: bugfix (correction from QA)
refactor/TC-XX  <- exec_type: refactoring
```

**Rules:**
- Work exclusively on the Task Contract branch — never commit directly to `main`
- **Never push** — pushing is the sole responsibility of the Orchestrator-Dev, after QA approval
- Commit locally as often as you like

### Commit format

Mandatory semantic prefix:

```
feat(TC-XX): [description of what was added]
fix(TC-XX):  [description of what was fixed]
refactor(TC-XX): [description of improvement without behavior change]
test(TC-XX): [description of tests added]
docs(TC-XX): [documentation update]
```

Prefer per-UI-module commits when the Task Contract involves multiple components or screens (e.g., first `feat(TC-05): add ProductCard component`, then `feat(TC-05): add ProductList page`, then `feat(TC-05): add product store`).

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
- Derive types from validation schemas with `z.infer` — never hand-maintain a type in parallel with its schema
- Use `satisfies` to check a literal against a type without widening it
- Model mutually exclusive shapes as discriminated unions (a literal discriminant field) — not optional-field bags
- Type assertions (`as`) to silence the compiler are forbidden — narrow with `unknown` + type guards instead (`as const` is the only accepted use)

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
├── components/
│   └── ui/              <- DS primitives (Card, Badge, Table, Form…) — cataloged in design-system/components.md
│       └── [primitive]/
│           ├── [primitive].tsx
│           ├── [primitive].types.ts
│           └── __tests__/[primitive].spec.tsx
├── features/            <- feature modules (domain logic + data live here)
│   └── [feature]/
│       └── components/  <- feature-local components: compose ui/ primitives; bound to one feature
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

> **DS primitive vs feature-local:** the criterion for what belongs in `components/ui/` (DS primitive) versus `features/<feature>/components/` (feature-local) is defined in `design-system/components.md` → "Catalog Membership". Promoting a feature-local component into `components/ui/` is a design-system spec change (CR) — the Developer flags the need; it never adds primitives to the catalog ad hoc.

---

## Mandatory tests and quality criteria

> Refer to `.claude/skills/u-fe-standards/SKILL.md` for the mandatory tests per Task Contract type table and test quality criteria. Tests are part of the delivery — the QA Agent does not write tests; it validates the coverage of the tests you delivered.

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

> Refer to the **universal checklist** and **handling patterns** in `.claude/skills/u-fe-standards/SKILL.md`. For every implemented function, handle applicable scenarios and document them in the delivery file.

---

## Security

### XSS prevention

- **Never use `dangerouslySetInnerHTML`** without explicit security review and DOMPurify sanitization.
- User-generated content rendered as HTML must be sanitized before rendering:

```typescript
import DOMPurify from 'dompurify';

// Bad
<div dangerouslySetInnerHTML={{ __html: userInput }} />

// Good — only when rendering HTML is truly required
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userInput) }} />
```

- Prefer text rendering over HTML rendering: `{userInput}` is safe; `dangerouslySetInnerHTML` is not.
- Never interpolate user input into `href`, `src`, or event handler strings.

### Input handling

- Validate all user inputs at the form/component boundary before sending to the API.
- Use a schema validation library (Zod, Yup) for form inputs — do not write manual type checks.
- Never trust API responses for rendering without type-checking: use `Zod.parse()` or equivalent.

### Sensitive data

- Never log user PII, tokens, or passwords — not even in development.
- Never store auth tokens in `localStorage` without an explicit product + security decision documented in `CLAUDE.md`.

---

## Performance

### Memoization

Apply memoization only when a measurable performance problem exists — premature optimization adds complexity without benefit.

| Hook / API | When to use | When NOT to use |
|---|---|---|
| `useMemo` | Expensive computation that re-renders frequently with the same inputs | Simple value derivation, string formatting |
| `useCallback` | Callback passed as prop to a memoized child component | Inline handlers in a non-memoized component |
| `React.memo` | Pure component that receives the same props frequently | Component that always receives new reference props |

```typescript
// Use useMemo for expensive transformations
const sortedItems = useMemo(
  () => items.slice().sort(compareFn),
  [items, compareFn]
);

// No useMemo needed for trivial derivations
const fullName = `${user.first} ${user.last}`;
```

### Code splitting and lazy loading

- Split routes with `React.lazy` + `Suspense` — never import all pages eagerly.
- Heavy libraries (charts, rich text editors, PDF viewers) must be dynamically imported:

```typescript
const HeavyChart = React.lazy(() => import('./HeavyChart'));
```

- Apply `Suspense` with a meaningful fallback at the route level and around heavy components.

### Bundle size

- Prefer named imports for tree-shaking: `import { format } from 'date-fns'` — not `import * as dateFns`.
- Never import entire icon libraries — import individual icons.
- If a third-party library adds > 50 kB gzipped, justify the addition in the delivery file.

### NFR thresholds

If `CLAUDE.md` defines `performance_metrics`, note expected impact in the delivery file. QA validates in Phase 3. Default reference thresholds (override via `CLAUDE.md`):

| Metric | Target | Critical |
|---|---|---|
| LCP (Largest Contentful Paint) | ≤ 2.5 s | > 4.0 s |
| FCP (First Contentful Paint) | ≤ 1.8 s | > 3.0 s |
| TTI (Time to Interactive) | ≤ 3.8 s | > 7.3 s |
| Initial JS bundle (gzipped) | ≤ 200 kB | > 500 kB |

---

## Error boundaries

Every feature must be wrapped in a React `ErrorBoundary` at the page/route level to prevent a single component failure from crashing the entire application.

**Mandatory wrapping points:**
- Each page/route component
- Each independently renderable widget or dashboard section

```tsx
// pages/product-list/index.tsx
import { ErrorBoundary } from 'react-error-boundary';

export function ProductListPage() {
  return (
    <ErrorBoundary fallback={<PageErrorFallback />}>
      <ProductList />
    </ErrorBoundary>
  );
}
```

**Fallback UI rules:**
- Must display a user-facing message in domain language — not "Something went wrong".
- Must offer a recovery action (retry, go home, contact support).
- Must log the error to the configured error tracking SDK.

**Forbidden:**
- Wrapping the entire app in a single `ErrorBoundary` without page-level boundaries.
- Empty fallback (`fallback={<></>}`) — silent failures are invisible to users and monitoring.

### Dashboard and widget isolation

A dashboard composed of independently loadable widgets must isolate each widget:

- Each widget owns its **own data fetch** — never hydrate the whole dashboard from a single request.
- Each widget owns its **own loading skeleton**.
- Each widget is wrapped in its **own `ErrorBoundary`** — one failing widget must not blank the entire dashboard.

---

## Internationalization (i18n)

If `CLAUDE.md` declares `i18n: true` or specifies an i18n library (`react-i18next`, `next-intl`, `formatjs`):

- **Forbidden:** hardcoded user-facing strings in component files.
- All user-facing text must use translation keys: `t('product.title')` — not `"Product Title"`.
- Numbers, dates, and currencies must use locale-aware formatting: `Intl.NumberFormat`, `Intl.DateTimeFormat`, or the project's configured formatter.
- `aria-label` and `alt` attributes are user-facing — must also use translation keys.

If `CLAUDE.md` does not declare `i18n`, mark as `N/A — i18n not configured` in the delivery file. Do not add i18n infrastructure speculatively.

---

## Explicit prohibitions

- `console.log` in production code (use the project’s configured logger)
- Hardcoded credentials, tokens, or environment URLs
- `any` in TypeScript without a justifying comment
- Unused imports
- Commented-out code (delete it, don’t comment it)
- `TODO` without a Task Contract or issue reference (`// TODO(TC-12): remove after migration`)
- Changing code outside the Task Contract scope without creating a separate technical Task Contract
- Inline CSS — using `style=""` in JSX or `style={{}}` in React components is forbidden; use CSS classes, CSS Modules, or Tailwind
- `dangerouslySetInnerHTML` without DOMPurify sanitization — **Security risk: XSS**
- Hardcoded user-facing strings when `i18n: true` is declared in `CLAUDE.md`
- Component file longer than 300 lines — split into subcomponents before delivering
- Array index as React `key` in a dynamic list (reorderable, insertable, or deletable) — use a stable unique id from the data

---

## Anti-patterns

### State anti-patterns

| Anti-pattern | Why forbidden | Correct approach |
|---|---|---|
| Duplicating server data in a UI store (e.g., copying React Query cache into Zustand) | Creates two sources of truth — they diverge on mutations and refetches | Read server data directly from the server-state library; put only UI-specific state (modal open, selected tab) in the store |
| Using Context API as a server cache | Context re-renders all consumers on every update — not designed for frequently changing data | Use a server-state library (React Query, SWR, RTK Query) for all data fetched from APIs |
| Deriving state with `useEffect` + `setState` | Creates render cycles and async race conditions | Compute derived values inline or with `useMemo` |
| Synchronizing two separate state variables that represent the same fact | Gets out of sync on edge cases | Keep one source of truth; derive the other |

### Export anti-patterns

| Anti-pattern | Why forbidden | Correct approach |
|---|---|---|
| `export default` for components | Breaks tree-shaking analysis, complicates automated refactoring, allows inconsistent import names | Always use named exports: `export function MyComponent` |
| `export default` for types | Same reason — import name is unconstrained | `export type { MyType }` |
| Barrel files that re-export everything (`export * from`) | Prevents tree-shaking, inflates bundle, creates circular dependency risk | Export explicitly: `export { MyComponent } from ‘./MyComponent’` |

### Component anti-patterns

| Anti-pattern | Why forbidden | Correct approach |
|---|---|---|
| Component with 2+ distinct responsibilities | Hard to test, reuse, and reason about | Extract sub-components — one responsibility per component |
| Prop drilling beyond 2 levels | Tightly couples unrelated components | Use a feature store or Context for shared state within a feature |
| Reading from a sibling’s internal state via ref | Creates invisible coupling | Lift state to the closest common ancestor or a store |
| Conditional hook calls | Violates Rules of Hooks — causes crashes | Move conditions inside the hook or use a separate component per condition |
| Array index as `key` in dynamic lists | Index shifts on reorder/insert/delete — React mis-associates state and DOM nodes | Use a stable unique id from the data (`item.id`) |

### Linting configuration

Add to the project’s ESLint for automatic enforcement:

```js
// eslint.config.js (flat config) or equivalent in .eslintrc
{
  rules: {
    // Inline CSS
    "react/forbid-dom-props": ["error", {
      forbid: [{ propName: "style", message: "Use CSS classes or Tailwind instead of inline style" }]
    }],
    "react/forbid-component-props": ["error", {
      forbid: [{ propName: "style", message: "Use CSS classes or Tailwind instead of inline style" }]
    }],

    // Named exports only
    "import/no-default-export": "error",

    // Hooks rules (catches conditional hook calls)
    "react-hooks/rules-of-hooks": "error",
    "react-hooks/exhaustive-deps": "warn",

    // No prop drilling beyond component boundary (enforce store usage)
    // Note: no single ESLint rule covers this — enforce via code review and component anti-pattern table above

    // No dangerouslySetInnerHTML without explicit annotation
    "react/no-danger": "error"
  }
}
```

> `react/forbid-dom-props` + `forbid-component-props` requires `eslint-plugin-react`.
> `import/no-default-export` requires `eslint-plugin-import`.
> `react-hooks/*` requires `eslint-plugin-react-hooks`.
> `react/no-danger` is part of `eslint-plugin-react` — blocks `dangerouslySetInnerHTML` unless explicitly disabled with a justification comment.

---

## Delivery file template

> When generating `tc-XX-delivery.md`, read the full template at `.claude/skills/u-fe-templates/delivery.md`.

---

## Backend dependency verification

Before starting implementation, map **all backend endpoints and services** the Task Contract needs to consume.

### How to verify

1. Extract from the Task Contract and UI Spec all actions that imply server communication
2. For each action, identify the expected endpoint (HTTP method, route, payload, response)
3. Search the backend project (or the API documentation referenced in `CLAUDE.md`)
4. Classify each endpoint:
   - **Available** — found and compatible with the expected contract
   - **Partial** — exists but with a different contract than needed
   - **Missing** — not found in any source

### When to generate the report

Generate the file `$SESSION_DIR/pending/$ORCH_TASK_ID-backend-pending.md` whenever there is **at least one endpoint classified as Partial or Missing**.

> For the full report template, read `.claude/skills/u-fe-templates/backend-pending-items.md`.

---

## Pre-delivery checklist

- [ ] Pre-flight gate (Step 1C) completed — all 3 gates passed or Orchestrator accepted risk
- [ ] All acceptance criteria have been addressed (even those not implemented, with justification)
- [ ] None of the explicit prohibitions were violated
- [ ] No `dangerouslySetInnerHTML` without DOMPurify + justification comment
- [ ] No `console.log` in production files
- [ ] New pages are wrapped in `<ErrorBoundary>` with a non-empty fallback
- [ ] Routes use `React.lazy` + `Suspense` (not eagerly imported)
- [ ] If `i18n: true` in `CLAUDE.md`: no hardcoded user-facing strings
- [ ] Mandatory edge cases have been handled
- [ ] **Each acceptance criterion has at least one corresponding test**
- [ ] **Edge cases handled in code have a corresponding test**
- [ ] "Tests written" section filled in the delivery file
- [ ] Backend dependency verification executed (Step 1B)
- [ ] If there are backend issues: `$SESSION_DIR/pending/$ORCH_TASK_ID-backend-pending.md` generated and Orchestrator notified
- [ ] Delivery file generated at `$SESSION_DIR/delivery/$ORCH_TASK_ID-delivery.md`
- [ ] `task_progress` event emitted via `emit.py` with `status: in_testing`
- [ ] Working on the correct branch (`feat/TC-XX`, `fix/TC-XX`, or `refactor/TC-XX`)
- [ ] Commits follow the semantic pattern (including `test(TC-XX):` for test commits)
- [ ] **No push performed** — pushing is the Orchestrator-Dev’s responsibility
- [ ] If this is a post-QA fix: only the bugs from the report were changed — approved behaviors left untouched
- [ ] Component spec gate executed — qualifying shared components without spec flagged as Warning in delivery
- [ ] Props Contract verified — for each `component.spec.md §2` consumed by this Task Contract, no props were added, removed, or renamed without a spec CR
- [ ] Orchestrator-Dev notified of completion
