# Reverse Spec Pipeline Skills

Skills used by agents in the Reverse Spec team.

## u-reverse-spec

**Consumer**: Reverse Spec Writer

Primary reverse engineering skill:
- Mapping rules between code artifacts and spec artifacts
- Generation rules and quality criteria
- Draft status conventions
- Uncertainty marking (`<!-- TO CONFIRM -->`)
- Template compliance for generated specs

## u-reverse-spec-analysis

**Consumer**: Reverse Spec Analyzer

Source code analysis patterns for identifying project elements across multiple stacks:
- Entity detection patterns (models, schemas, data structures)
- Endpoint detection patterns (routes, controllers, handlers)
- Business rule extraction patterns (validations, guards, middleware)
- Event detection patterns (emitters, listeners, queues)
- UI structure patterns (components, pages, layouts)
- State management detection
- Data fetching pattern detection

The skill contains framework-specific search patterns that enable the Analyzer to work with different technology stacks without hardcoding assumptions. The actual stack is auto-detected from the project's dependency manifests and file structure.
