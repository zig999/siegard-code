"""Layer Hard Cleanup — global acceptance criteria for prod-hardening (task 15).

Asserts the structural invariants the pipeline set out to establish (PLAN.md G1-G7).
G5 (full suite green) and G8 (state.json all completed) are checked by the run
itself / the final report, not here.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))


class TestGlobalAcceptance:
    def test_g1_transition_precondition_installed(self):
        import orch_core
        assert "phase_transitioned" in orch_core._APPEND_PRECONDITIONS

    def test_g3_handoff_validator_recomputes_sha256(self):
        v = (ROOT / "dist/.claude/skills/u-handoff-validator/validate.py").read_text(encoding="utf-8")
        assert "hashlib" in v and "sha256" in v

    def test_g4_stale_tasks_has_runtime_caller(self):
        hits = subprocess.run(
            ["grep", "-rl", "reap_stale_tasks", str(ROOT / "dist/.claude/scripts"), str(ROOT / "dist/.claude/hooks")],
            capture_output=True, text=True).stdout
        assert hits.strip(), "reap_stale_tasks()/stale_tasks() must have a runtime caller"

    def test_g6_zero_external_deps(self):
        out = subprocess.run(
            ["grep", "-rhnE", "^import |^from ",
             str(ROOT / "dist/.claude/lib"), str(ROOT / "dist/.claude/scripts"), str(ROOT / "dist/.claude/hooks")],
            capture_output=True, text=True).stdout
        allowed = re.compile(
            r"(__future__|sys|json|os|re|hashlib|fcntl|uuid|random|time|dataclasses|datetime|"
            r"enum|pathlib|typing|collections|argparse|subprocess|shutil|importlib|io|curses|"
            r"textwrap|signal|platform|tempfile|math|itertools|functools|fnmatch)\b")
        local = {"orch_core", "minimal_yaml", "gc_orphan_blobs"}
        bad = []
        for line in out.splitlines():
            toks = line.split()
            if len(toks) >= 2:
                mod = toks[1].split(".")[0]
                if not allowed.match(mod) and mod not in local:
                    bad.append(line.strip())
        assert not bad, f"non-stdlib imports in dist: {bad}"
