# Skills

Skills are reusable pattern libraries consumed by agents (not orchestrators). They provide templates, conventions, checklists, and quality rules that agents reference during execution.

## Skill catalog by pipeline

| Pipeline | Skills | Description |
|----------|--------|-------------|
| **[Spec](spec.md)** | 5 skills | Writing, review, validation, globals, templates |
| **[Backend](backend.md)** | 3 skills + templates | Development, standards, QA |
| **[Frontend](frontend.md)** | 4 skills + templates | Development, standards, QA, UI |
| **[Reverse Spec](reverse-spec.md)** | 2 skills | Mapping rules, analysis patterns |

## How skills are loaded

Skills are embedded into agent context during activation by the orchestrator. Each agent receives only the skills it needs:

- **Writer** receives: `u-spec-writing`, `u-spec-globals`, `u-spec-templates`
- **Reviewer** receives: `u-spec-review`, `u-spec-globals`
- **Validator** receives: `u-spec-validation`, `u-spec-globals`
- **BE Developer** receives: `u-be-development`, `u-be-standards`
- **FE Developer** receives: `u-fe-development`, `u-fe-standards`
- **BE QA** receives: `u-be-qa-docs`, `u-be-standards`
- **FE QA** receives: `u-fe-qa-docs`, `u-fe-standards`
- **UI Agent** receives: `u-fe-ui`
- **Planner** receives: `u-planning`
- **Analyzer** receives: `u-reverse-spec-analysis`

## Skill vs protocol

- **Skills** provide knowledge (templates, patterns, rules) -- consumed by agents
- **Protocols** define behavior (when to do what) -- activated by orchestrators
