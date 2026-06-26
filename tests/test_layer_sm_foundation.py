"""Layer SM Foundation — StateMachine + Action + sm_runner.py CLI.

Task 00 of the sm-refactor plan (extras/sm-refactor/tasks/00-foundation.md).
Red phase: these tests must fail before the green phase implements the API.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

DIST_LIB = Path(__file__).parent.parent / "dist" / ".claude" / "lib"
sys.path.insert(0, str(DIST_LIB))


class TestStateMachineSkeleton:
    def test_action_dataclass_has_name_and_params(self):
        from orch_core import Action

        a = Action(name="dispatch", params={"mode": "standard"})
        assert a.name == "dispatch"
        assert a.params == {"mode": "standard"}

    def test_action_default_params_is_empty_dict(self):
        from orch_core import Action

        a = Action(name="noop")
        assert a.params == {}

    def test_state_machine_evaluate_returns_action_first_match_wins(self):
        from orch_core import Action, StateMachine

        transitions = {
            ("ready", lambda i: i["x"] == 1): Action("a1", {}),
            ("ready", lambda i: i["x"] == 2): Action("a2", {}),
        }
        sm = StateMachine(transitions)
        assert sm.evaluate("ready", {"x": 1}).name == "a1"
        assert sm.evaluate("ready", {"x": 2}).name == "a2"

    def test_no_match_returns_no_match_action(self):
        from orch_core import Action, StateMachine

        sm = StateMachine({("ready", lambda i: False): Action("never", {})})
        result = sm.evaluate("ready", {"x": 1})
        assert result.name == "no_match"

    def test_state_filter_isolates_transitions(self):
        from orch_core import Action, StateMachine

        sm = StateMachine(
            {
                ("a", lambda i: True): Action("from_a", {}),
                ("b", lambda i: True): Action("from_b", {}),
            }
        )
        assert sm.evaluate("a", {}).name == "from_a"
        assert sm.evaluate("b", {}).name == "from_b"
        assert sm.evaluate("c", {}).name == "no_match"

    def test_predicate_exception_is_swallowed_and_skips_transition(self):
        from orch_core import Action, StateMachine

        sm = StateMachine(
            {
                ("ready", lambda i: i["missing_key"] == 1): Action("unsafe", {}),
                ("ready", lambda i: True): Action("safe_fallback", {}),
            }
        )
        result = sm.evaluate("ready", {"x": 1})
        assert result.name == "safe_fallback"


class TestSmRunnerCli:
    def test_runner_help_succeeds(self):
        result = subprocess.run(
            ["python3", str(DIST_LIB / "sm_runner.py"), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "machine" in result.stdout.lower()

    def test_runner_list_returns_json_with_registered_machines_key(self):
        result = subprocess.run(
            ["python3", str(DIST_LIB / "sm_runner.py"), "--list"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert "registered_machines" in data
        assert isinstance(data["registered_machines"], list)

    def test_runner_unknown_machine_returns_exit_1(self):
        result = subprocess.run(
            ["python3", str(DIST_LIB / "sm_runner.py"), "--machine", "ghost", "--inputs", "{}"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        combined = (result.stdout or "") + (result.stderr or "")
        assert "unknown_machine" in combined

    def test_runner_invalid_inputs_json_returns_exit_1(self):
        result = subprocess.run(
            [
                "python3",
                str(DIST_LIB / "sm_runner.py"),
                "--machine",
                "ghost",
                "--inputs",
                "{not valid json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
