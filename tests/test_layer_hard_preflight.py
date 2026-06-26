"""Layer Hard Preflight — capability gate for the Bash dependency (F-01).

A meta-orchestrator spawned in background runs without the Bash tool and stalls
for minutes before asking for permission. preflight.py must surface a missing/
unusable Bash deterministically as an E_NO_BASH failure so the infra gate blocks
the cycle immediately.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "dist" / ".claude" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "dist" / ".claude" / "lib"))

import preflight  # noqa: E402


class TestBashCapabilityCheck:
    def test_bash_available_is_first_local_check(self):
        # Fail-fast: the bash probe must run before any other local check.
        assert preflight.LOCAL_CHECKS[0][0] == "bash_available"

    def test_passes_in_normal_environment(self):
        # The suite itself runs under bash; the probe must succeed.
        result = preflight.check_bash_available()
        assert result.ok is True
        assert "bash" in result.reason.lower()

    def test_e_no_bash_when_binary_absent(self, monkeypatch):
        monkeypatch.setattr(preflight.shutil, "which", lambda _name: None)
        result = preflight.check_bash_available()
        assert result.ok is False
        assert result.reason.startswith("E_NO_BASH")
        assert "foreground" in str(result.detail).lower()

    def test_e_no_bash_when_probe_errors(self, monkeypatch):
        monkeypatch.setattr(preflight.shutil, "which", lambda _name: "/usr/bin/bash")

        def _boom(*_a, **_k):
            raise OSError("permission denied")

        monkeypatch.setattr(preflight.subprocess, "run", _boom)
        result = preflight.check_bash_available()
        assert result.ok is False
        assert result.reason.startswith("E_NO_BASH")

    def test_failed_bash_propagates_to_overall_not_ok(self, monkeypatch):
        monkeypatch.setattr(preflight.shutil, "which", lambda _name: None)
        local = preflight.run_checks([("bash_available", preflight.check_bash_available)])
        output = preflight.build_output(local, {}, quick=True)
        assert output["ok"] is False
        assert any(f["check"] == "bash_available" for f in output["failed_checks"])
