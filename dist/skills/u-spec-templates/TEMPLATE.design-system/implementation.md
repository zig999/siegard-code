# Design System — Implementation

> Part of: `{SPECS_DIR}/front/design-system/`
> Index: [`_index.md`](./_index.md)

---

## 13. Animations and Micro-interactions

<!-- INSTRUCTION: Define the animation pattern per interaction type. Be specific: which CSS properties animate, what duration, what easing. Do not use "transition: all". -->

| Element | Duration | Easing | Animated Properties |
|---|---|---|---|
| Buttons (hover/active) | 150ms | ease-out | background-color, box-shadow |
| Inputs (focus) | 150ms | ease-out | border-color, box-shadow |
| Modals (entry) | 200ms | ease-out | opacity, transform (scale) |
| Modals (exit) | 150ms | ease-in | opacity, transform (scale) |
| Toasts (entry) | 200ms | ease-out | opacity, transform (translateY) |
| Sidebars (open) | 250ms | ease-out | transform (translateX) |
| Skeletons (pulse) | 1500ms | ease-in-out | opacity (loop) |

> All animations must be wrapped in `@media (prefers-reduced-motion: no-preference)`.

<!-- OPTIONAL EXTENSION — Component-specific animations: projects with charts, real-time data, or elaborate page transitions may add:
     Page entry: opacity 0->1 + translateY(8px)->0, 200ms ease-out.
     Area/line chart: stroke-dashoffset, 600ms ease-out.
     Bar chart: scaleY 0->1 with 40ms stagger between bars, 400ms ease-out.
     Live status (flickering): keyframes neon-flicker, minimum duration 4s, max 2 simultaneous elements. -->

---

## 14. Accessibility

<!-- INSTRUCTION: Document the token pairs that ensure sufficient contrast. Verify WCAG AA ratios (4.5:1 for normal text, 3:1 for large text and UI). -->

| Combination | Estimated Ratio | WCAG Level | Usage |
|---|---|---|---|
| `--text-primary` on `--bg-primary` | >= 4.5:1 | AA | Main interface text |
| `--text-body` on `--bg-surface` | >= 4.5:1 | AA | General content |
| `--text-muted` on `--bg-surface` | >= 3:1 | AA (UI) | Metadata, placeholders |
| `--primary-action` on `--bg-primary` | >= 3:1 | AA (UI) | Action elements |

> **Glassmorphism and contrast:** if the project uses surfaces with `backdrop-filter`, effective text contrast is reduced. Always use `--text-primary` (never `--text-body` or `--text-muted`) on glass elements.

---

## 15. Visual QA Checklist

<!-- INSTRUCTION: Use during PR review and visual QA. Mark as completed only when verified in the actual implementation, not in the spec. -->

- [ ] Is the primary action clear and unique per screen?
- [ ] Does typography match the semantic role (titles in display, data in mono, body in body)?
- [ ] Are comparable numbers using `tabular-nums` and mono family?
- [ ] Is `--accent-data` being improperly used as an action color?
- [ ] Is there more than one primary action on the same screen?
- [ ] Are the visual density limits (composition.md §11) being respected?
- [ ] Is the grid organized per layout patterns (composition.md §10)?
- [ ] Are hover and focus correct and consistent?
- [ ] Are there arbitrary spacings outside the `--space-*` scale?
- [ ] Is there `style=""` / `style={{}}` inline without dynamic value justification?
- [ ] Is there `transition: all` instead of specific properties?
- [ ] Are animations wrapped in `prefers-reduced-motion`?
- [ ] Do contrasts meet WCAG 2.1 AA?
- [ ] Are there components using tokens outside their declared semantics?

<!-- OPTIONAL EXTENSION — Additional checks for projects with visual effects: neon active limit per viewport respected? simultaneous backdrop-filter limit respected? grain texture duplicated in child elements (forbidden)? -->

---

<!-- OPTIONAL EXTENSION — Team guidelines: projects with larger teams may add a guidelines section by role (Design / Frontend / Product), with "Do" and "Don't" lists for each. -->

<!-- OPTIONAL EXTENSION — Tailwind reference config: projects using Tailwind CSS may add a section with the canonical token configuration. This section documents available tokens as reference — the authoritative implementation lives in global.css or tailwind.config.ts. -->
