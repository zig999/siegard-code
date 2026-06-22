"""
SIEGARD-01 — root-cause hint on worker death + structural-failure telemetry.

Regression for the forensic package in temp/siegard-fixes/. Imports the hooks
directly (orch_core lib is already on sys.path via tests/conftest.py).

- test_infer_cause_* : unit of the heuristic (short→tool, long→context). Pure.
- test_synthesized_failure_carries_cause : enriched failure dict preserves the
  original `reason` and gains suspected_cause + elapsed_s. Pure.
- test_metrics_expose_failure_breakdown : _compute_metrics surfaces
  failure_reason_breakdown + structural_failure_rate. Uses inline path isolation
  (monkeypatch, NO reload — orch_dir's reload would break on_stop's bound symbols).
- test_on_stop_counts_emitted_reason : grep guard — on_stop counts the SAME
  string the hook emits (protects against the historical mismatch regressing).
"""
import sys
from datetime import timedelta
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent.parent / "dist" / ".claude" / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import orch_core  # noqa: E402  (lib already on sys.path via conftest)
import on_stop  # noqa: E402
import on_subagent_stop as sas  # noqa: E402


def _iso_ago(seconds: int) -> str:
    dt = orch_core.parse_iso(orch_core.now_iso()) - timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _isolate_orch(tmp_path, monkeypatch):
    """Redirect orch_core paths to a tmp .orch/ WITHOUT reloading the module, so
    on_stop's import-time bindings (reduce_all, PhaseStatus) stay identity-valid."""
    base = tmp_path / ".orch"
    rel = {
        "ORCH_DIR": base, "LOG_PATH": base / "log.jsonl",
        "LOCK_PATH": base / "log.jsonl.lock", "STATE_DIR": base / "state",
        "DLQ_DIR": base / "dlq", "AUDIT_DIR": base / "audit",
        "METRICS_DIR": base / "metrics", "BLOBS_DIR": base / "blobs",
        "WORKERS_DIR": base / "workers", "CONFIG_PATH": base / "config.json",
    }
    for name, val in rel.items():
        monkeypatch.setattr(orch_core, name, val)
    orch_core.ensure_dirs()


def test_infer_cause_short_elapsed_is_tool_error():
    cause = sas._infer_cause({"registered_at": _iso_ago(2)})
    assert cause["suspected_cause"] == "tool_error_or_missing_input"
    assert cause["elapsed_s"] >= 0


def test_infer_cause_long_elapsed_is_context_or_timeout():
    cause = sas._infer_cause({"registered_at": _iso_ago(200)})
    assert cause["suspected_cause"] == "context_limit_or_timeout"


def test_infer_cause_large_context_wins():
    cause = sas._infer_cause(
        {"registered_at": _iso_ago(2), "spawn_context_chars": 200_000}
    )
    assert cause["suspected_cause"] == "context_limit"
    assert cause["spawn_context_chars"] == 200_000


def test_synthesized_failure_carries_cause():
    """The dict the hook passes to append_event keeps `reason` and gains the hint."""
    base = {
        "phase": "dev",
        "reason": "worker_exited_without_terminal",
        "retryable": True,
        "synthesized_by": "u-fe-developer-x",
    }
    data = {**base, **sas._infer_cause({"registered_at": _iso_ago(5)})}
    assert data["reason"] == "worker_exited_without_terminal"  # contract preserved
    assert data["retryable"] is True
    assert "suspected_cause" in data and "elapsed_s" in data


def test_metrics_expose_failure_breakdown(tmp_path, monkeypatch):
    """_compute_metrics surfaces failure_reason_breakdown + structural_failure_rate."""
    _isolate_orch(tmp_path, monkeypatch)

    orch_core.append_event(
        agent="orch", event_type="phase_declared",
        data={"workflow_id": "w", "phases": [{"name": "dev", "order": 1, "required": True}]},
    )
    orch_core.append_event(
        agent="orch", event_type="phase_entered",
        data={"phase": "dev", "order": 1, "workflow_id": "w"},
    )
    orch_core.append_event(
        agent="orch", event_type="task_created", task_id="T1",
        data={"phase": "dev", "tier": "standard", "type": "impl", "spec": "s", "deps": []},
    )
    orch_core.append_event(
        agent="orch", event_type="task_claimed", task_id="T1",
        data={"phase": "dev", "worker_type": "u-be-developer", "worker_id": "w1"},
    )
    orch_core.append_event(
        agent="orch", event_type="task_failed", task_id="T1",
        data={"phase": "dev", "reason": "worker_exited_without_terminal", "retryable": True},
    )

    metrics = on_stop._compute_metrics(orch_core.reduce_all())

    assert "failure_reason_breakdown" in metrics
    assert metrics["failure_reason_breakdown"].get("worker_exited_without_terminal") == 1
    assert metrics["structural_failure_rate"] > 0.0


def test_on_stop_counts_emitted_reason():
    """on_stop counts the SAME string the hook emits — no stale string."""
    root = Path(__file__).resolve().parent.parent
    on_stop_src = (root / "dist" / ".claude" / "hooks" / "on_stop.py").read_text(encoding="utf-8")
    hook_src = (root / "dist" / ".claude" / "hooks" / "on_subagent_stop.py").read_text(encoding="utf-8")

    emitted = "worker_exited_without_terminal"
    assert emitted in hook_src, "precondition: the hook emits this string"
    assert "worker_stopped_without_terminal_event" not in on_stop_src, (
        "on_stop.py still references the obsolete string"
    )
    assert emitted in on_stop_src, "on_stop.py must count the string the hook emits"
