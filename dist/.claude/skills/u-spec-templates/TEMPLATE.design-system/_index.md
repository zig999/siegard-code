# Design System — {Project Name}

> Path: `{SPECS_DIR}/front/design-system/`
> Implementation: `{path to the project's global CSS file}`
> Version: 1.0.0 | Layer: permanent


---

## 1. System principles


| Principle | Description |
|---|---|
| {name} | {1-2 line description} |

---

## 2. Visual context

- **Color mode:** {dark-only | light-only | both}
- **Aesthetic constraints:** {list of constraints — e.g., must follow brand guidelines, no animations, WCAG AAA}

**Visual personality** — consumed by `u-ui-design` to calibrate directional rules (scale, weight, spacing, grid, effects):

```yaml
visual_personality:
  direction: bold | minimal | balanced
  intensity: 1 | 2 | 3 | 4 | 5
```

| direction | When to use |
|---|---|
| `bold` | Marketing, landing pages, brand-forward products — maximize impact and distinctiveness |
| `minimal` | Dashboards, data-dense tools, B2B apps — maximize clarity and information density |
| `balanced` | General-purpose apps — standard hierarchy, no strong directional push |

| intensity | Effect |
|---|---|
| 1 | Slight lean toward the direction — barely noticeable |
| 2 | Moderate lean — clear but restrained |
| 3 | Strong lean — direction is evident |
| 4 | Very strong — direction dominates most decisions |
| 5 | Maximum — full directional rules applied (e.g., bold 5 = bolder mode full directives) |

---

## 3. File summary

| File | Content | When to load |
|---|---|---|
| `tokens.md` | Colors, spacing, typography, shadows and borders | Whenever implementing visual styles |
| `composition.md` | Visual effects (glass, neon, spotlight), hierarchy, layout, density | Screens with effects, dashboards, complex layout |
| `components.md` | Catalog membership (DS primitive vs feature-local) + component catalog: slots x states, do/dont | Implementing or specifying visual components |
| `implementation.md` | Accessibility, animations, QA checklist, team guidelines | Visual QA, PR review, accessibility adjustments |

---

## Changelog

| Version | Date | Author | Type | Description | CR |
|---|---|---|---|---|---|
| 1.0.0 | {date} | Front Spec Agent | initial | Initial version | -- |
