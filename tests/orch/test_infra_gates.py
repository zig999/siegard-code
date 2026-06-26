"""TD-01 — orch-infra gate scripts (run_preflight / run_integrity / run_circuit_check).

These three wrappers are the Step 0 hard gates of EVERY phase orchestrator:
a regression here silently blocks all workflows. Each test runs the real
script as a subprocess against an isolated ORCH_PROJECT_DIR and asserts the
structured-JSON contract (status, check, reason) and the exit code.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).parents[2] / "dist" / ".claude" / "skills"
INFRA = SKILLS_DIR / "orch-infra" / "scripts"
APPEND = str(SKILLS_DIR / "orch-log" / "scripts" / "append.py")


def _run(script: str, tmp_path) -> tuple[int, dict]:
    env = dict(os.environ)
    env["ORCH_PROJECT_DIR"] = str(tmp_path)
    r = subprocess.run(
        [sys.executable, str(INFRA / script)],
        cwd=str(tmp_path), capture_output=True, text=True, env=env,
    )
    try:
        payload = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        payload = {"_unparseable_stdout": r.stdout, "_stderr": r.stderr}
    return r.returncode, payload


def _append(tmp_path, event_type, task_id=None, data=None, agent="orchestrator"):
    env = dict(os.environ)
    env["ORCH_PROJECT_DIR"] = str(tmp_path)
    cmd = [sys.executable, APPEND, "--agent", agent, "--event-type", event_type,
           "--data", json.dumps(data or {})]
    if task_id:
        cmd += ["--task-id", task_id]
    r = subprocess.run(cmd, cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _seed_phase(tmp_path):
    _append(tmp_path, "phase_declared", data={
        "workflow_id": "wf-gates",
        "phases": [{"name": "dev", "order": 1, "required": True}]})
    _append(tmp_path, "phase_entered",
            data={"phase": "dev", "order": 1, "workflow_id": "wf-gates"})


# ---------------------------------------------------------------------------
# run_integrity.py
# ---------------------------------------------------------------------------

class TestRunIntegrity:
    def test_ok_when_no_log(self, tmp_path):
        code, out = _run("run_integrity.py", tmp_path)
        assert code == 0
        assert out["status"] == "ok"
        assert out["check"] == "integrity"
        assert out["events_verified"] == 0
        assert out["note"] == "no_log"

    def test_ok_on_valid_chain(self, tmp_path):
        _seed_phase(tmp_path)
        code, out = _run("run_integrity.py", tmp_path)
        assert code == 0
        assert out["status"] == "ok"
        assert out["events_verified"] == 2

    def test_blocked_on_tampered_log(self, tmp_path):
        _seed_phase(tmp_path)
        log = tmp_path / ".orch" / "log.jsonl"
        # Flip payload content in the first line: JSON stays valid, hash chain breaks.
        tampered = log.read_text(encoding="utf-8").replace("wf-gates", "wf-EVIL!", 1)
        log.write_text(tampered, encoding="utf-8")
        code, out = _run("run_integrity.py", tmp_path)
        assert code == 1
        assert out["status"] == "blocked"
        assert out["reason"] in ("chain_invalid", "corrupted_log")

    def test_tolerates_truncated_last_line(self, tmp_path):
        """A malformed LAST line is a torn write from a crash mid-append — the
        event was never acknowledged, so the chain is still considered intact
        (documented in _iter_events_from_path). Pin that semantics here."""
        _seed_phase(tmp_path)
        log = tmp_path / ".orch" / "log.jsonl"
        with log.open("a", encoding="utf-8") as fh:
            fh.write('{"seq": 3, "truncated...')
        code, out = _run("run_integrity.py", tmp_path)
        assert code == 0
        assert out["status"] == "ok"
        assert out["events_verified"] == 2

    def test_blocked_on_malformed_line_in_the_middle(self, tmp_path):
        _seed_phase(tmp_path)
        log = tmp_path / ".orch" / "log.jsonl"
        lines = log.read_text(encoding="utf-8").splitlines()
        lines.insert(1, "{not valid json")  # between event 1 and event 2
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        code, out = _run("run_integrity.py", tmp_path)
        assert code == 1
        assert out["status"] == "blocked"
        assert out["reason"] in ("chain_invalid", "corrupted_log")


# ---------------------------------------------------------------------------
# run_circuit_check.py
# ---------------------------------------------------------------------------

class TestRunCircuitCheck:
    def test_ok_when_no_log(self, tmp_path):
        code, out = _run("run_circuit_check.py", tmp_path)
        assert code == 0
        assert out["status"] == "ok"
        assert out["check"] == "circuit"
        assert out["tripped"] is False
        assert out["note"] == "no_log"

    def test_ok_on_healthy_log(self, tmp_path):
        _seed_phase(tmp_path)
        code, out = _run("run_circuit_check.py", tmp_path)
        assert code == 0
        assert out["status"] == "ok"
        assert out["tripped"] is False

    def test_blocked_when_breaker_already_tripped(self, tmp_path):
        _seed_phase(tmp_path)
        _append(tmp_path, "circuit_breaker_tripped", data={
            "window_start": "2026-06-12T10:00:00Z",
            "window_end": "2026-06-12T10:10:00Z",
            "failure_count": 50,
            "threshold": 50,
        })
        code, out = _run("run_circuit_check.py", tmp_path)
        assert code == 1
        assert out["status"] == "blocked"
        assert out["tripped"] is True
        assert out["reason"] == "circuit_tripped"


# ---------------------------------------------------------------------------
# run_preflight.py
# ---------------------------------------------------------------------------

class TestRunPreflight:
    def test_contract_status_matches_exit_code(self, tmp_path):
        """The wrapper must emit single-line JSON with the documented shape and
        an exit code consistent with `status`. The overall ok/blocked outcome
        depends on the host (e.g. claude binary present), so the contract —
        not a specific verdict — is what this asserts."""
        code, out = _run("run_preflight.py", tmp_path)
        assert "_unparseable_stdout" not in out, out
        assert out["check"] == "preflight"
        assert out["status"] in ("ok", "blocked")
        assert (code == 0) == (out["status"] == "ok")
        if out["status"] == "ok":
            assert out["passed"] == out["total"]
            assert out["failed_count"] == 0
        else:
            assert "reason" in out

    def test_underlying_preflight_quick_emits_valid_json(self, tmp_path):
        """preflight.py --quick itself must produce parseable JSON with an `ok`
        bool — catches import-time crashes (e.g. an unguarded fcntl import)."""
        script = Path(__file__).parents[2] / "dist" / ".claude" / "scripts" / "preflight.py"
        env = dict(os.environ)
        env["ORCH_PROJECT_DIR"] = str(tmp_path)
        r = subprocess.run([sys.executable, str(script), "--quick"],
                           cwd=str(tmp_path), capture_output=True, text=True, env=env)
        data = json.loads(r.stdout)
        assert isinstance(data.get("ok"), bool)
        assert data.get("mode") == "quick"
        assert (r.returncode == 0) == data["ok"]
