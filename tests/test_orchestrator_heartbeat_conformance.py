"""Conformance: every phase orchestrator emits `orchestrator_heartbeat` (rec #3 / CONF-05).

Regression guard for the `consulta-web-report` finding: only `orchestrator-dev` emitted
`orchestrator_heartbeat`, so `detect_stale_orchestrator` could not distinguish a stalled
orchestrator from a live one in sdd/review/test — the root of the 7.4h nightly stall.

`detect_stale_orchestrator` (orch_core.py) filters heartbeats by
`data.phase == current_phase`, so the `phase` string in each heartbeat MUST equal the
canonical phase name. This test asserts both the presence of the emit and the correct
phase string.

Also guards F-03: review/test must NOT synthesize `task_failed(stale_timeout)` from the
prompt — stale tasks are reaped deterministically by `check_stale.py`.
"""
import re
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1] / "dist" / ".claude" / "agents"

# Canonical phase names (orch_core.py default phase set + check_worker W04).
PHASE_ORCHESTRATORS = {
    "orchestrator-sdd.md": "sdd",
    "orchestrator-dev.md": "dev",
    "orchestrator-review.md": "review",
    "orchestrator-test.md": "test",
}

# F-03 (no in-prompt stale synthesis) is an invariant for ALL phase orchestrators —
# not only the two that violated it. Guarding all four prevents a future regression in
# any of them. agent name = filename without ".md".
IN_PROMPT_STALE_AGENTS = {fn: fn[:-3] for fn in PHASE_ORCHESTRATORS}


@pytest.mark.parametrize("filename,phase", sorted(PHASE_ORCHESTRATORS.items()))
def test_phase_orchestrator_emits_heartbeat(filename, phase):
    text = (AGENTS / filename).read_text(encoding="utf-8")
    assert "--event-type orchestrator_heartbeat" in text, (
        f"{filename} does not emit orchestrator_heartbeat — "
        "detect_stale_orchestrator cannot tell it apart from a stalled orchestrator"
    )
    # The heartbeat's phase must equal the canonical current_phase, else
    # detect_stale_orchestrator (which filters by data.phase == current_phase) never
    # sees it and always reports the orchestrator as stale.
    # Tolerate whitespace around the JSON punctuation — the guard is about the phase
    # value being canonical, not about exact formatting.
    pattern = (
        r"--event-type\s+orchestrator_heartbeat\s+--data\s+"
        r"'\{\s*\"phase\"\s*:\s*\"" + re.escape(phase) + r"\"\s*\}'"
    )
    assert re.search(pattern, text), (
        f"{filename} heartbeat does not carry the canonical "
        f"--data '{{\"phase\":\"{phase}\"}}'"
    )


@pytest.mark.parametrize("filename,agent", sorted(IN_PROMPT_STALE_AGENTS.items()))
def test_no_in_prompt_stale_synthesis(filename, agent):
    """F-03: the orchestrator must not synthesize stale_timeout from the prompt.

    The deterministic reaper (check_stale.py) is the only prompt-side path allowed to
    fail a task for staleness; an in-prompt append computes thresholds in the LLM,
    which F-03 forbids.
    """
    text = (AGENTS / filename).read_text(encoding="utf-8")
    # `synthesized_by` alone is NOT a violation — it is used legitimately elsewhere
    # (e.g. the E18 auto-approval human_response). The violation is a `--data` blob that
    # is BOTH reason=stale_timeout AND synthesized_by=<this orchestrator>. Order- and
    # whitespace-tolerant lookaheads catch a reordered reintroduction; the blob is a
    # single-quoted JSON literal ([^']*) tied to a --data argument.
    pattern = (
        r"--data\s+'\{"
        r"(?=[^']*\"reason\"\s*:\s*\"stale_timeout\")"
        r"(?=[^']*\"synthesized_by\"\s*:\s*\"" + re.escape(agent) + r"\")"
        r"[^']*\}'"
    )
    assert not re.search(pattern, text), (
        f"{filename} still synthesizes task_failed(stale_timeout) in-prompt "
        "(F-03 violation) — reap via check_stale.py instead"
    )


class TestCheckpointBlindTaskTypes:
    """2026-07-15 post-fix audit: planning and spec-triage dispatch prompts had NO
    progress-checkpoint instructions — those tasks rode their whole stale window
    (900s / 600s) in total silence, forcing the large thresholds that set every
    liveness-detection floor. Their dispatch prompts must now carry the same
    mandatory task_progress checkpoint block the impl/spec/test/review prompts have.
    """

    def _text(self, name):
        from pathlib import Path
        root = Path(__file__).parent.parent / "dist" / ".claude" / "agents"
        return (root / name).read_text(encoding="utf-8")

    def test_spec_triage_prompt_has_checkpoints(self):
        text = self._text("orchestrator-sdd.md")
        idx = text.index("subagent_type: u-spec-triage")
        block = text[idx:idx + 3000]
        assert '"checkpoint":"context_loaded"' in block
        assert '"checkpoint":"classification_complete"' in block

    def test_planner_prompts_have_checkpoints(self):
        text = self._text("orchestrator-dev.md")
        assert '"checkpoint":"specs_loaded"' in text
        assert '"checkpoint":"contracts_drafted"' in text
        # the parallel-planners path must reference the same block explicitly:
        idx = text.index("dispatch_parallel_planners")
        par_block = text[idx:idx + 6000]
        assert "Progress checkpoints" in par_block
