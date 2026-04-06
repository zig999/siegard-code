## Context Mounting — UI Agent

**Agent:** `.claude/agents/dev/u-fe-ui.md`

### Activation prompt structure

```
Read in parallel:
- CLAUDE.md
- [relevant data — see extraction below]
- .claude/agents/dev/u-fe-ui.md

[task instruction]
```

> **Note:** the skill `u-fe-ui` is embedded in the agent's system prompt (`u-fe-ui.md`). **DO NOT** re-inject it in the activation prompt.

### Context extraction (token reduction)

### Design System (selective context for UI Agent)

The UI Agent references tokens and components — it needs more context than the Developer.

**Always include:**
```
## Design System — Rules (extracted from {SPECS_DIR}/front/design-system-rules.md)
[full content]
```

**Always include for the UI Agent (differs from Developer):**
```
## Design System — Tokens (extracted from {SPECS_DIR}/front/design-system/tokens.md)
[full content — UI Agent needs all tokens to reference]

## Design System — Components (extracted from {SPECS_DIR}/front/design-system/components.md)
[full content — UI Agent needs the catalog to specify screens]
```

**Include conditionally:**

| Epic type | Additional file |
|---|---|
| Dashboard, metrics, complex layout | `design-system/composition.md` |
| Visual review, accessibility | `design-system/implementation.md` |

> **Rule:** the UI Agent receives more context than the Developer because it **specifies** the screens. If a needed token does not exist, the UI Agent must flag it to the Orchestrator (do not invent tokens).

#### Spec-first mode (when {SPECS_DIR} exists with approved domains)

Copy into the prompt:
```
## Target Epic and Stories (extracted from backlog.md)
[EPIC-XX block with objective and its Stories]

## Available Screen Specs (extracted from {SPECS_DIR}/front/screens/)
[full content of relevant .screen.md for screens in this Epic]
[include: UI-NN states, error mapping, input validations]

## Available Flow Specs (extracted from {SPECS_DIR}/front/_flows/)
[content of .flow.md whose screens correspond to this Epic]
[include: happy path, alternative flows, navigation rules FL-NN]

```

> **Instruction to the UI Agent:** Screen Specs are the mandatory base. Complement with layout, components, visual hierarchy, and styles. DO NOT contradict states, errors, or validations already defined in the screen spec.

#### Improve mode (without {SPECS_DIR})

Copy into the prompt:
```
## Target Epic and Stories (extracted from backlog.md)
[EPIC-XX block with objective and its Stories]

## Reference improvements (extracted from original improve##.md)
[description, location, and desired behavior of each improvement linked to the Epic]

> Use the improvement descriptions and the project's existing code
> as reference for visual specification.
> Prioritize consistency with what already exists in the project.
```
