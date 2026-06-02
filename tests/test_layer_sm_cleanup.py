"""Layer SM — final cleanup verification.

Task 10 of the sm-refactor plan (extras/sm-refactor/tasks/10-cleanup-validation.md).
This task verifies the refactor is complete: every orchestrator delegates to
sm_runner.py, every transition table is registered, no residual conditional
logic remains in bash blocks, and zero external deps were introduced.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
DIST = REPO / "dist" / ".claude"
DIST_LIB = DIST / "lib"
DIST_AGENTS = DIST / "agents"
sys.path.insert(0, str(DIST_LIB))


class TestAllOrchestratorsUseSm:
    @pytest.mark.parametrize(
        "orch",
        [
            "orchestrator.md",
            "orchestrator-sdd.md",
            "orchestrator-dev.md",
            "orchestrator-review.md",
            "orchestrator-test.md",
        ],
    )
    def test_orchestrator_calls_sm_runner(self, orch):
        path = DIST_AGENTS / orch
        content = path.read_text()
        assert "sm_runner.py" in content, f"{orch} must call sm_runner.py"

    def test_all_5_machines_registered(self):
        result = subprocess.run(
            ["python3", str(DIST_LIB / "sm_runner.py"), "--list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        registered = set(data["registered_machines"])
        assert registered >= {"meta", "sdd", "dev", "review", "test"}, (
            f"Missing machines: {{'meta', 'sdd', 'dev', 'review', 'test'}} - {registered}"
        )


class TestNoResidualConditionalsInOrchestrators:
    """Patterns that should ONLY appear in narrative/pseudocode, not in ```bash blocks."""

    FORBIDDEN_PATTERNS_IN_BASH = [
        # SDD
        (r"\btrigger\s*==\s*\"u-improve\"\s*AND\s*mode_hint", "S5/S6 effective_mode derivation"),
        (r"^if\s+.*greenfield\s*==\s*true", "S8 greenfield routing"),
        (r"\brepair_cycles\s*<\s*2\b", "S16 repair loop check"),
        # Dev
        (r"^if\s+.*\bstack\s*==\s*\"fullstack\"", "D8 stack-conditional"),
        (r"^if\s+.*\bplanner_required\s*==\s*false", "D7 planner skip"),
        (r"^if\s+.*\bdev_impact\s*==\s*\"no_action\"", "D6 short-circuit"),
        # Review
        (r"^if\s+.*\ball_qa_mode_micro\s*==", "R10 auto-approval check"),
        (r"^max_concurrent\s*=\s*[0-9]", "R9 dynamic concurrency literal"),
        # Test
        (r"^if\s+.*nesting_depth\s*>=\s*3", "T1 nesting guard"),
        # Meta
        (r"^if\s+.*current_phase\s*==\s*\"(sdd|dev|review|test)\"", "M7 phase routing"),
    ]

    @pytest.mark.parametrize(
        "orch_file",
        list((DIST_AGENTS).glob("orchestrator*.md")),
        ids=lambda p: p.name,
    )
    def test_no_forbidden_patterns_in_bash_blocks(self, orch_file):
        content = orch_file.read_text()
        # Extract only ```bash blocks (not all code blocks — pseudocode in plain ```
        # is allowed as documentation).
        bash_blocks = re.findall(r"```bash\n(.*?)\n```", content, re.DOTALL)
        bash_text = "\n".join(bash_blocks)
        violations = []
        for pattern, label in self.FORBIDDEN_PATTERNS_IN_BASH:
            if re.search(pattern, bash_text, re.IGNORECASE | re.MULTILINE):
                violations.append(f"{orch_file.name}: residual '{label}' (pattern: {pattern})")
        assert not violations, "\n".join(violations)


class TestAllTransitionTablesPresent:
    @pytest.mark.parametrize(
        "name",
        [
            "META_TRANSITIONS",
            "SDD_TRANSITIONS",
            "DEV_TRANSITIONS",
            "REVIEW_TRANSITIONS",
            "TEST_TRANSITIONS",
        ],
    )
    def test_transition_table_exists_and_nonempty(self, name):
        import orch_core

        table = getattr(orch_core, name, None)
        assert table is not None, f"orch_core must export {name}"
        assert len(table) > 0, f"{name} must have at least one transition"


class TestAllStateMachineSubclassesPresent:
    @pytest.mark.parametrize(
        "name",
        [
            "MetaStateMachine",
            "SddStateMachine",
            "DevStateMachine",
            "ReviewStateMachine",
            "TestPhaseStateMachine",
        ],
    )
    def test_state_machine_subclass_exists(self, name):
        import orch_core

        cls = getattr(orch_core, name, None)
        assert cls is not None, f"orch_core must export {name}"


class TestNoExternalDependencies:
    STDLIB = {
        "sys", "os", "json", "re", "dataclasses", "enum", "pathlib",
        "typing", "datetime", "collections", "subprocess", "uuid", "hashlib",
        "argparse", "io", "shutil", "tempfile", "functools", "itertools",
        "abc", "copy", "time", "logging", "warnings", "__future__",
        "fcntl", "random",
    }

    def test_orch_core_stdlib_only(self):
        content = (DIST_LIB / "orch_core.py").read_text()
        imports = re.findall(r"^(?:from |import )(\S+)", content, re.MULTILINE)
        for imp in imports:
            top = imp.split(".")[0]
            assert top in self.STDLIB, f"non-stdlib import in orch_core.py: {imp}"

    def test_sm_runner_stdlib_only(self):
        content = (DIST_LIB / "sm_runner.py").read_text()
        imports = re.findall(r"^(?:from |import )(\S+)", content, re.MULTILINE)
        allowed = self.STDLIB | {"orch_core"}
        for imp in imports:
            top = imp.split(".")[0]
            assert top in allowed, f"non-stdlib import in sm_runner.py: {imp}"


class TestSmRefactorEndToEnd:
    """Smoke test — exercise one transition per machine end-to-end via CLI."""

    @pytest.mark.parametrize(
        "machine,state,inputs,expected_action",
        [
            ("test", "entry", {"nesting_depth": 3}, "block"),
            ("meta", "phase_entry", {"current_phase": "sdd"}, "spawn_phase_orchestrator"),
            ("dev", "post_manifest", {"handoff_type": "fast_track", "dev_impact": "no_action"}, "exit_vacuous"),
            ("review", "classify_qa_mode_done", {"qa_mode": "micro", "rationale": "x"}, "create_qa_task"),
            ("sdd", "triage_done", {"type": "implementation_only", "trigger": "u-improve", "mode_hint": "full"}, "exit_no_spec_change"),
        ],
    )
    def test_machine_runtime_smoke(self, machine, state, inputs, expected_action):
        result = subprocess.run(
            [
                "python3",
                str(DIST_LIB / "sm_runner.py"),
                "--machine",
                machine,
                "--state",
                state,
                "--inputs",
                json.dumps(inputs),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["action"] == expected_action
