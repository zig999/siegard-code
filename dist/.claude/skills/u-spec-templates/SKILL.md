---
name: u-spec-templates
description: Canonical TEMPLATE.* artifacts for SDD spec writers — domain spec, back spec, front spec, feature spec, flow, component spec, decisions, design-system rules and design-system bundle. Consumed by u-spec-writer, u-spec-back, and u-spec-front, which read templates by path. Also ships scripts/read_spec_sections.py, which loads only the sections a worker needs while always returning the full section index (R16). Not user-invocable.
user-invocable: false
allowed-tools: Bash(python3 *), Read
---

# u-spec-templates

Canonical templates consumed by SDD spec agents, read by path (`.claude/skills/u-spec-templates/<file>`); the directory listing is authoritative.

## scripts/read_spec_sections.py

Loads the sections a worker needs and returns the **complete section index** either way, so partial
loading never becomes partial awareness.

```bash
python3 .claude/skills/u-spec-templates/scripts/read_spec_sections.py \
  --file "$SPECS_DIR/domains/<domain>/back/<domain>.back.md" \
  --sections "Business Rules,State Machine"        # numbers, §N, or title text
# --index-only : titles and line counts, no bodies
# --all        : explicit opt-out of scoping
# exit 2       : a selector matched nothing (reported, never silently dropped)
```

Sections are level-2 headings; the shipped templates number them (`## 4. State Machine (ST)`), and
unnumbered ones (`## Changelog`) are addressable by title. The preamble before the first heading is
always included — it carries the artifact's identity and version.

**Measured effect** (`troubleshooting-engine`, the domain that consumed 57,213 of a 60,000 token
budget):

| Worker | Artifact | Whole file | Scoped |
|---|---|---:|---:|
| `u-spec-back` | `.spec.md` | 1046 | 833 (−20%) |
| `u-spec-front` | `.spec.md` | 1046 | 259 (−75%) |
| `u-spec-validator` | `.spec.md` | 1046 | 833 (−20%) |
| `u-spec-validator` | `.back.md` | 1374 | 1168 (−15%) |
| `u-spec-reviewer` | `.spec.md` | 1046 | 1046 (0% — by design) |

The back/validator saving is modest because §Business Rules is the largest section (763 of 1374
lines in that `.back.md`) and those workers genuinely need it. `u-spec-front` is the large win: it
needs UI-facing states and errors, not backend enforcement detail.

`u-spec-reviewer` and `u-spec-compliance` read whole files deliberately — one checks completeness,
the other scans for gaps, and both are defeated by a subset.

## Index

| Template | Produces | Primary consumer |
|---|---|---|
| `TEMPLATE.spec.md` | `domains/{domain}/{domain}.spec.md` | u-spec-writer |
| `TEMPLATE.back.md` | `domains/{domain}/back/{domain}.back.md` | u-spec-back |
| `TEMPLATE.front.md` | `{SPECS_DIR}/front/front.md` (global frontend spec) | u-spec-front |
| `TEMPLATE.feature.spec.md` | `{SPECS_DIR}/front/features/*.feature.spec.md` | u-spec-front |
| `TEMPLATE.flow.md` | `{SPECS_DIR}/front/flow.md` | u-spec-front |
| `TEMPLATE.component.spec.md` | `design-system/components/*.spec.md` | u-fe-spec-writer |
| `TEMPLATE.decisions.md` | `{SPECS_DIR}/decisions.md` | u-spec-writer |
| `TEMPLATE.design-system-rules.md` | `front/design-system-rules.md` | u-spec-front |
| `TEMPLATE.design-system/` | `design-system/` bundle (`_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`) | u-spec-front |
| `FRONTEND-MANDATORY-ARTIFACTS.md` | single source of truth for the frontend design-system artifacts the front pipeline must produce and the validator blocks on (F-07) | u-spec-front (produces), u-spec-validator (gates) |

## Constraints

- Templates contain `<!-- INSTRUCTION: ... -->` placeholders — producers MUST resolve every placeholder; none may survive into generated artifacts
- Identifier prefixes used across templates follow the global pattern defined in `u-spec-globals/conventions.md` (UC, BR, ST, EV, UI, FL)
