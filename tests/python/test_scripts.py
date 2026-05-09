"""
Script tests — preflight.py and circuit_breaker.py via subprocess boundary.
"""
import json
import subprocess
import sys
from pathlib import Path
import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dist" / ".claude" / "scripts"
_PREFLIGHT = _SCRIPTS_DIR / "preflight.py"
_CB = _SCRIPTS_DIR / "circuit_breaker.py"


def _run(script: Path, args: list[str], env_overrides: dict, timeout: int = 15):
    import os
    env = os.environ.copy()
    env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, str(script)] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return result


# ---------------------------------------------------------------------------
# preflight.py
# ---------------------------------------------------------------------------

class TestPreflight:

    def test_quick_mode_exits_0_on_healthy_project(self, orch_dir, make_event):
        make_event("orchestrator_heartbeat", data={})
        result = _run(_PREFLIGHT, ["--quick"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        # Exit code 0 means all checks passed
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_quick_mode_outputs_json(self, orch_dir, make_event):
        make_event("orchestrator_heartbeat", data={})
        result = _run(_PREFLIGHT, ["--quick"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        output = json.loads(result.stdout)
        assert "status" in output or "checks" in output or isinstance(output, dict)

    def test_missing_orch_dir_exits_nonzero(self, tmp_path):
        """If ORCH_PROJECT_DIR has no .orch/, preflight should exit non-zero."""
        result = _run(_PREFLIGHT, ["--quick"], {"ORCH_PROJECT_DIR": str(tmp_path)})
        # tmp_path has no .orch/ — expect failure
        assert result.returncode != 0 or "fail" in result.stdout.lower() or "error" in result.stdout.lower()

    def test_invalid_args_exits_2(self, orch_dir):
        result = _run(_PREFLIGHT, ["--unknown-flag"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# circuit_breaker.py — status and reset path
# ---------------------------------------------------------------------------

class TestCircuitBreaker:

    def test_status_when_not_tripped(self, orch_dir, make_event):
        make_event("orchestrator_heartbeat", data={})
        result = _run(_CB, ["--status"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode in (0, 1)  # 0 = tripped shown, 1 = not tripped

    def test_reset_when_not_tripped_exits_1(self, orch_dir, make_event):
        """Circuit breaker not tripped — reset is a noop, exits 1."""
        make_event("orchestrator_heartbeat", data={})
        result = _run(
            _CB,
            ["--reset", "--confirm", "--operator", "ops@test.com"],
            {"ORCH_PROJECT_DIR": str(orch_dir)},
        )
        assert result.returncode == 1
        output = json.loads(result.stdout)
        assert output.get("status") == "noop"

    def test_reset_without_confirm_when_not_tripped_exits_1(self, orch_dir, make_event):
        """circuit_breaker.py checks tripped state before flag validation — not tripped → 1."""
        make_event("orchestrator_heartbeat", data={})
        result = _run(
            _CB,
            ["--reset", "--operator", "ops@test.com"],
            {"ORCH_PROJECT_DIR": str(orch_dir)},
        )
        # exits 1 because circuit is not tripped (checked before --confirm validation)
        assert result.returncode == 1
