# Spec Templates

5 specification templates stored in `{SPECS_DIR}/_templates/`. Used by the Spec Writer and Front Spec Agent.

## 1. TEMPLATE.spec.md

Domain specification template:
- Vision and scope
- Actors/personas
- Use Cases (UC-NN) with pre/post conditions
- Business Rules summary
- State machine overview
- Error codes
- Out-of-scope
- Glossary

## 2. TEMPLATE.back.md

Backend technical specification template:
- Technology stack reference (from CLAUDE.md)
- Data model (entities, relationships, indexes)
- Business Rules (BR-NN) with implementation detail
- State Machines (ST-NN) with transitions
- Domain Events (EV-NN) with payloads
- Integration points
- Technical constraints

## 3. TEMPLATE.front.md

Frontend technical specification template:
- Technology stack reference (from CLAUDE.md)
- State management approach
- Data fetching patterns
- Error handling strategy
- Component architecture

## 4. TEMPLATE.screen.md

Screen specification template:
- Domains consumed (which backend domains this screen uses)
- UI States (UI-NN): loading, empty, error, success
- Behaviors and interactions
- API requests mapped to UI elements
- Validations
- Error mapping (HTTP status -> UI handling)

## 5. TEMPLATE.flow.md

Navigation flow template:
- Screens involved
- Happy path (step-by-step)
- Alternative paths
- Navigation rules and guards
- Error recovery paths

## Design system templates

Additional templates for the design system reference:
- **TEMPLATE.design-system/**: `_index.md`, `tokens.md`, `composition.md`, `components.md`, `implementation.md`
- **TEMPLATE.design-system-rules.md**: Token and rule quick reference
