# Orchestration Engine

Multi-phase Claude Code orchestration system. Event-sourced, phase-agnostic workflow dispatcher.

## Requirements

- Python 3.10+
- Claude Code v2.1+
- Linux / macOS / WSL2

## Setup

```bash
pip install -r requirements-dev.txt
```

## Running tests

```bash
pytest                          # all tests
pytest --cov=.claude/lib        # with coverage
pytest tests/test_event.py      # single file
```

## Project layout

```
.claude/lib/orch_core.py    ← shared library (event sourcing engine)
.claude/skills/             ← orch-log, orch-state, orch-report
.claude/agents/             ← orchestrator + workers
.claude/hooks/              ← on_subagent_stop, on_stop
.claude/scripts/            ← preflight, circuit_breaker, dlq_triage
tests/                      ← pytest suite
```

## Linting

```bash
ruff check .claude/lib
```
