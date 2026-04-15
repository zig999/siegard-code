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

**Before injecting any design system file, extract from `CLAUDE.md`:**

| Field | Location in CLAUDE.md | Used for |
|---|---|---|
| `design_system.path` | header | Resolves the path to `tokens.md`, `components.md`, etc. |
| `design_system.token_prefix` | header | CSS custom property prefix for design tokens (e.g. `"--color-"`) |
| `design_system.component_library` | header | UI Agent references components by exact library name |
| `design_system.color_mode` | header | UI Agent applies correct dark/light token variants |
| `design_system.enforce_tokens` | header | If `false`, downgrade token violation findings from BUG to Warning in the spec |
| `design_system.motion_policy` | header | If `strict`, UI Agent must reference `--duration-*` + `--ease-*` tokens in all interaction specs |

> `design_system` block is optional. If absent or partially filled, apply the canonical defaults defined in the `CLAUDE.md` template comment block: `path = {specs_dir}/front/design-system/`, `token_prefix = "--color-"`, `color_mode = both`, `component_library = none`, `enforce_tokens = true`, `motion_policy = strict`.

**Always include:**
```
## Design System — Rules (extracted from {SPECS_DIR}/front/design-system-rules.md)
[full content]

## Design System — Config (extracted from CLAUDE.md design_system block)
component_library: {value}
color_mode: {value}
motion_policy: {value}
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

Inject in this order — the UI Agent reads primary sources before secondary:

```
## Available Feature Specs (extracted from {SPECS_DIR}/front/features/)
[full content of relevant .feature.spec.md for features in this Epic]
[include ALL sections: §2 States, §3 Transition Table, §5 Validations, §6 Error Mapping, §9 BDD Scenarios]
[§2, §3, §5, §6 are LOCKED — agent must not contradict them]
[§9 BDD Scenarios are the acceptance contract — agent must make every scenario visually realizable]

## Available Flow Specs (extracted from {SPECS_DIR}/front/_flows/)
[content of .flow.md whose features correspond to this Epic]
[include: happy path, alternative flows, navigation rules FL-NN]

## Component Specs (conditional — include only if §7 of any feature spec references components)
[for each component listed in §7 of the relevant feature specs:]
[§2 Props Contract + §3 Component States + §5 Variants from {SPECS_DIR}/front/components/{name}.component.spec.md]

## Front Spec Global (extracted from {SPECS_DIR}/front/front.md)
[stack, component patterns, routing conventions]

## Target Epic and Task Contracts (extracted from backlog.md)
[EPIC-XX block with objective and its Task Contracts]
```

> **Instruction to the UI Agent:** Feature Specs (feature.spec.md) are the primary source — start by extracting all UI-NN states from §2, FL-NN flows from §3, and §9 BDD scenarios. §2 States, §3 Transitions, §5 Validations, and §6 Error Mapping are LOCKED. Your job is to add the visual layer: layout, component selection, tokens, visual hierarchy, interactions, and accessibility. Every §9 scenario must be visually realizable in your spec — verify coverage before declaring ready_for_development: true. If a §9 scenario requires a state not present in §2, flag it with Warning for the Spec Team — do not invent states.


#### Improve mode (without {SPECS_DIR})

Copy into the prompt:
```
## Target Epic and Task Contracts (extracted from backlog.md)
[EPIC-XX block with objective and its Task Contracts]

## Reference improvement scope (extracted from improve_scope block in log-orchestrator-dev.md)
[description, location (affected_specs), and desired behavior of each improvement linked to the Epic]
```

> In improve mode there are no feature.spec.md files. The UI Agent defines states from scratch using the improvement descriptions and the project's existing code as reference. Prioritize visual consistency with what already exists in the project. The ui-spec-gate fields `ui_nn_covered` and `bdd_scenarios_covered` may be omitted or left empty in this mode.
