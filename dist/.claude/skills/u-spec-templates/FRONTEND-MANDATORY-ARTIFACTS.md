# Frontend mandatory artifacts — single source of truth

Producer: `u-spec-front` (must create/sync on its FIRST pass).
Consumer / gate: `u-spec-validator` Mode 1b (rules 10, 10b, 11, 12, 12b).

This file is the single source of truth for the design-system artifacts the front
spec pipeline must produce and the validator blocks on. `u-spec-front` self-checks
against it before finalizing (Step 5); `u-spec-validator` enforces it. Both MUST
reference this list — divergence between producer and gate caused a guaranteed
INVALID + repair cycle on every frontend wave (F-07).

## Required files (rule 10 — blocking if missing)

| Path | Notes |
|------|-------|
| `front/design-system/_index.md` | principles, visual context, file summary, populated Changelog (rule 12) |
| `front/design-system/tokens.md` | `## Token Declarations` CSS block with ≥1 non-placeholder value (10a); `token-manifest` YAML block (10b) |
| `front/design-system/composition.md` | visual effects, hierarchy, layout, density |
| `front/design-system/components.md` | component catalog covering all components referenced by feature specs (rule 11) |
| `front/design-system/implementation.md` | accessibility, animations, QA checklist |
| `front/design-system-rules.md` | compact summary (≤150 lines), **synced to `tokens.md`** (rule 12b — blocking) |

## Sync invariants

- **12b (blocking):** every token defined in `design-system/tokens.md` is reflected in
  `design-system-rules.md`. A stale rules.md makes developer agents use wrong tokens.
  After ANY change to `design-system/`, regenerate `design-system-rules.md`.
- **10b (warning):** token names in the `tokens.md` CSS block and the `token-manifest`
  YAML block must match.
- **11 (warning):** every component referenced in feature specs is cataloged in
  `design-system/components.md`.

> Templates: `.claude/skills/u-spec-templates/TEMPLATE.design-system/` (the 5 files)
> and `.claude/skills/u-spec-templates/TEMPLATE.design-system-rules.md`.
