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
| **E2E integration (fullstack)** | ~3K | 2-4 min | Per session |

### Fullstack overhead

Fullstack sessions run BE and FE phases sequentially, so total time is additive. The E2E integration validation adds ~3K tokens when cross-domain stories exist. The meta-orchestrator itself has minimal overhead (~1K tokens for phase coordination).

## Pre-execution estimate

Before starting, every orchestrator presents a token and time projection based on:
- Number of domains (spec) or Stories (dev)
- Operating mode
- Complexity indicators
- For fullstack: stories per phase and cross-domain story count

The user can proceed or abort based on this estimate.

## Token optimization strategies

- **Short mode** reduces reactivation from ~15K to ~2K tokens
- **Context mounting** loads only what each agent needs
- **Triage** processes 5-10 items per session instead of all at once
- **Compressed logs** for sessions with 15+ Stories
- **Scope filtering** in fullstack mode ensures each phase loads only relevant stories
