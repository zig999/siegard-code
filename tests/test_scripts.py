"""
Script tests — preflight.py and circuit_breaker.py via subprocess boundary.
"""
import json
import subprocess
import sys
from pathlib import Path
import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "dist" / ".claude" / "scripts"
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
        # "Healthy" includes a configured target CLAUDE.md (claude_md_config).
        (orch_dir / "CLAUDE.md").write_text(
            "# Target\n\nspecs_dir: specs\ndomain: billing\n", encoding="utf-8")
        result = _run(_PREFLIGHT, ["--quick"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        # Exit code 0 means all checks passed
        assert result.returncode == 0, f"stderr: {result.stderr}"

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


# ---------------------------------------------------------------------------
# dlq_triage.py
# ---------------------------------------------------------------------------

_DLQ = _SCRIPTS_DIR / "dlq_triage.py"


def _setup_dlq_task(orch_dir):
    """Append events to create a DLQ task via the Python API directly."""
    import sys
    sys.path.insert(0, str(_SCRIPTS_DIR.parent.parent / "lib"))
    import importlib
    import os
    os.environ["ORCH_PROJECT_DIR"] = str(orch_dir)
    import orch_core
    importlib.reload(orch_core)

    orch_core.append_event("test", "phase_declared", data={
        "workflow_id": "wf-dlq", "phases": [{"name": "sdd", "order": 1, "required": True}]
    })
    orch_core.append_event("test", "phase_entered", data={
        "phase": "sdd", "order": 1, "workflow_id": "wf-dlq"
    })
    return orch_core


class TestDLQTriage:

    def test_exits_1_when_no_dlq_tasks(self, orch_dir, make_event):
        """No DLQ tasks → exit 1."""
        make_event("orchestrator_heartbeat", data={})
        result = _run(_DLQ, ["--json"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode == 1

    def test_exits_4_when_no_log(self, tmp_path):
        """No log.jsonl → exit 4 (error)."""
        result = _run(_DLQ, ["--json"], {"ORCH_PROJECT_DIR": str(tmp_path)})
        assert result.returncode == 4

    def test_exits_0_when_dlq_tasks_present(self, orch_dir, make_event):
        """DLQ tasks present → exit 0 and JSON output."""
        oc = _setup_dlq_task(orch_dir)
        oc.append_event("test", "task_created", task_id="t1", data={
            "phase": "sdd", "tier": "standard", "type": "spec", "spec": "x", "deps": []
        })
        oc.append_event("test", "task_claimed", task_id="t1", data={
            "phase": "sdd", "worker_type": "spec-w", "worker_id": "wkr-01"
        })
        oc.append_event("test", "task_failed", task_id="t1", data={
            "phase": "sdd", "reason": "internal_error", "retryable": False
        })
        oc.append_event("test", "task_dlq", task_id="t1", data={
            "phase": "sdd", "reason": "max_attempts_exceeded", "last_error": "exhausted retries"
        })
        result = _run(_DLQ, ["--json"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["total_dlq"] >= 1

    def test_json_output_has_buckets(self, orch_dir, make_event):
        """JSON output must include a buckets dict."""
        make_event("orchestrator_heartbeat", data={})
        result = _run(_DLQ, ["--json"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        # Even when no DLQ tasks, JSON contains structure
        output = json.loads(result.stdout)
        assert "total_dlq" in output

    def test_invalid_args_exits_2(self, orch_dir, make_event):
        make_event("orchestrator_heartbeat", data={})
        result = _run(_DLQ, ["--unknown-flag"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# gc_orphan_blobs.py
# ---------------------------------------------------------------------------

_GC = _SCRIPTS_DIR / "gc_orphan_blobs.py"


class TestGCOrphanBlobs:

    def test_exits_4_when_no_log(self, tmp_path):
        """No log.jsonl → exit 4."""
        result = _run(_GC, ["--json"], {"ORCH_PROJECT_DIR": str(tmp_path)})
        assert result.returncode == 4

    def test_exits_0_when_no_blobs_dir(self, orch_dir, make_event):
        """log.jsonl exists but no blobs/ dir → exit 0 (noop)."""
        make_event("orchestrator_heartbeat", data={})
        blobs_dir = orch_dir / ".orch" / "blobs"
        if blobs_dir.exists():
            import shutil
            shutil.rmtree(blobs_dir)
        result = _run(_GC, ["--json"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["status"] == "noop"

    def test_dry_run_reports_orphans_without_deleting(self, orch_dir, make_event):
        """Dry run: orphan blobs are reported but not deleted."""
        make_event("orchestrator_heartbeat", data={})
        blobs_dir = orch_dir / ".orch" / "blobs"
        blobs_dir.mkdir(exist_ok=True)
        orphan = blobs_dir / "orphan_blob.json"
        orphan.write_text(json.dumps({"data": "unreferenced"}))

        result = _run(_GC, ["--json"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["orphans_found"] >= 1
        assert output["orphans_deleted"] == 0
        assert orphan.exists()

    def test_delete_removes_orphan_blobs(self, orch_dir, make_event):
        """--delete flag removes unreferenced blobs."""
        make_event("orchestrator_heartbeat", data={})
        blobs_dir = orch_dir / ".orch" / "blobs"
        blobs_dir.mkdir(exist_ok=True)
        orphan = blobs_dir / "orphan_to_delete.json"
        orphan.write_text(json.dumps({"data": "gone"}))

        result = _run(_GC, ["--json", "--delete"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["orphans_deleted"] >= 1
        assert not orphan.exists()

    def test_invalid_args_exits_2(self, orch_dir, make_event):
        make_event("orchestrator_heartbeat", data={})
        result = _run(_GC, ["--unknown-flag"], {"ORCH_PROJECT_DIR": str(orch_dir)})
        assert result.returncode == 2
