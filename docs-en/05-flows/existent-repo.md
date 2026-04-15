# Applying SDD Standards to an Existing Repository

## Overview

Use this flow when a project already has code and/or documentation and you need to migrate everything to the SDD standard established in `dist/`.

---

## Recommended Flow

### Step 1 — Install `dist/` in the Target Project

```bash
cp -r dist/agents/   /your-project/.claude/agents/
cp -r dist/commands/ /your-project/.claude/commands/
cp -r dist/skills/   /your-project/.claude/skills/
```

Create `CLAUDE.md` from the template in `dist/templates/`:

```markdown
domain: fullstack | backend | frontend
stack: <your stack>
specs_dir: docs/specs
sessions_dir: .sessions
```

---

### Step 2 — Run `/u-reverse-spec`

**This is the correct entry point for projects with existing code.**

```
/u-reverse-spec {SPECS_DIR}
```

Internal pipeline:

```
Analyzer (u-reverse-spec-analyzer.md)
  ├─ Detects language/framework via u-reverse-spec-detection.md
  ├─ Maps code structure (routes, entities, contracts)
  └─ Reads existing documentation as additional context

Writer (u-reverse-spec-writer.md)
  ├─ Generates drafts: openapi.yaml, domain.spec.md, .back.md
  └─ Marks all artifacts with status: draft | needs-review
```

The `u-reverse-spec-merge.md` protocol manages the merge strategy when documentation already exists — it reconciles what the code says vs. what the docs say.

---

### Step 3 — Refine via `/u-spec` (reverse-eng review mode)

After the reverse-spec generates drafts, the Spec Orchestrator automatically detects the `reverse-eng review` mode when it finds `origin-reverse-spec.md`:

```
/u-spec {SPECS_DIR}
```

Pipeline in this mode:

```
Spec Reviewer
  └─ Reviews generated drafts (skips the Writer)

Back Spec Agent(s)
  └─ Deepens technical specs per domain

Front Spec Agent
  └─ Generates features (.feature.spec.md), flows, design-system if applicable

Spec Validator
  └─ Cross-reference: openapi.yaml ↔ .back.md ↔ .front.md
  └─ Produces final handoff-manifest.yaml
```

---

## Complete Flow Diagram

```
Existing project (code + legacy docs)
          │
          ▼
  /u-reverse-spec          ← entry point
   Analyzer + Writer
   (uses existing docs as context)
          │
          ▼
  drafts in {SPECS_DIR}/
  [origin-reverse-spec.md created]
          │
          ▼
  /u-spec                  ← detects reverse-eng review mode
   Reviewer → Back → Front → Validator
          │
          ▼
  approved specs in SDD standard
  handoff-manifest.yaml
```

---

## Edge Cases

| Situation | Behavior |
|---|---|
| Existing docs contradict the code | `u-reverse-spec-merge.md` resolves: code is source of truth |
| Existing docs are partially in SDD format | Analyzer absorbs what is valid, Writer completes the rest |
| Only code exists, no documentation | Analyzer infers everything; Writer generates specs from scratch |
| Very large documentation | Analyzer uses selective context mounting (only relevant sections per domain) |

---

## Final Output

After the full cycle, the project will have:

```
{specs_dir}/
├── _global/
│   ├── conventions.md
│   ├── glossary.md
│   └── error-codes.md
├── domains/{domain}/
│   ├── {domain}.spec.md
│   └── {domain}.back.md
├── front/
│   ├── front.md
│   ├── features/
│   │   └── {feature}.feature.spec.md
│   ├── components/
│   │   └── {name}.component.spec.md
│   ├── _flows/
│   │   └── {flow}.flow.md
│   └── design-system/
├── openapi.yaml
└── handoff-manifest.yaml
```

All documentation in SDD standard, ready to be consumed by `/u-dev` in future development cycles.

---

## Related

- [Reverse Spec Team](../04-teams/reverse-spec/README.md)
- [Reverse Spec Merge Protocol](../06-protocols/reverse-spec-merge.md)
- [Spec-First Flow](spec-first.md)
- [`/u-reverse-spec` command](../03-commands/u-reverse-spec.md)
- [`/u-spec` command](../03-commands/u-spec.md)
