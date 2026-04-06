# Estimates

Token consumption and approximate time per operating mode. These are estimates based on typical usage -- actual values vary by project complexity.

## Spec pipeline estimates

| Mode | Tokens (approx) | Time (approx) | Scope |
|------|-----------------|---------------|-------|
| **New/Major** | ~19K | 7-12 min | Per domain |
| **Fast-track** | ~11K | 4-7 min | Per change |
| **Reverse-eng review** | ~14K | 5-8 min | Per domain |
| **Triage** | ~3K | 1-2 min | Per item |

### Breakdown by stage (New/Major)

| Stage | Tokens |
|-------|--------|
| Writer | ~6K |
| Reviewer | ~3K |
| Back Spec + Front Spec | ~6K |
| Validator | ~4K |

## Dev pipeline estimates

| Mode | Tokens (approx) | Time (approx) | Scope |
|------|-----------------|---------------|-------|
| **Per Story (spec-first)** | ~14K | 10-18 min | Per Story |
| **Per Story (improve)** | ~10K | 8-13 min | Per Story |

## Pre-execution estimate

Before starting, every orchestrator presents a token and time projection based on:
- Number of domains (spec) or Stories (dev)
- Operating mode
- Complexity indicators

The user can proceed or abort based on this estimate.

## Token optimization strategies

- **Short mode** reduces reactivation from ~15K to ~2K tokens
- **Context mounting** loads only what each agent needs
- **Triage** processes 5-10 items per session instead of all at once
- **Compressed logs** for sessions with 15+ Stories
