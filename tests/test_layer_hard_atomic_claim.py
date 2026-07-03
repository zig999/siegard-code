"""Layer Hard Atomic Claim — dispatch serialization protocol (double-dispatch fix).

Two concurrent orchestrator instances can read the same READY batch before
either claim lands (eternal audit, log seqs 774-788). The fix is claim.py:
an atomic check-and-append under the log lock. This layer enforces the
protocol side: every phase orchestrator emits task_claimed exclusively via
claim.py (never via append.py) and documents the claimed:false drop rule.
The runtime side (claim_task) is covered by tests/orch/test_claim.py.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

ORCHESTRATORS = [
    "orchestrator-sdd.md",
    "orchestrator-dev.md",
    "orchestrator-review.md",
    "orchestrator-test.md",
]


def _src(name: str) -> str:
    return (ROOT / "dist/.claude/agents" / name).read_text(encoding="utf-8")


class TestClaimScriptExists:
    def test_claim_py_shipped(self):
        assert (ROOT / "dist/.claude/skills/orch-log/scripts/claim.py").is_file()

    def test_claim_task_exported(self):
        import sys
        sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))
        import orch_core
        assert callable(orch_core.claim_task)
        assert "claim_task" in orch_core.__all__

    def test_skill_md_documents_claim(self):
        skill = (ROOT / "dist/.claude/skills/orch-log/SKILL.md").read_text(encoding="utf-8")
        assert "scripts/claim.py" in skill
        assert '"claimed": false' in skill.lower() or '"claimed": False' in skill


class TestOrchestratorsUseAtomicClaim:
    def test_no_task_claimed_via_append(self):
        """task_claimed MUST go through claim.py — an append.py emission
        bypasses the atomic eligibility re-check and reopens the race."""
        for name in ORCHESTRATORS:
            src = _src(name)
            for block in re.findall(r"append\.py.*?(?:```|$)", src, flags=re.DOTALL):
                assert "--event-type task_claimed" not in block, (
                    f"{name}: task_claimed emitted via append.py (must use claim.py)"
                )

    def test_every_orchestrator_calls_claim_py(self):
        for name in ORCHESTRATORS:
            assert "orch-log/scripts/claim.py" in _src(name), (
                f"{name}: no claim.py invocation found"
            )

    def test_every_orchestrator_handles_claimed_false(self):
        """The drop rule must be spelled out: a claimed:false task leaves the
        batch and is never spawned."""
        for name in ORCHESTRATORS:
            src = _src(name)
            assert '"claimed": false' in src, (
                f"{name}: missing claimed:false handling instruction"
            )

    def test_i5_invariant_references_atomic_claim(self):
        for name in ORCHESTRATORS:
            src = _src(name)
            i5 = [l for l in src.splitlines() if l.startswith("| I5 |")]
            assert i5 and "claim.py" in i5[0], (
                f"{name}: I5 invariant must mandate claim.py"
            )
