# Protocol: Spec Agent Context Mounting

## Purpose
Define exactly which files each agent must load before starting its work. Irrelevant context degrades generation quality.

## General rule
The Orchestrator must pass **ONLY** the files listed below to each agent. Never the entire folder.

## Context per agent

### Spec Writer
```
MANDATORY:
  .claude/skills/u-spec-globals/conventions.md
  .claude/skills/u-spec-globals/error-codes.md
  .claude/skills/u-spec-globals/glossary.md
  .claude/skills/u-spec-templates/TEMPLATE.spec.md
  .claude/skills/u-spec-writing/SKILL.md
  {user requirement}

CONDITIONAL (if change request):
  domains/{domain}/openapi.yaml (current version)
  domains/{domain}/{domain}.spec.md (current version)
  Previous review report (if resubmission)
```

### Spec Reviewer
```
MANDATORY:
  domains/{domain}/openapi.yaml
  domains/{domain}/{domain}.spec.md
  .claude/skills/u-spec-globals/conventions.md
  .claude/skills/u-spec-globals/error-codes.md
  .claude/skills/u-spec-review/SKILL.md

CONDITIONAL (if fast-track):
  Diff of changes vs previous version

CONDITIONAL (if reverse engineering review):
  {SPECS_DIR}/_temp/analysis-report.md — code analysis report that originated the specs
  {SPECS_DIR}/_meta/origin-reverse-spec.md — generation metadata (stack, domains, gaps)
```

### Back Spec Agent
```
MANDATORY:
  domains/{domain}/openapi.yaml (APPROVED)
  domains/{domain}/{domain}.spec.md (APPROVED)
  .claude/skills/u-spec-globals/conventions.md
  .claude/skills/u-spec-templates/TEMPLATE.back.md
  .claude/skills/u-spec-back-writing/SKILL.md
  CLAUDE.md (stack section)

CONDITIONAL (if rewrite after validation):
  Spec Validator report
```

### Front Spec Agent
```
MANDATORY:
  domains/{domain}/openapi.yaml (APPROVED) — one for each domain involved in the features
  domains/{domain}/{domain}.spec.md (APPROVED) — one for each domain
  .claude/skills/u-spec-globals/error-codes.md
  .claude/skills/u-spec-templates/TEMPLATE.front.md
  .claude/skills/u-spec-templates/TEMPLATE.feature.spec.md
  .claude/skills/u-spec-templates/TEMPLATE.component.spec.md
  .claude/skills/u-spec-templates/TEMPLATE.flow.md
  CLAUDE.md (stack section)

CONDITIONAL (if front.md already exists — additional feature):
  front/front.md (current version — to update instead of rewriting from scratch)

CONDITIONAL (design-system does not exist — creating):
  .claude/skills/u-spec-templates/TEMPLATE.design-system/_index.md
  .claude/skills/u-spec-templates/TEMPLATE.design-system/tokens.md
  .claude/skills/u-spec-templates/TEMPLATE.design-system/composition.md
  .claude/skills/u-spec-templates/TEMPLATE.design-system/components.md
  .claude/skills/u-spec-templates/TEMPLATE.design-system/implementation.md
  .claude/skills/u-spec-templates/TEMPLATE.design-system-rules.md

CONDITIONAL (design-system exists — updating):
  {SPECS_DIR}/front/design-system/_index.md

CONDITIONAL (if rewrite after validation):
  Spec Validator report
  front/features/{feature}.feature.spec.md affected (only the invalidated ones)
```

### Spec Validator
```
MANDATORY:
  domains/{domain}/openapi.yaml
  domains/{domain}/{domain}.spec.md
  .claude/skills/u-spec-globals/error-codes.md
  .claude/skills/u-spec-validation/SKILL.md

INCREMENTAL — back phase (as available):
  domains/{domain}/back/{domain}.back.md

INCREMENTAL — front phase (after Front Spec Agent completes):
  front/front.md
  front/features/{feature}.feature.spec.md (all features for the requirement)
  front/_flows/{flow}.flow.md (all flows for the requirement)
  domains/{domain}/openapi.yaml for each domain consumed by the features
```

## Short mode (reactivation in the same session)
When an agent is reactivated in the same session (e.g., after a rejection cycle), load only:
1. Report/feedback that motivated the reactivation
2. File(s) that need modification
3. DO NOT reload skills and templates (already in context)
