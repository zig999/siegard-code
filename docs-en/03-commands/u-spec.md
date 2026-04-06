# /u-spec -- Specification Command

Creates or evolves technical specifications through a multi-agent pipeline.

## Usage

```
/u-spec [SPECS_DIR] [SESSION]
```

## Pipeline

```
Writer -> Reviewer -> Back Spec Agent(s) -> Validator -> Front Spec Agent -> Validator -> Handoff
```

- **Writer** creates `openapi.yaml` + `{domain}.spec.md`
- **Reviewer** approves or rejects (max 3 rejection cycles)
- **Back Spec Agent** produces `{domain}.back.md` per domain
- **Validator** performs incremental validation after each `.back.md`
- **Front Spec Agent** runs after ALL `.back.md` files are valid (screens compose multiple domains)
- **Validator** performs final cross-reference validation
- **Handoff** packages artifacts for the Dev team

## Mode detection

The orchestrator automatically detects the operating mode:

| Mode | Trigger | Behavior |
|------|---------|----------|
| **New domain** | No `{SPECS_DIR}` exists | Full pipeline from scratch |
| **Reverse-eng review** | `origin-reverse-spec.md` found in `_meta/` | Review draft specs from `/u-reverse-spec` |
| **Merge review** | `merge-pending-review.md` exists | Review merge results with existing specs |
| **New with structure** | `{SPECS_DIR}` exists but new domain requested | Add domain to existing structure |
| **Resume** | `log-orchestrator-spec.md` exists with incomplete stages | Resume from last completed stage |

## Fast-track

For minor/patch changes, a simplified pipeline is activated:
- **Writer** -> **Reviewer** (delta-focused) -> **Validator** (incremental)
- Skips Back/Front agents when their artifacts are not impacted

## Generated artifacts

- `openapi.yaml` per domain
- `{domain}.spec.md` -- Use cases, business rules, state machines
- `{domain}.back.md` -- Backend technical specification
- `front.md` -- Global frontend specification
- `{screen}.screen.md` -- Per-screen UI specification
- `{flow}.flow.md` -- Navigation flow specification
- `openapi.root.yaml` -- Root aggregator
- `log-orchestrator-spec.md` -- Orchestrator execution log

## Estimates

- **New/Major**: ~19K tokens, 7-12 min per domain
- **Fast-track**: ~11K tokens, 4-7 min
- **Reverse-eng review**: ~14K tokens, 5-8 min
